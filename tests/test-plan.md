# Test Plan and Evidence Capture

Every test below maps to a requirement in the assignment brief. The expected
results assume the configs in `configs/` and `radius/` are loaded unchanged.

## 0. Conventions

- Run commands on the device named in **Where**.
- Save evidence as `report/evidence/Txx-short-name.png` (screenshot) or
  `report/evidence/Txx-short-name.txt` (copied console output).
- Endpoint containers are GNS3 Docker nodes. Find their Docker names with:

  ```sh
  docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}'
  ```

  Then enter one with `docker exec -it <name> sh`. GNS3 may name containers
  differently from the node labels; match on the image name.
- `ping -c 3 -W 2 <ip>` works in both endpoint images (BusyBox).
- The `campus-client` image includes `curl`; the sensor image has BusyBox
  `wget`/`ping` but no `curl`.

The lab's "Internet" is R2's loopback `8.8.8.8`. R2 has an HTTP listener on
port 80; there is no DNS or HTTPS service on the simulated Internet. Tests for
DNS/HTTPS therefore verify the ACL permit counters and the absence of a
listener, not a successful application response. This is called out explicitly
where it applies.

## 1. Requirement traceability

| Brief requirement | Tests |
|---|---|
| 2 routers and 3 switches | T01 |
| STAFF VLAN with at least 3 devices | T02, T04, T05, T11 |
| STUDENT VLAN with at least 3 devices | T02, T04, T06, T12 |
| GUEST VLAN with 1 guest | T02, T04, T06, T13 |
| IoT VLAN with at least 3 real sensors | T02, T04, T07, T14, T16 |
| Firewall policy | T11, T12, T13, T14, T15, T17 |
| Dynamic VLAN assignment via RADIUS | T05, T06, T07, T08 |
| Unauthenticated/failed auth fallback | T09, T10 |
| MQTT sensor traffic and isolation | T14, T16 |
| NAT/PAT and Internet access | T11, T12, T13, T18 |

## 2. Baseline tests

### T01 - Build inventory and link status

**Where:** GNS3 workspace; R1, R2, SW1-SW3 consoles.

**Steps:**

1. Confirm the GNS3 project contains R1, R2, SW1, SW2, SW3, seven client
   containers, three sensor containers, SERVER-CLOUD (16 nodes).
2. Confirm the 15 links in `topology/gns3-build-steps.md` section 5.
3. On R1 and each switch: `show cdp neighbors` (or `show lldp neighbors` if
   CDP is disabled).
4. On each device: `show ip interface brief`.

**Expected:** R1 sees SW1 on g0/0 and R2 on g0/2; SW1 sees SW2/SW3; every
configured interface is `up/up`; R1 g0/1 is up toward the Cloud.

**Evidence:** GNS3 topology screenshot, `show cdp neighbors` from R1, SW1,
`show ip interface brief` from all five devices.

### T02 - VLAN database and access-port membership

**Where:** SW1, SW2, SW3.

**Steps:**

```text
show vlan brief
show vlan id 10
show vlan id 20
show vlan id 30
show vlan id 40
show vlan id 99
```

**Expected:**

| Switch | VLAN 10 ports | VLAN 20 ports | VLAN 30 ports | VLAN 40 ports |
|---|---|---|---|---|
| SW1 | none (trunks only) | none | none | none |
| SW2 | Gi0/1, Gi0/2, Gi0/3 | Gi1/0, Gi1/1, Gi1/2 | none | none |
| SW3 | none | none | Gi0/1 | Gi0/2, Gi0/3, Gi1/0 |

All five VLANs exist and have the names STAFF, STUDENT, GUEST, IOT, MGMT on
every switch. VLAN 99 has the management SVI.

> IOSvL2 has no `Gi0/4`-`Gi0/6`; student links 4-6 and the humidity sensor are
> on the `Gi1/x` port group. GNS3 adapter 4 maps to `Gi1/0`.
>
> After 802.1X succeeds, a port may be shown in the RADIUS-assigned VLAN
> instead of its initial access VLAN. Both should be the same VLAN in this
> design; T05/T06/T07 prove the assignment.

**Evidence:** `show vlan brief` from all three switches.

### T03 - Trunk status and allowed VLANs

**Where:** SW1, SW2, SW3.

**Steps:**

```text
show interfaces trunk
show interfaces GigabitEthernet0/0 switchport
```

