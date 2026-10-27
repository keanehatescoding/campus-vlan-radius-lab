#!/usr/bin/env python3
"""Offline consistency checks for the segmented campus network project.

This does NOT validate Cisco IOS syntax on a real image. It checks that the
generated artefacts agree with the design in topology/topology.md and with each
other: addressing, VLANs, trunks, access ports, ACLs, DHCP, NAT, RADIUS users,
client supplicant profiles and the Docker server segment.

Run:
    python3 tests/verify_configs.py
Exit code 0 = all checks passed.
"""

from __future__ import annotations

import ipaddress
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIGS = ROOT / "configs"
RADIUS = ROOT / "radius"
CLIENTS = ROOT / "endpoints" / "client"
SENSOR = ROOT / "endpoints" / "sensor"

SWITCHES = ("SW1", "SW2", "SW3")
EXPECTED_VLANS = {10: "STAFF", 20: "STUDENT", 30: "GUEST", 40: "IOT", 99: "MGMT"}
TRUNK_VLANS = {10, 20, 30, 40, 99}
EXPECTED_TRUNKS = {
    "SW1": {"GigabitEthernet0/0", "GigabitEthernet0/1", "GigabitEthernet0/2"},
    "SW2": {"GigabitEthernet0/0"},
    "SW3": {"GigabitEthernet0/0"},
}
# (switch, port) -> (access VLAN, node name in description)
EXPECTED_ACCESS = {
    ("SW2", "GigabitEthernet0/1"): (10, "STAFF-PC1"),
    ("SW2", "GigabitEthernet0/2"): (10, "STAFF-PC2"),
    ("SW2", "GigabitEthernet0/3"): (10, "STAFF-PC3"),
    ("SW2", "GigabitEthernet1/0"): (20, "STUDENT-PC1"),
    ("SW2", "GigabitEthernet1/1"): (20, "STUDENT-PC2"),
    ("SW2", "GigabitEthernet1/2"): (20, "STUDENT-PC3"),
    ("SW3", "GigabitEthernet0/1"): (30, "GUEST-PC1"),
    ("SW3", "GigabitEthernet0/2"): (40, "SENSOR-TEMP"),
    ("SW3", "GigabitEthernet0/3"): (40, "SENSOR-MOTION"),
    ("SW3", "GigabitEthernet1/0"): (40, "SENSOR-HUMIDITY"),
}
MGMT_IPS = {"SW1": "192.168.99.11", "SW2": "192.168.99.12", "SW3": "192.168.99.13"}
SENSOR_PORTS = {
    "GigabitEthernet0/2": "0200.0000.4001",
    "GigabitEthernet0/3": "0200.0000.4002",
    "GigabitEthernet1/0": "0200.0000.4003",
}
EXPECTED_ACLS = {"STAFF_IN", "STUDENT_IN", "GUEST_IN", "IOT_IN", "MGMT_IN"}

EXPECTED_USERS = {
    "staff1": ("10", "Staff1Pass!"),
    "staff2": ("10", "Staff2Pass!"),
    "staff3": ("10", "Staff3Pass!"),
    "student1": ("20", "Student1Pass!"),
    "student2": ("20", "Student2Pass!"),
    "student3": ("20", "Student3Pass!"),
    "guest1": ("30", "Guest1Pass!"),
    "0200.0000.4001": ("40", None),
    "0200.0000.4002": ("40", None),
    "0200.0000.4003": ("40", None),
}
SENSOR_MAC_ENV = {
    "SENSOR_MAC_TEMP": "0200.0000.4001",
    "SENSOR_MAC_MOTION": "0200.0000.4002",
    "SENSOR_MAC_HUMIDITY": "0200.0000.4003",
}


class Checker:
    def __init__(self) -> None:
        self.passed = 0
        self.failed: list[str] = []

    def check(self, condition: bool, message: str) -> None:
        if condition:
            self.passed += 1
            print(f"[PASS] {message}")
        else:
            self.failed.append(message)
            print(f"[FAIL] {message}")

    def contains(self, haystack: str, needle: str, message: str) -> None:
        self.check(needle in haystack, message)

    def summary(self) -> int:
        print()
        print("=" * 72)
        print(f"SUMMARY: {self.passed} passed, {len(self.failed)} failed")
        if self.failed:
            print()
            for item in self.failed:
                print(f"  - {item}")
            return 1
        return 0


