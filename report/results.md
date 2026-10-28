# Live Test Results

Run on the GNS3 3.1 project `campus-network` (16 nodes, 15 links) with
IOSv/IOSvL2 images, FreeRADIUS 3.2.3 and Mosquitto 2.x. Console output and
command transcripts are in `report/evidence/`.

## Summary sheet

| Test | Result | Evidence |
|---|---|---|
| T01 Build inventory | Pass | `T01-T20-r1.txt`, `T02-T03-T19-sw1.txt` |
| T02 VLAN membership | Pass | `T02-T03-T19-sw1.txt`, `T02-T19-sw2.txt`, `T02-T19-sw3.txt` |
| T03 Trunks | Pass | `T02-T03-T19-sw1.txt` |
| T04 DHCP/addressing | Pass | `T17-T18-r1-acl-nat.txt` (bindings), sensor/client `ip addr` |
| T05 staff1 VLAN 10 | Pass | `T05-T15-sw2-sessions.txt` |
| T06 student1/guest1 VLANs | Pass | `T05-T15-sw2-sessions.txt`, `T06-T07-sw3-sessions.txt` |
| T07 Sensor access VLAN 40 | Pass (port security; see limitation) | `T06-T07-sw3-sessions.txt`, `T16-mqtt-subscribe.txt` |
| T08 Move staff1 port | Not run | — |
| T09 Wrong password fallback | Pass | `T09-wrongpass.txt` |
| T10 RADIUS server-dead fallback | Pass | `T10-server-dead.txt` |
| T11 STAFF ACL matrix | Pass | `T11-staff-acl-matrix.txt` |
| T12 STUDENT ACL matrix | Pass | `T12-student-acl-matrix.txt` |
| T13 GUEST ACL matrix | Pass | `T13-guest-acl-matrix.txt` |
| T14 IOT ACL matrix | Pass | `T14-iot-acl-matrix.txt` |
| T15 MGMT RADIUS-only | Pass | `T05-T15-sw2-sessions.txt` |
| T16 MQTT all sensors | Pass | `T16-mqtt-subscribe.txt` |
| T17 ACL counters | Pass | `T17-T18-r1-acl-nat.txt` |
| T18 NAT/PAT | Pass | `T18-nat-live.txt` |
| T19 Spanning tree | Pass | `T02-T03-T19-sw1.txt` and SW2/SW3 files |
| T20 Config persistence | Partial | `T01-T20-r1.txt`, startup hostname checks on all five devices |

## Key observations

### 802.1X dynamic VLAN

- `SW2 Gi0/1` staff1: `dot1x Authc Success`, server policy `Vlan: 10`,
  lease 192.168.10.21.
- `SW2 Gi1/0` student1: `Authc Success`, `Vlan: 20`, lease 192.168.20.21.
- `SW3 Gi0/1` guest1: `Authc Success`, `Vlan: 30`, lease 192.168.30.21.
- `test aaa group CAMPUS-RADIUS staff1 Staff1Pass! legacy` returns
  `User was successfully authenticated`; `show radius statistics` shows 13
  auth responses, 0 timeouts.

### IoT access (platform limitation)

MAB is not usable on IOSvL2. With `mab` configured, the sensor's DHCP
discovers arrive on `Gi0/2` (link capture and interface counters both show
them), but `show authentication sessions` stays empty and the MAC table never
learns the address, because the 802.1X-controlled port discards data frames
until authorized. `debug mab all` / `debug authentication all` produce no
events.

The shipped config pins the sensor MAC with port security:

```
show port-security
Secure Port  MaxSecureAddr  CurrentAddr  SecurityViolation  Security Action
      Gi0/2              1            1                  0         Restrict
      Gi0/3              1            1                  0         Restrict
      Gi1/0              1            1                  0         Restrict
```

All three sensors then obtain 192.168.40.21-23 and publish to the broker.
RADIUS is still MAB-ready: `radtest 0200.0000.4001` returns Access-Accept with
`Tunnel-Private-Group-Id = "40"`.

### Failed-auth fallback (T09)

STAFF-PC2 was restarted with `wpa_supplicant-wrongpass.conf` on `Gi0/2`.
RADIUS rejected staff1 three times, SW2 logged `DOT1X-5-RESULT_OVERRIDE` and
applied `AUTH_FAIL_VLAN_Gi0/2` with `Vlan: 30`. A manual `udhcpc` on that
container obtained 192.168.30.22; HTTP to 8.8.8.8 returned 401 while pings to
192.168.10.21, 192.168.40.21 and 192.168.50.10 were dropped by the guest ACL.
The node was then restored to the staff2 profile and re-authenticated in VLAN
10 with 192.168.10.22.

### RADIUS server dead (T10)

The first attempt used `authentication event no-response`, which is the
*supplicant silent* event; it does not fire when RADIUS is unreachable. The
working configuration is `authentication event server dead action authorize
vlan 30`, plus `radius-server dead-criteria time 10 tries 2`.

With the RADIUS container stopped, the session cleared and a fresh EAPOL
exchange, SW2 logged `%RADIUS-4-RADIUS_DEAD` and the `Dead: ... count`
incremented. `Gi0/3` was authorized in VLAN 30 (`UNKNOWN Auth` session) and
STAFF-PC3 obtained 192.168.30.22. HTTP to 8.8.8.8 returned 401 (the simulated
Internet listener), while pings to 192.168.10.21 and TCP to 192.168.50.10/20
were dropped by `GUEST_IN`. After RADIUS restarted and the session was
cleared, the port returned to VLAN 10 and the client renewed 192.168.10.23.

Two operational notes:

- A *re-authentication* timeout does not move an already authorized port; IOS
  keeps the last known good session. T10 needs a fresh session (clear the
  session / bounce the link).
- The default dead criteria are slow (10 tries). The lab sets `time 10 tries 2`
  so the fallback happens in under a minute.

The same `server dead` policy is applied to every 802.1X user port on SW2 and
to the guest port on SW3.

### ACL and NAT

- `STAFF_IN` 58 matches, 0 denies; all eight staff rows succeed, including
  Internet HTTP 401 and ping to the SW1 SVI.
- `STUDENT_IN` and `GUEST_IN`: HTTP to 8.8.8.8 succeeds (401); pings to staff,
  IoT, MGMT, RADIUS and MQTT fail with 100% loss; deny counters increase.
- `IOT_IN`: 605 matches on `tcp ... 192.168.50.20 eq 1883`; Internet and
  internal pings fail; `nc -z 192.168.50.20 1883` succeeds.
- `MGMT_IN`: RADIUS permits match; echo replies for staff-initiated pings
  match; switch-originated pings and TCP SYNs are denied and logged.
- NAT: staff ICMP and student/guest TCP flows translate to `10.0.0.1`;
  IoT produces no translation because `IOT_IN` drops the packet first.

## Remaining work

- T08 (moving staff1 to another port) still needs a controlled link move.
- T20 is complete for `write memory` and startup-config checks; the optional
  reload was not performed.