**Expected:** SW1 has three trunk ports (g0/0, g0/1, g0/2); SW2 and SW3 each
have g0/0. Every trunk is `trunking`, `802.1q`, forwarding, and its allowed
VLAN list is exactly `10,20,30,40,99`. Native VLAN is 1. No access port appears
as a trunk.

**Evidence:** `show interfaces trunk` from each switch.

### T04 - Addressing and DHCP leases

**Where:** R1 and endpoints.

**Steps:**

1. On R1: `show ip interface brief`, `show ip dhcp binding`,
   `show ip dhcp pool`.
2. On each client/sensor: `ip addr show eth0`, `ip route`.
3. On R1: `show ip arp`.

**Expected:** R1 has 192.168.10.1, .20.1, .30.1, .40.1, .99.1, .50.1 and
10.0.0.1. Each endpoint has an address in its VLAN's `.21-.254` range with the
matching default gateway and DNS 8.8.8.8. There are at least three STAFF
leases, three STUDENT leases, one GUEST lease and three IOT leases.

**Evidence:** `show ip dhcp binding` (R1), `ip addr`/`ip route` from one
endpoint per VLAN, `show ip arp`.

## 3. RADIUS dynamic VLAN tests

### T05 - staff1 is dynamically placed in VLAN 10

**Where:** STAFF-PC1, SW2, RADIUS logs.

**Preconditions:** STAFF-PC1 uses `wpa_supplicant-staff1.conf`; RADIUS is
running; SW2 g0/1 is connected.

**Steps:**

1. Reconnect/restart STAFF-PC1.
2. On SW2:

   ```text
   show authentication sessions
   show authentication sessions interface GigabitEthernet0/1 details
   show dot1x interface GigabitEthernet0/1 details
   ```

3. On the Docker host, capture the RADIUS exchange in debug mode. Stop and
   remove the compose RADIUS container (this releases 192.168.50.10), start a
   debug instance on the same macvlan network, then trigger a reconnect:

   ```sh
   cd network-project/radius
   docker compose stop radius
   docker compose rm -f radius
   docker network ls | grep campus-network_server
   docker run --rm --network campus-network_server --ip 192.168.50.10 \
     -v "$PWD/clients.conf:/etc/freeradius/clients.conf:ro" \
     -v "$PWD/users:/etc/freeradius/mods-config/files/authorize:ro" \
     freeradius/freeradius-server:3.2.3 freeradius -X
   ```

   Press Ctrl-C when the exchange is captured, then restore the service with
   `docker compose up -d radius`. (The network name may be
   `campus-network_server` or `network-project_server` depending on the
   Compose project name.)

**Expected:** `show authentication sessions` shows interface g0/1, method
`dot1x`, status `Auth`, and **VLAN 10**. The RADIUS debug shows an
`Access-Accept` containing `Tunnel-Type = VLAN`,
`Tunnel-Medium-Type = IEEE-802`, and `Tunnel-Private-Group-Id = "10"`.
`show dot1x ... details` shows the supplicant MAC and `Authorized`.

**Evidence:** `show authentication sessions ... details`, the RADIUS
`Access-Accept` block, and the client's DHCP address in 192.168.10.0/24.

### T06 - student1 -> VLAN 20; guest1 -> VLAN 30

**Where:** STUDENT-PC1, GUEST-PC1, SW2 Gi1/0, SW3 Gi0/1.

**Steps:**

1. Reconnect STUDENT-PC1 with `wpa_supplicant-student1.conf`.
2. On SW2: `show authentication sessions interface GigabitEthernet1/0 details`.
3. Reconnect GUEST-PC1 with `wpa_supplicant-guest1.conf`.
4. On SW3: `show authentication sessions interface GigabitEthernet0/1 details`.

**Expected:** STUDENT-PC1 is authorized in VLAN 20 with a 192.168.20.x lease;
GUEST-PC1 is authorized in VLAN 30 with a 192.168.30.x lease. The RADIUS
Access-Accept for each contains the matching `Tunnel-Private-Group-Id`.

**Evidence:** Two session outputs, two DHCP addresses, RADIUS debug excerpts.

### T07 - Sensor access -> VLAN 40

**Where:** SW3 Gi0/2, Gi0/3, Gi1/0; RADIUS logs.

> **Platform note:** IOSvL2 accepts the `mab` command but never creates an
> authentication session, so a MAB-configured port stays unauthorized and the
> sensor cannot DHCP. The shipped `configs/SW3.cfg` pins each sensor MAC with
> port security instead. Both variants are checked below; on Catalyst hardware
> run the MAB variant, on IOSvL2 run the port-security variant.

