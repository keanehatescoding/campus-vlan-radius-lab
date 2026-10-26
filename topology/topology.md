# Campus Network - Topology and Addressing

This is the build reference for the GNS3 project. The click-by-click procedure
is in [gns3-build-steps.md](gns3-build-steps.md); the firewall/RADIUS policy is
implemented in `configs/` and `radius/`.

## 1. Logical diagram

```
                              8.8.8.8/32 (Loopback0)
                                      [R2]
                                       | 10.0.0.0/30
                                       | R2 .2 / R1 .1
                                       |
                          [R1  Gateway / Firewall / DHCP / PAT]
                         / g0/0 (802.1Q trunk)          g0/1
                        /                                \  192.168.50.0/24
                  [SW1  Distribution / STP root]          [ SERVER SEGMENT ]
                  / g0/1                  \ g0/2            RADIUS 192.168.50.10
                 /                          \               MQTT   192.168.50.20
            [SW2  Access]                [SW3  Access]      (Docker compose,
            /     |      \                |     |    \      reached via GNS3
       g0/1   g0/2   g0/3  g0/4-6       g0/1  g0/2-4       Cloud on br-srv)
        |      |      |     |             |      |
   STAFF-PC1 PC2  PC3  STUDENT-PC1..3  GUEST  SENSOR-TEMP
                                                  SENSOR-MOTION
                                                  SENSOR-HUMIDITY
```

VLANs are carried as 802.1Q tags on all inter-switch and R1-SW1 links:
`10,20,30,40,99`. The server segment is a separate routed subnet; it is not a
VLAN on the switch trunk.

## 2. Node inventory

| Node | GNS3 type | Role | Notes |
|---|---|---|---|
| R1 | Cisco IOSv | Campus gateway, DHCP, NAT/PAT, ACL firewall | 3 interfaces used: g0/0, g0/1, g0/2 |
| R2 | Cisco IOSv | Simulated ISP / Internet | Loopback0 = 8.8.8.8/32 |
| SW1 | Cisco IOSvL2 | Distribution, rapid-PVST root | 3 trunk ports, no access ports |
| SW2 | Cisco IOSvL2 | STAFF + STUDENT access | 802.1X authenticator |
| SW3 | Cisco IOSvL2 | GUEST + IoT access | 802.1X + MAB authenticator |
| STAFF-PC1..3 | Docker `campus-client:1.0` | Staff endpoints | wpa_supplicant, EAP-MD5 |
| STUDENT-PC1..3 | Docker `campus-client:1.0` | Student endpoints | wpa_supplicant, EAP-MD5 |
| GUEST-PC1 | Docker `campus-client:1.0` | Guest endpoint | wpa_supplicant, EAP-MD5 |
| SENSOR-TEMP | Docker `campus-sensor:1.0` | Temperature sensor | MAB, MAC 0200.0000.4001 |
| SENSOR-MOTION | Docker `campus-sensor:1.0` | Motion sensor | MAB, MAC 0200.0000.4002 |
| SENSOR-HUMIDITY | Docker `campus-sensor:1.0` | Humidity sensor | MAB, MAC 0200.0000.4003 |
| SERVER-CLOUD | GNS3 Cloud | Link to `br-srv` | R1 g0/1 attaches here |
| RADIUS | Docker compose | FreeRADIUS 3.2.3 | 192.168.50.10 |
| MQTT | Docker compose | Eclipse Mosquitto 2.x | 192.168.50.20 |

The RADIUS and MQTT containers are not GNS3 nodes. They run on the Docker host
and are reached through the SERVER-CLOUD link. See `radius/docker-compose.yml`
and `radius/setup-server-bridge.sh`.

## 3. Port map

| Link | Ports | Mode / VLAN | Endpoint |
|---|---|---|---|
| R1 <-> SW1 | R1 g0/0 <-> SW1 g0/0 | 802.1Q trunk, VLANs 10,20,30,40,99 | Router-on-a-stick |
| SW1 <-> SW2 | SW1 g0/1 <-> SW2 g0/0 | 802.1Q trunk | Distribution to access |
| SW1 <-> SW3 | SW1 g0/2 <-> SW3 g0/0 | 802.1Q trunk | Distribution to access |
| SW2 staff 1 | SW2 g0/1 | Access VLAN 10, 802.1X | STAFF-PC1 |
| SW2 staff 2 | SW2 g0/2 | Access VLAN 10, 802.1X | STAFF-PC2 |
| SW2 staff 3 | SW2 g0/3 | Access VLAN 10, 802.1X | STAFF-PC3 |
| SW2 student 1 | SW2 g0/4 | Access VLAN 20, 802.1X | STUDENT-PC1 |
| SW2 student 2 | SW2 g0/5 | Access VLAN 20, 802.1X | STUDENT-PC2 |
| SW2 student 3 | SW2 g0/6 | Access VLAN 20, 802.1X | STUDENT-PC3 |
| SW3 guest | SW3 g0/1 | Access VLAN 30, 802.1X | GUEST-PC1 |
| SW3 IoT temp | SW3 g0/2 | Access VLAN 40, MAB | SENSOR-TEMP |
| SW3 IoT motion | SW3 g0/3 | Access VLAN 40, MAB | SENSOR-MOTION |
| SW3 IoT humidity | SW3 g0/4 | Access VLAN 40, MAB | SENSOR-HUMIDITY |
| R1 <-> server | R1 g0/1 <-> SERVER-CLOUD (`br-srv`) | Routed 192.168.50.0/24 | RADIUS + MQTT |
| R1 <-> R2 | R1 g0/2 <-> R2 g0/0 | Routed 10.0.0.0/30 | Simulated ISP |