def read(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(f"missing required file: {path}")
    return path.read_text(encoding="utf-8")


def parse_blocks(text: str, header_re: re.Pattern[str]) -> dict[str, list[str]]:
    """Parse IOS-style indented blocks, e.g. interface or ACL stanzas."""
    blocks: dict[str, list[str]] = {}
    current: str | None = None
    for raw in text.splitlines():
        if not raw.strip():
            continue
        if raw[0].isspace():
            if current is not None:
                blocks[current].append(raw.strip())
            continue
        match = header_re.match(raw)
        if match:
            current = match.group(1)
            blocks[current] = []
            continue
        # Any top-level line, including '!', closes the current block.
        current = None
    return blocks


def block_text(blocks: dict[str, list[str]], name: str) -> str:
    return "\n".join(blocks.get(name, []))


def parse_vlan_list(value: str) -> set[int]:
    result: set[int] = set()
    for part in value.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            start, end = part.split("-", 1)
            result.update(range(int(start), int(end) + 1))
        else:
            result.add(int(part))
    return result


def parse_env(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    for raw in read(path).splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        env[key.strip()] = value.strip().strip('"').strip("'")
    return env


def parse_users(path: Path) -> dict[str, str]:
    """Return username -> joined attribute text for a FreeRADIUS users file."""
    entries: dict[str, list[str]] = {}
    current: str | None = None
    for raw in read(path).splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        if raw[0].isspace():
            if current is not None:
                entries[current].append(raw.strip())
            continue
        parts = raw.split(None, 1)
        current = parts[0]
        entries[current] = [parts[1].strip() if len(parts) > 1 else ""]
    return {name: " ".join(parts) for name, parts in entries.items()}


def main() -> int:
    c = Checker()

    # ------------------------------------------------------------------
    # Required delivery files
    # ------------------------------------------------------------------
    required = [
        ROOT / "README.md",
        ROOT / "topology" / "topology.md",
        ROOT / "topology" / "gns3-build-steps.md",
        ROOT / "tests" / "test-plan.md",
        ROOT / "report" / "report-outline.md",
        RADIUS / "docker-compose.yml",
        RADIUS / "clients.conf",
        RADIUS / "users",
        RADIUS / "secrets.env",
        RADIUS / "mosquitto.conf",
        RADIUS / "setup-server-bridge.sh",
        SENSOR / "Dockerfile",
        SENSOR / "sensor.py",
        CLIENTS / "Dockerfile",
        CLIENTS / "entrypoint.sh",
    ]
    for path in required:
        c.check(path.exists(), f"required file exists: {path.relative_to(ROOT)}")
    for name in ("R1", "R2", "SW1", "SW2", "SW3"):
        c.check((CONFIGS / f"{name}.cfg").exists(), f"required config exists: configs/{name}.cfg")

    if c.failed:
        # Avoid a cascade of confusing parse errors when files are missing.
        return c.summary()

    cfg = {name: read(CONFIGS / f"{name}.cfg") for name in ("R1", "R2", "SW1", "SW2", "SW3")}
    clients_conf = read(RADIUS / "clients.conf")
    users = parse_users(RADIUS / "users")
    env = parse_env(RADIUS / "secrets.env")
    compose = read(RADIUS / "docker-compose.yml")
    mosquitto = read(RADIUS / "mosquitto.conf")
    topology = read(ROOT / "topology" / "topology.md")

    # ------------------------------------------------------------------
    # Basic structure and hostnames
    # ------------------------------------------------------------------
    for name, text in cfg.items():
        c.check(re.search(rf"^hostname {name}$", text, re.M) is not None, f"{name}: hostname is {name}")
        c.check(text.rstrip().endswith("end"), f"{name}: config ends with 'end'")
        c.check("enable secret " in text, f"{name}: enable secret configured")

    # ------------------------------------------------------------------
    # VLAN database on every switch
    # ------------------------------------------------------------------
    switch_ifaces: dict[str, dict[str, list[str]]] = {}
    switch_vlans: dict[str, dict[int, str]] = {}
    for sw in SWITCHES:
        text = cfg[sw]
        switch_ifaces[sw] = parse_blocks(text, re.compile(r"^interface\s+(\S+)$"))
        vlan_blocks = parse_blocks(text, re.compile(r"^vlan\s+(\d+)$"))
        found: dict[int, str] = {}
        for vid, lines in vlan_blocks.items():
            match = re.search(r"^name\s+(\S+)$", "\n".join(lines), re.M)
            found[int(vid)] = match.group(1) if match else ""
        switch_vlans[sw] = found
        for vid, name in EXPECTED_VLANS.items():
            c.check(found.get(vid) == name, f"{sw}: VLAN {vid} exists and is named {name}")
        c.check("spanning-tree mode rapid-pvst" in text, f"{sw}: rapid-pvst enabled")

    # ------------------------------------------------------------------
    # Trunks and access ports
    # ------------------------------------------------------------------
    configured_trunks: dict[str, set[str]] = {}
    configured_access: dict[tuple[str, str], int] = {}
    for sw in SWITCHES:
        trunks: set[str] = set()
        for iface, lines in switch_ifaces[sw].items():
            block = "\n".join(lines)
            if re.search(r"^switchport mode trunk$", block, re.M):
                trunks.add(iface)
                allowed_match = re.search(r"^switchport trunk allowed vlan (.+)$", block, re.M)
                c.check(allowed_match is not None, f"{sw} {iface}: trunk has explicit allowed VLAN list")
                if allowed_match:
                    allowed = parse_vlan_list(allowed_match.group(1))
                    c.check(
                        allowed == TRUNK_VLANS,
                        f"{sw} {iface}: trunk allowed VLANs are exactly {sorted(TRUNK_VLANS)}",
                    )
            access_match = re.search(r"^switchport access vlan (\d+)$", block, re.M)
            if access_match:
                configured_access[(sw, iface)] = int(access_match.group(1))
        configured_trunks[sw] = trunks
        c.check(
            trunks == EXPECTED_TRUNKS[sw],
            f"{sw}: trunk ports are exactly {sorted(EXPECTED_TRUNKS[sw])}",
        )

    c.check(
        set(configured_access) == set(EXPECTED_ACCESS),
        "access-port map has exactly the expected ports and no extra access ports",
    )

    for (sw, iface), (vlan, node) in EXPECTED_ACCESS.items():
        lines = switch_ifaces[sw].get(iface, [])
        block = "\n".join(lines)
        c.check(bool(lines), f"{sw} {iface}: interface is configured")
        c.check(
            configured_access.get((sw, iface)) == vlan,
            f"{sw} {iface}: access VLAN is {vlan}",
        )
        c.check(
            re.search(r"^switchport mode access$", block, re.M) is not None,
            f"{sw} {iface}: switchport mode access",
        )
        c.check(node in block, f"{sw} {iface}: description identifies {node}")
        if vlan in (10, 20, 30):
            c.check(
                re.search(r"^authentication port-control auto$", block, re.M) is not None,
                f"{sw} {iface}: authentication port-control auto",
            )
            c.check(
                re.search(r"^dot1x pae authenticator$", block, re.M) is not None,
                f"{sw} {iface}: dot1x pae authenticator",
            )
            c.check(
                re.search(r"^authentication order dot1x$", block, re.M) is not None,
                f"{sw} {iface}: 802.1X is first authentication method",
            )
            c.check(
                "authentication event fail action authorize vlan 30" in block,
                f"{sw} {iface}: failed auth falls back to VLAN 30",
            )
            c.check(
                "authentication event no-response action authorize vlan 30" in block,
                f"{sw} {iface}: no RADIUS response falls back to VLAN 30",
            )
            c.check(
                "mab" not in [line.strip() for line in lines],
                f"{sw} {iface}: user port is not MAB-only",
            )
        else:
            # IOSvL2 accepts "mab" but never creates an authentication session,
            # so the shipped configs pin the sensor MAC with port security.
            sensor_mac = SENSOR_PORTS.get(iface)
            c.check(
                sensor_mac is not None and f"switchport port-security mac-address {sensor_mac}" in block,
                f"{sw} {iface}: port security pins sensor MAC {sensor_mac}",
            )
            c.check(
                re.search(r"^switchport port-security maximum 1$", block, re.M) is not None,
                f"{sw} {iface}: port security allows one MAC",
            )
            c.check(
                re.search(r"^switchport port-security violation restrict$", block, re.M) is not None,
                f"{sw} {iface}: port security restricts unknown MACs",
            )
            c.check(
                "authentication event fail action authorize vlan 30" not in block,
                f"{sw} {iface}: failed IoT auth is not moved to guest VLAN",
            )

    # Spanning tree root only on SW1.
    c.check(
        "spanning-tree vlan 10,20,30,40,99 root primary" in cfg["SW1"],
        "SW1: spanning-tree root primary for all VLANs",
    )
    for sw in ("SW2", "SW3"):
        c.check("root primary" not in cfg[sw], f"{sw}: does not claim spanning-tree root")

    # ------------------------------------------------------------------
    # Management SVIs and default gateways
    # ------------------------------------------------------------------
    for sw, ip in MGMT_IPS.items():
        block = block_text(switch_ifaces[sw], "Vlan99")
        c.check(re.search(rf"^ip address {re.escape(ip)} 255\.255\.255\.0$", block, re.M) is not None,
                f"{sw}: Vlan99 address is {ip}")
        c.check("ip default-gateway 192.168.99.1" in cfg[sw], f"{sw}: default gateway is 192.168.99.1")

    # ------------------------------------------------------------------
    # R1 addressing, subinterfaces, ACL application, NAT, DHCP
    # ------------------------------------------------------------------
    r1_ifaces = parse_blocks(cfg["R1"], re.compile(r"^interface\s+(\S+)$"))
    expected_r1 = {
        "GigabitEthernet0/0.10": ("192.168.10.1", "255.255.255.0", 10, "STAFF_IN"),
        "GigabitEthernet0/0.20": ("192.168.20.1", "255.255.255.0", 20, "STUDENT_IN"),
        "GigabitEthernet0/0.30": ("192.168.30.1", "255.255.255.0", 30, "GUEST_IN"),
        "GigabitEthernet0/0.40": ("192.168.40.1", "255.255.255.0", 40, "IOT_IN"),
        "GigabitEthernet0/0.99": ("192.168.99.1", "255.255.255.0", 99, "MGMT_IN"),
        "GigabitEthernet0/1": ("192.168.50.1", "255.255.255.0", None, None),
        "GigabitEthernet0/2": ("10.0.0.1", "255.255.255.252", None, None),
    }
    for iface, (ip, mask, vlan, acl) in expected_r1.items():
        block = block_text(r1_ifaces, iface)
        c.check(
            re.search(rf"^ip address {re.escape(ip)} {re.escape(mask)}$", block, re.M) is not None,
            f"R1 {iface}: address is {ip}/{mask}",
        )
        if vlan is not None:
            c.check(
                re.search(rf"^encapsulation dot1Q {vlan}$", block, re.M) is not None,
                f"R1 {iface}: encapsulation dot1Q {vlan}",
            )
            c.check(
                re.search(rf"^ip access-group {acl} in$", block, re.M) is not None,
                f"R1 {iface}: {acl} applied inbound",
            )
        if vlan in (10, 20, 30, 40):
            c.check("ip nat inside" in block, f"R1 {iface}: NAT inside")
        if iface == "GigabitEthernet0/2":
            c.check("ip nat outside" in block, f"R1 {iface}: NAT outside")
        if iface == "GigabitEthernet0/1":
            c.check("ip nat inside" not in block, "R1 server interface is not NATed")

    c.check("ip route 0.0.0.0 0.0.0.0 10.0.0.2" in cfg["R1"], "R1: default route via R2")
    c.check(
        "ip nat inside source list NAT_INSIDE interface GigabitEthernet0/2 overload" in cfg["R1"],
        "R1: PAT overload on the R2 link",
    )
    nat_block = block_text(parse_blocks(cfg["R1"], re.compile(r"^ip access-list standard (\S+)$")), "NAT_INSIDE")
    for vlan in (10, 20, 30, 40):
        c.check(
            f"permit 192.168.{vlan}.0 0.0.0.255" in nat_block,
            f"R1: NAT ACL includes VLAN {vlan} subnet",
        )
    c.check("permit 192.168.50.0 0.0.0.255" not in nat_block, "R1: server subnet is not NATed")
    c.check("permit 192.168.99.0 0.0.0.255" not in nat_block, "R1: MGMT subnet is not NATed")

    for vlan in (10, 20, 30, 40):
        c.check(
            f"ip dhcp excluded-address 192.168.{vlan}.1 192.168.{vlan}.20" in cfg["R1"],
            f"R1: DHCP excludes .1-.20 for VLAN {vlan}",
        )
        c.check(
            f"network 192.168.{vlan}.0 255.255.255.0" in cfg["R1"],
            f"R1: DHCP pool exists for VLAN {vlan}",
        )
        c.check(
            f"default-router 192.168.{vlan}.1" in cfg["R1"],
            f"R1: DHCP default router for VLAN {vlan}",
        )
    c.check("service dhcp" in cfg["R1"], "R1: DHCP service enabled")

    # ------------------------------------------------------------------
    # ACL definitions and references
    # ------------------------------------------------------------------
    acl_blocks = parse_blocks(cfg["R1"], re.compile(r"^ip access-list extended (\S+)$"))
    defined_acls = set(acl_blocks)
    c.check(defined_acls == EXPECTED_ACLS, "R1: exactly the five required named extended ACLs exist")
    for acl, lines in acl_blocks.items():
        meaningful = [line for line in lines if line and not line.startswith("remark")]
        c.check(
            meaningful and meaningful[-1] == "deny ip any any log",
            f"R1: ACL {acl} ends with 'deny ip any any log'",
        )
    c.check("permit ip any any" in acl_blocks.get("STAFF_IN", []), "R1: STAFF_IN permits all traffic")
    for acl in ("STUDENT_IN", "GUEST_IN", "IOT_IN", "MGMT_IN"):
        c.check(
            "permit ip any any" not in acl_blocks.get(acl, []),
            f"R1: ACL {acl} does not contain a blanket permit",
        )
    c.check(
        any("deny ip any 192.168.0.0 0.0.255.255" == line for line in acl_blocks.get("STUDENT_IN", [])),
        "R1: STUDENT_IN denies all 192.168/16 destinations before Internet permits",
    )
    c.check(
        any("deny ip any 192.168.0.0 0.0.255.255" == line for line in acl_blocks.get("GUEST_IN", [])),
        "R1: GUEST_IN denies all 192.168/16 destinations",
    )
    for acl in ("STUDENT_IN", "GUEST_IN"):
        joined = "\n".join(acl_blocks.get(acl, []))
        for needle, label in (
            ("permit udp any any eq domain", "DNS/UDP"),
            ("permit tcp any any eq domain", "DNS/TCP"),
            ("permit tcp any any eq www", "HTTP"),
            ("permit tcp any any eq 443", "HTTPS"),
            ("permit tcp any any established", "established return traffic"),
        ):
            c.check(needle in joined, f"R1: {acl} permits {label}")
    iot_joined = "\n".join(acl_blocks.get("IOT_IN", []))
    c.check("permit tcp any host 192.168.50.20 eq 1883" in iot_joined, "R1: IOT_IN permits MQTT to .20:1883")
    c.check("permit udp any eq bootpc any eq bootps" in iot_joined, "R1: IOT_IN permits DHCP")
    mgmt_joined = "\n".join(acl_blocks.get("MGMT_IN", []))
    c.check("host 192.168.50.10 eq 1812" in mgmt_joined, "R1: MGMT_IN permits RADIUS auth 1812")
    c.check("host 192.168.50.10 eq 1813" in mgmt_joined, "R1: MGMT_IN permits RADIUS accounting 1813")
    c.check("192.168.99.0 0.0.0.255" in mgmt_joined, "R1: MGMT_IN is scoped to the MGMT subnet")

    # Every ACL referenced in an interface must exist.
    referenced = set()
    for iface, lines in r1_ifaces.items():
        for line in lines:
            match = re.match(r"^ip access-group (\S+) (in|out)$", line)
            if match:
                referenced.add(match.group(1))
    c.check(referenced <= defined_acls, "R1: every referenced ACL is defined")
    c.check(referenced == EXPECTED_ACLS, "R1: all five ACLs are actually applied")

    # ------------------------------------------------------------------
    # Unique IPs and no overlapping subnets
    # ------------------------------------------------------------------
    ip_owner: dict[str, list[str]] = defaultdict(list)
    networks: list[tuple[ipaddress._BaseNetwork, str]] = []  # type: ignore[attr-defined]
    for name, text in cfg.items():
        for match in re.finditer(
            r"^\s*ip address (\d{1,3}(?:\.\d{1,3}){3}) (\d{1,3}(?:\.\d{1,3}){3})\s*$",
            text,
            re.M,
        ):
            ip, mask = match.group(1), match.group(2)
            ip_owner[ip].append(name)
            try:
                iface = ipaddress.ip_interface(f"{ip}/{mask}")
                networks.append((iface.network, f"{name}:{ip}"))
            except ValueError:
                c.check(False, f"{name}: invalid IP/mask {ip}/{mask}")
    duplicates = {ip: owners for ip, owners in ip_owner.items() if len(owners) > 1}
    c.check(not duplicates, f"no duplicate IP addresses (found {duplicates or 'none'})")
    overlaps: list[str] = []
    for idx, (net_a, owner_a) in enumerate(networks):
        for net_b, owner_b in networks[idx + 1:]:
            # Multiple interfaces on the same subnet are intentional (VLAN 99,
            # the /30 link). Only a partial overlap is a design error.
            if net_a.overlaps(net_b) and net_a != net_b:
                overlaps.append(f"{owner_a} {net_a} <-> {owner_b} {net_b}")
    c.check(not overlaps, f"no partially overlapping subnets (found {overlaps or 'none'})")

    # ------------------------------------------------------------------
    # R2
    # ------------------------------------------------------------------
    r2_ifaces = parse_blocks(cfg["R2"], re.compile(r"^interface\s+(\S+)$"))
    c.check("ip address 8.8.8.8 255.255.255.255" in block_text(r2_ifaces, "Loopback0"),
            "R2: loopback 8.8.8.8/32")
    c.check("ip address 10.0.0.2 255.255.255.252" in block_text(r2_ifaces, "GigabitEthernet0/0"),
            "R2: link address 10.0.0.2/30")
    c.check("ip route 192.168.0.0 255.255.0.0 10.0.0.1" in cfg["R2"],
            "R2: return route for 192.168.0.0/16")

    # ------------------------------------------------------------------
    # RADIUS: switch clients, shared secret, users, reply attributes
    # ------------------------------------------------------------------
    c.check("ip radius source-interface Vlan99" in cfg["SW1"], "SW1: RADIUS source interface is Vlan99")
    for sw in SWITCHES:
        text = cfg[sw]
        c.check("aaa new-model" in text, f"{sw}: aaa new-model")
        c.check("radius server RADIUS-1" in text, f"{sw}: radius server RADIUS-1")
        c.check("address ipv4 192.168.50.10 auth-port 1812 acct-port 1813" in text,
                f"{sw}: RADIUS server address/ports")
        c.check("aaa group server radius CAMPUS-RADIUS" in text,
                f"{sw}: named RADIUS server group CAMPUS-RADIUS")
        c.check("server name RADIUS-1" in text,
                f"{sw}: RADIUS-1 is a member of the server group")
        c.check("aaa authentication dot1x default group CAMPUS-RADIUS" in text,
                f"{sw}: dot1x authentication uses RADIUS")
        c.check("aaa authorization network default group CAMPUS-RADIUS" in text,
                f"{sw}: network authorization uses RADIUS (needed for dynamic VLAN)")
        c.check("aaa accounting dot1x default start-stop group CAMPUS-RADIUS" in text,
                f"{sw}: dot1x accounting uses RADIUS")
        c.check("dot1x system-auth-control" in text, f"{sw}: dot1x system-auth-control")
        c.check("ip radius source-interface Vlan99" in text, f"{sw}: RADIUS source interface is Vlan99")

    keys: dict[str, str] = {}
    for sw in SWITCHES:
        match = re.search(r"^\s*key 0 (\S+)$", cfg[sw], re.M)
        c.check(match is not None, f"{sw}: RADIUS key configured")
        if match:
            keys[sw] = match.group(1)
    c.check(len(set(keys.values())) == 1, "all switches use the same RADIUS key")
    secret_env = env.get("RADIUS_SECRET")
    c.check(secret_env is not None, "secrets.env defines RADIUS_SECRET")
    if secret_env:
        c.check(set(keys.values()) == {secret_env}, "switch RADIUS keys match secrets.env RADIUS_SECRET")
        c.check(secret_env != "", "RADIUS_SECRET is not empty")

    client_secrets = re.findall(r"^\s*secret\s*=\s*(\S+)$", clients_conf, re.M)
    c.check(client_secrets and len(set(client_secrets)) == 1, "clients.conf uses one shared secret")
    if client_secrets and secret_env:
        c.check(client_secrets[0] == secret_env, "clients.conf secret matches secrets.env")
        c.check(set(keys.values()) == {client_secrets[0]}, "switch keys match clients.conf")
    for ip in MGMT_IPS.values():
        c.check(f"ipaddr       = {ip}" in clients_conf, f"clients.conf has a client for {ip}")

    for name, (vlan, password) in EXPECTED_USERS.items():
        c.check(name in users, f"users file contains {name}")
        if name not in users:
            continue
        attributes = users[name]
        c.check(
            re.search(r"Tunnel-Type\s*=\s*VLAN", attributes) is not None,
            f"users: {name} has Tunnel-Type VLAN",
        )
        c.check(
            re.search(r"Tunnel-Medium-Type\s*=\s*IEEE-802", attributes) is not None,
            f"users: {name} has Tunnel-Medium-Type IEEE-802",
        )
        match = re.search(r"Tunnel-Private-Group-Id\s*=\s*\"?(\d+)\"?", attributes)
        c.check(match is not None and match.group(1) == vlan,
                f"users: {name} maps to VLAN {vlan}")
        if password:
            match = re.search(r'Cleartext-Password\s*:=\s*"([^"]*)"', attributes)
            c.check(match is not None and match.group(1) == password,
                    f"users: {name} password matches the design")

    for env_key, mac in SENSOR_MAC_ENV.items():
        c.check(env.get(env_key) == mac, f"secrets.env {env_key} is {mac}")
        c.check(mac in users, f"users file contains sensor MAC {mac}")

    # ------------------------------------------------------------------
    # Supplicant profiles
    # ------------------------------------------------------------------
    for name, (vlan, password) in EXPECTED_USERS.items():
        if password is None:
            continue
        path = CLIENTS / f"wpa_supplicant-{name}.conf"
        c.check(path.exists(), f"supplicant config exists for {name}")
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        c.check(f'identity="{name}"' in text, f"supplicant {name}: identity is correct")
        c.check(f'password="{password}"' in text, f"supplicant {name}: password matches users file")
        c.check("key_mgmt=IEEE8021X" in text, f"supplicant {name}: IEEE8021X key management")
        c.check("eap=MD5" in text, f"supplicant {name}: EAP-MD5 selected (no certificates needed)")
        c.check("ca_cert" not in text, f"supplicant {name}: no CA certificate required")

    # ------------------------------------------------------------------
    # Docker server segment and sensor
    # ------------------------------------------------------------------
    c.check("freeradius/freeradius-server" in compose, "compose: FreeRADIUS image")
    c.check("eclipse-mosquitto" in compose, "compose: Mosquitto image")
    c.check("driver: macvlan" in compose, "compose: server segment uses macvlan")
    c.check("192.168.50.10" in compose, "compose: RADIUS container address .10")
    c.check("192.168.50.20" in compose, "compose: MQTT container address .20")
    c.check("gateway: 192.168.50.1" in compose, "compose: gateway is R1 .1")
    c.check("listener 1883 0.0.0.0" in mosquitto, "mosquitto: listener on 1883")
    c.check("allow_anonymous true" in mosquitto, "mosquitto: anonymous access for lab")
    c.check(env.get("RADIUS_IP") == "192.168.50.10", "secrets.env RADIUS_IP matches compose")
    c.check(env.get("MQTT_IP") == "192.168.50.20", "secrets.env MQTT_IP matches compose")
    sensor_py = read(SENSOR / "sensor.py")
    for needle, label in (
        ('"id": SENSOR_ID', "JSON id field"),
        ('"type": SENSOR_TYPE', "JSON type field"),
        ('"value": value', "JSON value field"),
        ('"timestamp"', "JSON timestamp field"),
        ("MQTT_BROKER", "broker environment variable"),
        ("campus/iot/", "MQTT topic prefix"),
    ):
        c.check(needle in sensor_py, f"sensor: {label}")
    c.check("PUBLISH_INTERVAL" in sensor_py, "sensor: publish interval is configurable")
    c.check("5" in str(sensor_py), "sensor: default interval references 5 seconds")

    # ------------------------------------------------------------------
    # Documentation sanity
    # ------------------------------------------------------------------
    c.check("STAFF" in topology and "STUDENT" in topology and "GUEST" in topology and "IOT" in topology,
            "topology.md documents all four user VLANs")
    for port in ("SW2 g0/1", "SW2 Gi1/0", "SW2 Gi1/2", "SW3 Gi0/1", "SW3 Gi0/2", "SW3 Gi1/0"):
        c.check(port in topology, f"topology.md documents port map entry {port}")
    c.check("8.8.8.8" in topology, "topology.md documents the simulated Internet host")

    return c.summary()


if __name__ == "__main__":
    sys.exit(main())