**Steps (IOSvL2 / shipped config):**

1. Confirm each sensor's MAC:

   ```sh
   docker ps --format '{{.Names}} {{.Image}}'
   docker exec <sensor-container> cat /sys/class/net/eth0/address
   ```

2. On SW3:

   ```text
   show port-security
   show port-security interface GigabitEthernet0/2
   show mac address-table | include 0200.0000.40
   ```

3. Confirm the sensors have 192.168.40.x leases (`ip addr show eth0` in each
   container) and publish to the broker (T16).

**Expected:** Each IoT port is `Secure-up`, maximum 1 address, `Restrict`,
with `Last Source Address:Vlan` equal to the sensor MAC in VLAN 40. The MAC
table shows the three addresses as `STATIC` in VLAN 40. Each sensor has a
192.168.40.x lease.

**Steps (hardware MAB variant):**

1. Replace the port-security lines on each IoT port with
   `authentication order mab`, `authentication port-control auto`, `mab` and
   `dot1x pae authenticator`.
2. `show authentication sessions interface GigabitEthernet0/2 details` shows
   method `mab`, status `Auth`, VLAN 40.
3. In RADIUS debug, the Access-Request User-Name is `0200.0000.4001`
   (or one of the aliases in `radius/users`), and the Access-Accept contains
   `Tunnel-Private-Group-Id = "40"`.

**Evidence:** `report/evidence/T06-T07-sw3-sessions.txt` (port security,
sessions, MAC table), sensor leases, and `T16-mqtt-subscribe.txt`.

### T08 - Moving staff1 to another port keeps VLAN 10

**Where:** SW2 g0/1 and g0/3.

**Steps:**

1. With STAFF-PC1 authenticated on g0/1, delete the GNS3 link from SW2 g0/1.
2. Connect STAFF-PC1 itself to SW2 g0/3 (move its link), or use a spare client
   configured with the staff1 profile. Do not use STAFF-PC3's staff3 profile
   for this test.
3. If the port does not restart authentication, on SW2:

   ```text
   interface GigabitEthernet0/3
    shutdown
    no shutdown
   ```

4. Run `show authentication sessions interface GigabitEthernet0/3 details`.

**Expected:** The new port authenticates the same staff1 identity and is
authorized in VLAN 10 with a 192.168.10.x address. The old port has no active
session. This proves the VLAN comes from RADIUS, not from the port's static
access VLAN (both staff ports start in VLAN 10, so also show the RADIUS
Access-Accept for the new session).

**Evidence:** Session output on g0/3, DHCP address, RADIUS debug for the new
NAS port.

### T09 - Wrong password -> guest fallback VLAN 30

**Where:** a spare client using `wpa_supplicant-wrongpass.conf`, SW2, RADIUS.

**Steps:**

1. Connect the spare client to a staff port (for example g0/2) with the
   wrong-password profile. Build/use a client image whose `WPA_CONF` points at
   `/etc/wpa_supplicant/wpa_supplicant-wrongpass.conf`.
2. Watch `show authentication sessions interface GigabitEthernet0/2 details`
   and the RADIUS debug.
3. Check the client's DHCP address: `ip addr show eth0`.

**Expected:** RADIUS returns `Access-Reject` for staff1. SW2 applies
`authentication event fail action authorize vlan 30`; the port is authorized
in **VLAN 30**, and the client gets a 192.168.30.x address. It can reach the
Internet but cannot ping 192.168.10.x, 192.168.40.x, 192.168.50.x or
192.168.99.x (guest ACL).

**Evidence:** Access-Reject, session output showing VLAN 30, guest DHCP lease,
failed internal pings.

### T10 - RADIUS server dead -> guest fallback VLAN 30

**Where:** STAFF-PC3 on SW2 `Gi0/3`, Docker host.

**Steps:**

1. Stop RADIUS: `docker stop radius` (or `docker compose stop radius`).
2. Force a fresh authentication attempt. Re-authentication on an already
   authorized port does not test this path, because IOS keeps the last known
   good session when a *re-auth* times out. Clear the session and restart
   EAPOL instead:
   - SW2: `clear authentication sessions interface GigabitEthernet0/3`
   - client: `wpa_cli -i eth0 reassociate`
     (or stop/start the endpoint in GNS3)
3. Wait for the dead criteria: `radius-server dead-criteria time 10 tries 2`
   with `timeout 5` / `retransmit 3` marks the server dead in roughly 30-60s.