On SW2 and SW3 the initial `switchport access vlan` is the "pre-auth" VLAN:
10 for staff ports, 20 for student ports, 30 for guest, 40 for IoT. After a
successful RADIUS exchange the switch moves the port to the VLAN returned in
`Tunnel-Private-Group-Id` (normally the same VLAN, which makes the assignment
visible in `show authentication sessions`). A failed/no-response 802.1X user
port is authorized into VLAN 30 (guest fallback). IoT MAB failures stay
unauthorized by design.

## 4. Addressing

| VLAN | Name | Subnet | Gateway | DHCP pool | Notes |
|---|---|---|---|---|---|
| 10 | STAFF | 192.168.10.0/24 | 192.168.10.1 | .21-.254 | 3 Docker clients, full access |
| 20 | STUDENT | 192.168.20.0/24 | 192.168.20.1 | .21-.254 | 3 Docker clients, Internet only |
| 30 | GUEST | 192.168.30.0/24 | 192.168.30.1 | .21-.254 | 1 Docker client + fallback |
| 40 | IOT | 192.168.40.0/24 | 192.168.40.1 | .21-.254 | 3 Docker sensors, MQTT only |
| 99 | MGMT | 192.168.99.0/24 | 192.168.99.1 | static | SW1 .11, SW2 .12, SW3 .13 |
| - | SERVER | 192.168.50.0/24 | 192.168.50.1 | static | RADIUS .10, MQTT .20 |
| - | R1-R2 | 10.0.0.0/30 | - | - | R1 .1, R2 .2 |
| - | Internet sim | 8.8.8.8/32 | - | - | R2 Loopback0 |

DHCP is served by R1 on the VLAN 10/20/30/40 subinterfaces. Each pool excludes
`.1` through `.20`; clients receive `.21` and above. DNS option is `8.8.8.8`
(the simulated Internet host); see the test plan for the DNS caveat.

### Management addresses

| Device | Interface | Address | Default gateway |
|---|---|---|---|
| R1 | g0/0.99 | 192.168.99.1/24 | - |
| SW1 | Vlan99 | 192.168.99.11/24 | 192.168.99.1 |
| SW2 | Vlan99 | 192.168.99.12/24 | 192.168.99.1 |
| SW3 | Vlan99 | 192.168.99.13/24 | 192.168.99.1 |

### Fixed sensor MACs

| Sensor | MAC | RADIUS user | VLAN |
|---|---|---|---|
| Temperature | 0200.0000.4001 | 0200.0000.4001 | 40 |
| Motion | 0200.0000.4002 | 0200.0000.4002 | 40 |
| Humidity | 0200.0000.4003 | 0200.0000.4003 | 40 |

These MACs must be set on the GNS3 Docker nodes (or via `SENSOR_MAC`) so MAB
matches `radius/users`. `radius/users` includes dotted, plain, hyphen and colon
aliases; if the switch sends a format not listed there, add one alias as
described in the README.

## 5. VLAN/STP design

- `spanning-tree mode rapid-pvst` on all switches.
- SW1 is `root primary` for VLANs 10,20,30,40,99.
- SW2/SW3 are access switches; all their uplinks are trunks.
- Access ports use `spanning-tree portfast`.
- Native VLAN is left at VLAN 1 on the trunks; only tagged VLANs 10,20,30,40,99
  are allowed. No user traffic is placed in VLAN 1.

## 6. Server segment wiring

The Docker segment is deliberately separated from the switch fabric:

```
R1 g0/1 --- GNS3 Cloud (br-srv)
                        |
                  srv-br (veth peer)
                        |
                  srv-mac (macvlan parent)
                   /          \
             radius .10     mqtt .20
```

`radius/setup-server-bridge.sh` creates the bridge and veth pair. The compose
network uses `srv-mac` as its macvlan parent and `192.168.50.1` as the
containers' gateway, which is R1. This keeps R1 as the only router/firewall for
the server segment and avoids putting a Docker bridge IP on 192.168.50.1.

## 7. Traffic policy summary

| Source VLAN | Allowed | Denied |
|---|---|---|
| STAFF (10) | Everything: Internet, SERVER, STUDENT, IOT, MGMT | none |
| STUDENT (20) | DHCP, gateway echo, Internet DNS/HTTP/HTTPS | all RFC1918 reached through R1 (STAFF, IOT, MGMT, SERVER) |
| GUEST (30) | DHCP, gateway echo, Internet DNS/HTTP/HTTPS | all RFC1918 |
| IOT (40) | DHCP, DNS to 8.8.8.8, MQTT tcp/1883 to 192.168.50.20 | Internet, all other internal ranges |
| MGMT (99) | RADIUS udp/1812,1813 to 192.168.50.10 (replies are routed out, not filtered) | everything else |

The ACLs are named extended ACLs on R1: `STAFF_IN`, `STUDENT_IN`, `GUEST_IN`,
`IOT_IN`, `MGMT_IN`, each applied inbound on its VLAN subinterface and ending
with `deny ip any any log`. They filter only traffic that is routed through
R1; two hosts in the same VLAN exchange frames through the access switch and
do not hit these ACLs. Add private VLANs or `switchport protected` if
same-VLAN peer isolation is required.
