# Segmented Campus Network - GNS3 Build Kit

A complete, paste-ready GNS3 lab for:

- **2 routers** (R1 campus gateway/firewall/DHCP/NAT, R2 simulated ISP)
- **3 switches** (SW1 distribution, SW2 staff/student access, SW3 guest/IoT access)
- **STAFF VLAN** with 3 Docker clients
- **STUDENT VLAN** with 3 Docker clients
- **GUEST VLAN** with 1 Docker client
- **IOT VLAN** with 3 real Docker sensors publishing MQTT
- **Firewall policy** as five named extended ACLs on R1
- **RADIUS dynamic VLAN** using FreeRADIUS, 802.1X for users and MAB for sensors
- **MQTT broker** and a server segment isolated behind R1

The repo is designed so the human only has to supply the Cisco images, build
the GNS3 topology, paste the configs and run the tests. Claude Code did not run
GNS3 or a Cisco image; see [Offline validation performed](#offline-validation-performed)
for exactly what was and was not verified.

## What you must supply

1. **Cisco IOSv image** for R1 and R2 (IOS 15.x, at least 3 GigabitEthernet
   interfaces). Import it into GNS3 as an IOSv QEMU template.
2. **Cisco IOSvL2 image** for SW1, SW2, SW3 (IOS 15.2-class, at least 8
   GigabitEthernet interfaces, 802.1X-capable feature set). Import it as an
   IOSvL2 QEMU template and mark it as an Ethernet switch.
3. **GNS3 2.2.x** with a local Linux server (or a GNS3 VM with Docker).
4. **Docker Engine + Compose v2** on the GNS3 server host, for FreeRADIUS,
   Mosquitto and the endpoint images.

The Cisco images are **not** included and cannot be redistributed here. No
image filenames are assumed: use whatever IOSv/IOSvL2 images you are licensed
to use, then match the interface names in the configs.

You do **not** need Packet Tracer. Packet Tracer cannot do this lab's RADIUS
dynamic VLAN and MAB behavior; use GNS3 or EVE-NG.

## Repository layout

```
network-project/
  README.md                       this file
  topology/
    topology.md                   diagram, port map, addressing
    gns3-build-steps.md           click-by-click GNS3 build and paste order
  configs/
    R1.cfg R2.cfg                 routers
    SW1.cfg SW2.cfg SW3.cfg       switches
  radius/
    docker-compose.yml            FreeRADIUS + Mosquitto on the server segment
    clients.conf                  SW1/SW2/SW3 RADIUS clients + secret
    users                         users, MAC users, Tunnel-* VLAN attributes
    secrets.env                   canonical list of lab secrets/placeholders
    mosquitto.conf                lab broker (anonymous, port 1883)
    setup-server-bridge.sh        br-srv + veth + macvlan plumbing
  endpoints/
    sensor/                       Dockerfile, sensor.py, DHCP/entrypoint
    client/                       Dockerfile, wpa_supplicant-*.conf, entrypoint
  tests/
    test-plan.md                  20 tests, expected results, evidence
    verify_configs.py             offline consistency checker
  report/
    report-outline.md             report sections and screenshot checklist
```

## First 10 minutes

Run these in order. Stop and fix any error before building the GNS3 topology.

### 1. Check the generated files

```sh
cd network-project
python3 tests/verify_configs.py
```

Expected last line: `SUMMARY: ... 0 failed`.

### 2. Prepare the Docker server segment

```sh
cd radius
chmod +x setup-server-bridge.sh
./setup-server-bridge.sh
docker compose up -d
docker compose ps
docker logs radius --tail 30
```

Wait for `Ready to process requests` in the FreeRADIUS log. The script creates
`br-srv` and the `srv-mac`/`srv-br` veth pair. The GNS3 Cloud node attaches to
`br-srv`; R1 g0/1 connects to that Cloud. R1 is `192.168.50.1` and is the
containers' default gateway.

If GNS3 runs inside a **GNS3 VM**, do this inside the VM and attach the Cloud
node to the VM's `br-srv`. A local GNS3 server on the same Linux host is the
simplest setup. Do not run Compose on your desktop while GNS3 runs in a VM that
cannot see that bridge.

### 3. Build endpoint images

```sh
cd ..            # back to network-project/
docker build -t campus-client:1.0 endpoints/client
docker build -t campus-sensor:1.0 endpoints/sensor
```

### 4. Build the GNS3 project

Follow [topology/gns3-build-steps.md](topology/gns3-build-steps.md). It has the
node list, 15 links, Docker environment variables, startup order and the exact
paste procedure.

Recommended startup order: **RADIUS/MQTT -> SW1/SW2/SW3 -> R1/R2 -> endpoints**.

Recommended config paste order: **SW1 -> SW2 -> SW3 -> R1 -> R2**, ending each
with `end` and `write memory`.

### 5. Run the tests

Use [tests/test-plan.md](tests/test-plan.md). The minimum evidence set is in
[report/report-outline.md](report/report-outline.md#screenshot-checklist-minimum).

## Design summary

| Item | Value |
|---|---|
| R1-SW1 link | 802.1Q trunk, VLANs 10,20,30,40,99 |
| SW1-SW2, SW1-SW3 | 802.1Q trunks, same VLAN list |
| Staff | VLAN 10, 192.168.10.0/24, 802.1X, 3 clients |
| Student | VLAN 20, 192.168.20.0/24, 802.1X, 3 clients |
| Guest | VLAN 30, 192.168.30.0/24, 802.1X + fallback, 1 client |
| IoT | VLAN 40, 192.168.40.0/24, MAB, 3 sensors |
| MGMT | VLAN 99, 192.168.99.0/24, SW1 .11/SW2 .12/SW3 .13 |
| Server segment | 192.168.50.0/24, RADIUS .10, MQTT .20, R1 .1 |
| R1-R2 | 10.0.0.0/30, R1 .1, R2 .2 |
| Internet sim | 8.8.8.8/32 on R2 Loopback0 |
| DHCP | R1 pools for 10/20/30/40, leases from .21 |
| NAT | PAT of 10/20/30/40 out R1 g0/2; server and MGMT not translated |
| Firewall | `STAFF_IN`, `STUDENT_IN`, `GUEST_IN`, `IOT_IN`, `MGMT_IN`, inbound on R1 subinterfaces |
| RADIUS | FreeRADIUS 3.2.3, EAP-MD5 for users, MAB for sensors, dynamic VLAN via Tunnel-* attributes |

## Secrets and consistency

`radius/secrets.env` is the canonical list, but Cisco IOS and FreeRADIUS cannot
read it directly, so values are repeated in the files they configure. Before
using the lab outside an isolated GNS3 project, change:

| Secret | Where it appears |
|---|---|
| `RADIUS_SECRET` | `radius/secrets.env`, `radius/clients.conf` (4 clients), `configs/SW1.cfg`, `SW2.cfg`, `SW3.cfg` (`key 0 ...`) |
| `DEVICE_ENABLE_SECRET` | `radius/secrets.env`, `enable secret` and `username admin ... secret` in all five Cisco configs |
| Staff/student/guest passwords | `radius/secrets.env`, `radius/users`, `endpoints/client/wpa_supplicant-*.conf` |
| Sensor MACs | `radius/secrets.env`, `radius/users`, GNS3 Docker node MAC / `SENSOR_MAC` |

The checked-in value `S3cr3t-Shared-Key-2026` is a **placeholder shared
secret**; it is intentionally easy to find. `tests/verify_configs.py` checks
that the copies stay in sync but does not judge their strength.

Do not commit real production secrets. Do not expose the lab's anonymous MQTT
broker or RADIUS shared secret outside the isolated lab network.

## RADIUS authentication choice

Users authenticate with **EAP-MD5**. The stock FreeRADIUS 3.2 image enables
`default_eap_type = md5` and needs no client certificate, so the lab is
reproducible without a PKI. `wpa_supplicant` is started with the wired driver:
`wpa_supplicant -i eth0 -D wired -c <profile>`. The sensor and client
entrypoints request DHCP after authentication.

For PEAP/MSCHAPv2 or EAP-TLS, add a CA/server certificate, set `eap=PEAP` and
`phase2="auth=MSCHAPV2"` (or `eap=TLS`) in the supplicant profiles, and update
the FreeRADIUS `eap` module. EAP-MD5 is deprecated for production Wi-Fi but is
appropriate for this wired lab.

## Offline validation performed

These checks were run in the build environment and do not require GNS3. The
Docker daemon socket was not accessible to the build user, so the container
checks used rootless **Podman with the same images and mounts**; the Compose
file was parsed with Docker Compose v5.6.1. Docker users can run the same
commands with `docker` in place of `podman`.

| Check | Command | Result |
|---|---|---|
| Config consistency | `python3 tests/verify_configs.py` | **415 passed, 0 failed** |
| Compose syntax | `docker compose -f radius/docker-compose.yml config` | Valid; network `campus-network_server`, macvlan parent `srv-mac`, RADIUS .10, MQTT .20 |
| FreeRADIUS syntax | `freeradius -CX` in `freeradius/freeradius-server:3.2.3` with the repo's `clients.conf` + `users` | **Configuration appears to be OK** |
| RADIUS PAP/VLAN | `radtest staff1 ...` and `radtest 0200.0000.4001 ...` | Access-Accept with `Tunnel-Type=VLAN`, `Tunnel-Medium-Type=IEEE-802`, `Tunnel-Private-Group-Id="10"` / `"40"` |
| RADIUS EAP-MD5 | `eapol_test` against the exact supplicant profiles (control-interface line removed for the host test) | **SUCCESS** for staff1/2/3, student1/2/3, guest1; wrong-password profile returns **FAILURE** |
| MQTT payload | Local Mosquitto 2.1 + `sensor.py`, three types, 1-second test interval | JSON with `id`, `type`, `value`, `timestamp`; all three IDs observed |
| Sensor image | `podman build -t campus-sensor:1.0 endpoints/sensor` | Builds; container publishes to Mosquitto |
| Client image | `podman build -t campus-client:1.0 endpoints/client` | Builds; stays running and emits supplicant/DHCP diagnostics |

**Not verified offline:** GNS3 GUI, Cisco IOSv/IOSvL2 command acceptance, real
EAPOL on an IOSvL2 switch, end-to-end dynamic VLAN assignment, GNS3 Cloud
plumbing, and the complete ACL matrix. Those require the images and GNS3 and
are covered by `tests/test-plan.md`.

One implementation correction came out of the offline tests: `wpa_supplicant`
2.10 has no `-f` option, so the client entrypoint redirects stdout/stderr to
`/tmp/wpa_supplicant.log` instead. The image was rebuilt and rechecked after
that change.

## Known limitations

- **IOSvL2 802.1X is image-dependent.** Some IOSvL2 builds reject
  `authentication`/`dot1x` commands or behave inconsistently with EAPOL. If
  that happens, fall back to MAB-only for the dynamic VLAN demonstration: use
  `mab` on the user ports, add the client MACs to `radius/users` with VLAN 10
  or 20, and state in the report that EAP was not exercised. The VLAN, ACL,
  DHCP and RADIUS attribute design still works.
- **Packet Tracer cannot do this part.** Use GNS3 or EVE-NG.
- **The simulated Internet has no DNS or HTTPS service.** R2 answers ICMP and
  HTTP on 8.8.8.8. DNS and HTTPS tests prove the ACL permits via counters, not
  a successful application response. Add a DNS/HTTPS container to the server
  segment if the report needs those responses.
- **EAP-MD5 is lab-only.** It is not a production authentication method.
- **Anonymous MQTT.** The broker is intentionally open on the isolated IoT
  VLAN; add authentication/TLS for anything real.
- **The Docker server segment is host-dependent.** The macvlan/veth/bridge
  setup must exist on the GNS3 server host. A GNS3 VM needs the same setup
  inside the VM. The Cloud node must select `br-srv`.
- **Docker endpoint capabilities.** The client and sensor containers need
  `NET_ADMIN` (and `NET_RAW` for `wpa_supplicant -D wired`) to send EAPOL and,
  for sensors, to override the MAC. GNS3 normally grants these to Docker
  nodes; if your install does not, run the endpoint containers privileged or
  set the sensor MAC in the GNS3 node properties.
- **MAC format for MAB.** Cisco IOS normally sends `0200.0000.4001`. The
  `radius/users` file includes aliases for dotted, plain, hyphen and colon
  forms. If your image sends some other format (for example uppercase),
  `radiusd -X` shows the exact User-Name; add one alias with that string.
- **No high availability.** SW1 is a single distribution switch and R1 is a
  single gateway; this matches the brief but is not resilient.

## Troubleshooting quick reference

| Problem | Check | Fix |
|---|---|---|
| `verify_configs.py` fails | The message names the file/field | Fix the generated file, rerun |
| Compose cannot create the macvlan network | `ip link show srv-mac` | Run `radius/setup-server-bridge.sh`; ensure the parent is up |
| `br-srv` missing in GNS3 Cloud | GNS3 server host / VM | Run the setup script on the GNS3 server host; restart the GNS3 server |
| RADIUS container exits | `docker logs radius` | Validate config with `freeradius -CX`; check mounts |
| Switch cannot ping 192.168.50.10 | SW SVI, VLAN 99 trunk, R1 `MGMT_IN` counters | `show ip interface brief`; `show interfaces trunk`; `show access-lists` |
| Client gets no DHCP | `show authentication sessions`, `show dot1x all` | Confirm EAP success/fallback; `docker exec ... cat /tmp/wpa_supplicant.log` |
| Client authenticated in wrong VLAN | RADIUS debug Tunnel-Private-Group-Id | Check the `users` entry and `aaa authorization network default group CAMPUS-RADIUS` |
| Sensor not authorized | MAC mismatch/format | Set the GNS3 MAC or `SENSOR_MAC`; inspect `radiusd -X` User-Name |
| MQTT no messages | Sensor DHCP, IOT_IN 1883 permit, broker | `docker logs <sensor>`; `show access-lists`; `docker exec mqtt mosquitto_sub ...` |
| Trunk not forwarding VLAN | `show interfaces trunk` allowed list | Repaste the trunk block; check both ends |

## What to read next

- Build: [topology/gns3-build-steps.md](topology/gns3-build-steps.md)
- Design tables: [topology/topology.md](topology/topology.md)
- Tests: [tests/test-plan.md](tests/test-plan.md)
- Report structure: [report/report-outline.md](report/report-outline.md)
- RADIUS details: [radius/users](radius/users), [radius/clients.conf](radius/clients.conf)