4. Check `show aaa servers` (`Dead: ... count`), `show logging` for
   `%RADIUS-4-RADIUS_DEAD`, and
   `show interface GigabitEthernet0/3 switchport` (`Access Mode VLAN: 30`).
5. Renew DHCP on the client and test the guest ACL.
6. Restart RADIUS (`docker start radius`), clear the session and reassociate;
   confirm the port returns to VLAN 10.

**Expected:** While RADIUS is unreachable, the port is authorized in **VLAN 30**
by `authentication event server dead action authorize vlan 30`, and the client
gets a 192.168.30.x lease. As in T09, HTTP to 8.8.8.8 succeeds while staff,
RADIUS, MQTT and MGMT destinations are blocked by `GUEST_IN`.

**Note:** `authentication event no-response` is about a silent *supplicant*,
not a silent RADIUS server; it is not the right event for a RADIUS outage.
`authentication event server dead` is the working fallback on this image.

**Evidence:** `T10-server-dead.txt` - dead counter, `RADIUS_DEAD` syslog,
session in VLAN 30, 192.168.30.22 lease, HTTP 401, blocked internal probes.

## 4. Firewall policy tests

Run each row from the named endpoint. Use `ping` for ICMP rows and `curl` for
HTTP rows. A "pass" means the expected protocol succeeds; "fail" means it is
blocked by R1, not merely that an application is absent. For DNS and HTTPS,
there is no service on the simulated Internet, so the pass criterion is the
ACL permit counter incrementing (T17) rather than an application response.

### T11 - STAFF ACL matrix

**Where:** STAFF-PC1.

| # | Destination | Command | Expected |
|---|---|---|---|
| 1 | 8.8.8.8 | `ping -c 3 8.8.8.8` | Pass (NAT to Internet) |
| 2 | 8.8.8.8:80 | `curl -sS -m 5 -o /dev/null -w '%{http_code}\n' http://8.8.8.8/` | Pass (HTTP code, 401 is acceptable) |
| 3 | 192.168.50.10 | `ping -c 3 192.168.50.10` | Pass |
| 4 | 192.168.50.20 | `ping -c 3 192.168.50.20` | Pass |
| 5 | 192.168.20.21 | `ping -c 3 192.168.20.21` | Pass |
| 6 | 192.168.40.21 | `ping -c 3 192.168.40.21` | Pass |
| 7 | 192.168.99.11 | `ping -c 3 192.168.99.11` | Pass |
| 8 | 192.168.30.21 | `ping -c 3 192.168.30.21` | Pass |

If a student/IoT/guest endpoint is not at `.21`, use its actual DHCP address
from T04. Staff has no deny rules, so all rows should succeed.

**Evidence:** Command output for all rows, `show access-lists` on R1 showing
STAFF_IN permit counters.

### T12 - STUDENT ACL matrix

**Where:** STUDENT-PC1.

| # | Destination | Command | Expected |
|---|---|---|---|
| 1 | 8.8.8.8 | `ping -c 3 8.8.8.8` | Fail (ICMP is not in the student allow-list; use HTTP row 2) |
| 2 | 8.8.8.8:80 | `curl -sS -m 5 -o /dev/null -w '%{http_code}\n' http://8.8.8.8/` | Pass (HTTP code) |
| 3 | 8.8.8.8:443 | `curl -k -sS -m 5 https://8.8.8.8/` | ACL permits; no HTTPS listener, so connection fails. Confirm STUDENT_IN permit counter increments. |
| 4 | 8.8.8.8:53 | `nslookup example.com 8.8.8.8` | ACL permits; no DNS listener, so timeout. Confirm permit counter increments. |
| 5 | 192.168.10.21 | `ping -c 3 192.168.10.21` | Fail (STAFF denied) |
| 6 | 192.168.40.21 | `ping -c 3 192.168.40.21` | Fail (IOT denied) |
| 7 | 192.168.99.11 | `ping -c 3 192.168.99.11` | Fail (MGMT denied) |
| 8 | 192.168.50.10 | `ping -c 3 192.168.50.10` | Fail (SERVER denied) |
| 9 | 192.168.50.20 | `ping -c 3 192.168.50.20` | Fail (SERVER/MQTT denied) |

> A ping between two hosts in VLAN 20 (for example student1 to student2) is
> **not** in this matrix. That traffic is switched by SW2 and never reaches
> R1's `STUDENT_IN` ACL, so it succeeds. The ACLs enforce inter-VLAN policy;
> same-VLAN peer isolation would require private VLANs or `switchport
> protected` on the access ports, which is outside this brief.

**Evidence:** Output for all rows; R1 `show access-lists` STUDENT_IN deny
counters for rows 5-9.

### T13 - GUEST ACL matrix

**Where:** GUEST-PC1.

| # | Destination | Command | Expected |
|---|---|---|---|
| 1 | 8.8.8.8 | `ping -c 3 8.8.8.8` | Fail (ICMP is not in the guest allow-list) |
| 2 | 8.8.8.8:80 | `curl -sS -m 5 -o /dev/null -w '%{http_code}\n' http://8.8.8.8/` | Pass (HTTP code) |
| 3 | 192.168.10.21 | `ping -c 3 192.168.10.21` | Fail |
| 4 | 192.168.20.21 | `ping -c 3 192.168.20.21` | Fail |
| 5 | 192.168.40.21 | `ping -c 3 192.168.40.21` | Fail |
| 6 | 192.168.50.10 | `ping -c 3 192.168.50.10` | Fail |
| 7 | 192.168.99.11 | `ping -c 3 192.168.99.11` | Fail |

**Evidence:** Output for all rows; GUEST_IN deny counters.

### T14 - IOT ACL matrix

**Where:** each sensor container (SENSOR-TEMP/MOTION/HUMIDITY), SW3.

| # | Destination | Command | Expected |
|---|---|---|---|
| 1 | 192.168.50.20:1883 | MQTT publish is automatic; verify with T16 | Pass |
| 2 | 8.8.8.8 | `ping -c 3 8.8.8.8` | Fail (Internet denied) |
| 3 | 8.8.8.8:80 | `wget -T 5 -O /dev/null http://8.8.8.8/` | Fail (Internet denied) |
| 4 | 8.8.8.8:53 | `nslookup example.com 8.8.8.8` | ACL permits DNS; no DNS listener, so timeout. Confirm IOT_IN permit counter. |
| 5 | 192.168.50.10 | `ping -c 3 192.168.50.10` | Fail (RADIUS not an IoT destination) |
| 6 | 192.168.50.10:1812 | `nc -z -w 3 192.168.50.10 1812` (if nc exists) or rely on ACL counter | Fail |
| 7 | 192.168.10.21 | `ping -c 3 192.168.10.21` | Fail |
| 8 | 192.168.20.21 | `ping -c 3 192.168.20.21` | Fail |
| 9 | 192.168.40.1 | `ping -c 3 192.168.40.1` | Fail (internal/gateway; IOT_IN denies) |

**Evidence:** `ping`/`wget` output from each sensor, `show access-lists`
IOT_IN counters showing 1883 permits and deny counters.

### T15 - MGMT ACL and RADIUS-only access

**Where:** SW2 (MGMT VLAN 99), R1.

**Steps:**

1. On SW2, test RADIUS reachability:

   ```text
   test aaa group CAMPUS-RADIUS staff1 Staff1Pass! legacy
   show radius statistics
   ```

2. Try to reach the Internet and MQTT from the switch's management SVI:

   ```text
   ping 8.8.8.8
   ping 192.168.50.20
   ```

3. Try to ping a staff endpoint from SW2:

   ```text
   ping 192.168.10.21
   ```

**Expected:** `test aaa` reports successful authentication (or at least a
RADIUS Access-Accept and non-zero auth counters); `show radius statistics`
shows requests/responses. Pings to 8.8.8.8, 192.168.50.20 and 192.168.10.21
fail (packets from VLAN 99 are denied by `MGMT_IN`). RADIUS still works because
UDP 1812/1813 to 192.168.50.10 is explicitly permitted.

> `MGMT_IN` also permits ICMP echo replies and established TCP so that staff
> (which `STAFF_IN` allows to reach MGMT) can ping or SSH to the switch SVIs.
> Switch-originated echo requests and TCP SYNs do not match those entries and
> are still denied, which is what this test checks.
>
> If `test aaa` is unsupported on your IOSvL2 image, the live 802.1X tests
> (T05-T09) already prove MGMT-to-RADIUS reachability; capture
> `show radius statistics` instead.

**Evidence:** `test aaa` output, `show radius statistics`, failed ping output,
MGMT_IN counters.

## 5. MQTT and sensor tests

### T16 - All three sensors publish to the broker

**Where:** Docker host, MQTT container.

**Steps:**

1. Confirm all three sensor containers are running and have 192.168.40.x
   addresses.
2. Subscribe for at least 9 messages (3 sensors x 3 samples at 5-second
   intervals):

   ```sh
   docker exec -it mqtt mosquitto_sub \
     -h 127.0.0.1 -t 'campus/iot/#' -v -C 9
   ```

3. Save the output. Each line should be `campus/iot/<id> {"id":...}`.

**Expected:** Messages from `temp-01`, `motion-01` and `humidity-01` arrive
within 30 seconds. Payloads are JSON with `id`, `type`, `value`, `timestamp`;
types are `temperature`, `motion`, `humidity`; values are plausible (18-26,
0/1, 35-65). No sensor can ping 8.8.8.8 (T14 row 2), proving the IoT ACL does
not accidentally permit general Internet access.

**Evidence:** `mosquitto_sub` output with at least 9 lines, sensor logs,
sensor `ip addr`, failed Internet ping from one sensor.

### T17 - ACL hit counters

**Where:** R1.

**Steps:**

1. Before tests: `clear ip access-list counters` (or note the current counts).
2. Run the T11-T15 matrix.
3. `show access-lists`.
4. `show logging | include ACL|denied` (the ACL entries use `log`).

**Expected:** `STAFF_IN` has high permit counts and no denies; `STUDENT_IN`,
`GUEST_IN`, `IOT_IN` and `MGMT_IN` each show both permits for allowed traffic
and nonzero denies for the blocked rows. The final `deny ip any any log` entry
has a nonzero count when a test hit an unlisted destination. Log entries show
the source/destination and the ACL name.

**Evidence:** `show access-lists` before/after, `show logging` excerpt.

### T18 - NAT/PAT

**Where:** R1, STAFF-PC1/STUDENT-PC1/GUEST-PC1.

**Steps:**

1. From STAFF-PC1, `ping -c 3 8.8.8.8`.
2. From STUDENT-PC1 and GUEST-PC1, use
   `curl -sS -m 5 -o /dev/null -w '%{http_code}\n' http://8.8.8.8/`
   (their ACLs do not permit ICMP).
3. On R1: `show ip nat translations`, `show ip nat statistics`.
4. From an IoT sensor, attempt `ping 8.8.8.8`, then check NAT again.

**Expected:** Staff, student and guest flows appear as translations from
10.0.0.1 to 8.8.8.8; IoT produces no translation because its ACL drops the
packet before NAT. Server/MGMT traffic is not translated.

**Evidence:** NAT translation table, NAT statistics, IoT failed ping.

## 6. Supporting tests

### T19 - Spanning tree

**Where:** SW1, SW2, SW3.

**Steps:**

```text
show spanning-tree vlan 10
show spanning-tree vlan 20
show spanning-tree vlan 30
show spanning-tree vlan 40
show spanning-tree vlan 99
show spanning-tree summary
```

**Expected:** SW1 is root for all five VLANs; SW2/SW3 reach SW1 through a root
port on g0/0; no access port is blocking; rapid-pvst is active.

**Evidence:** `show spanning-tree` output from each switch.

### T20 - Configuration persistence

**Where:** all five Cisco devices.

**Steps:**

1. `write memory` on each device.
2. `show startup-config | include hostname|radius|access-list|vlan`.
3. Optional: `reload` one switch, wait for boot, and confirm
   `show authentication sessions` and `show vlan brief` after reconnecting a
   client.

**Expected:** Startup config matches the running config; VLANs, ACLs, RADIUS
key and 802.1X settings survive a reload.

**Evidence:** `show startup-config` excerpts, post-reload session output.

## 7. Pass/fail summary sheet

Copy this into the report and fill it in:

| Test | Result (Pass/Fail) | Evidence file |
|---|---|---|
| T01 Build inventory | | |
| T02 VLAN membership | | |
| T03 Trunks | | |
| T04 DHCP/addressing | | |
| T05 staff1 VLAN 10 | | |
| T06 student1/guest1 VLANs | | |
| T07 Sensor MAB VLAN 40 | | |
| T08 Move staff1 port | | |
| T09 Wrong password fallback | | |
| T10 RADIUS no-response fallback | | |
| T11 STAFF ACL matrix | | |
| T12 STUDENT ACL matrix | | |
| T13 GUEST ACL matrix | | |
| T14 IOT ACL matrix | | |
| T15 MGMT RADIUS-only | | |
| T16 MQTT all sensors | | |
| T17 ACL counters | | |
| T18 NAT/PAT | | |
| T19 Spanning tree | | |
| T20 Persistence | | |
