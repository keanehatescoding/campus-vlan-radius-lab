# GNS3 Build Steps

These are click-by-click steps for GNS3 2.2.x on Linux. GNS3 is not run by the
person who generated this repo, so treat the GUI labels as a guide: wording
changes slightly between GNS3 releases. The configs and topology are the
authoritative parts.

## 0. What you must supply

The repo does **not** contain Cisco images. You must obtain them yourself and
comply with Cisco's licence terms:

- A Cisco **IOSv** image for R1 and R2 (IOS 15.x, at least 3 GigabitEthernet
  interfaces). Import it as a QEMU IOSv template.
- A Cisco **IOSvL2** image for SW1, SW2 and SW3 (IOS 15.2, at least 8
  GigabitEthernet interfaces, 802.1X capable). Import it as a QEMU IOSvL2
  template and mark it as an Ethernet switch.

Do not rename the interfaces in the configs. The configs assume
`GigabitEthernet0/0`, `0/1`, ... on both routers and switches. If your image
numbers ports differently (for example `Gi1/0`), use search/replace in the
configs before pasting, or adapt the port map.

You also need:

- Docker Engine with Compose v2, on the same Linux host as the GNS3 server (or
  inside the GNS3 VM if that is where the server runs).
- The `campus-client:1.0` and `campus-sensor:1.0` images built in step 2.
- Internet access only for the first image pulls/builds. The lab itself uses
  the simulated 8.8.8.8 host on R2.

## 1. Prepare the Docker server segment first

The RADIUS and MQTT containers must be running before the switches boot,
otherwise the first 802.1X attempts time out (the switches will use the guest
fallback, but the demonstration is cleaner if RADIUS is ready).

```sh
cd network-project/radius
chmod +x setup-server-bridge.sh
./setup-server-bridge.sh
docker compose up -d
docker compose ps
docker logs radius --tail 30
```

Wait for the FreeRADIUS log line `Ready to process requests`. If you see
`Error binding to port` or a config error, stop here and fix it before building
the topology. `docker logs mqtt` should show `mosquitto version ... running`.

The setup script creates:

- `br-srv`: the Linux bridge that the GNS3 Cloud node attaches to.
- `srv-mac` / `srv-br`: a veth pair; `srv-mac` is the macvlan parent used by
  Compose, `srv-br` is enslaved to `br-srv`.

If your GNS3 server is in a **GNS3 VM**, run these commands inside that VM.
The Cloud node must be able to see `br-srv` on the GNS3 server host. A local
GNS3 server on the same Linux host is the simplest setup.

## 2. Build the endpoint images

From the repo root:

```sh
docker build -t campus-client:1.0 endpoints/client
docker build -t campus-sensor:1.0 endpoints/sensor
docker images | grep campus
```

`campus-client` contains all seven supplicant profiles. The profile is selected
at runtime with `WPA_CONF`; do not build a separate image per user.

## 3. Create the GNS3 project and templates

1. Start GNS3 and create a new blank project named `campus-network`.
2. Open **Edit > Preferences > QEMU > IOS routers** (or the equivalent
   template manager) and import your IOSv image. Name the template `IOSv`.
   Set RAM to at least 512 MB. Set **Adapters** to **3** (R1 needs g0/0, g0/1,
   g0/2).
3. Import your IOSvL2 image as template `IOSvL2`. Set RAM to at least 512 MB.
   Set **Adapters** to at least **8** (SW2 uses g0/0 through g0/6). Mark the
   template as an Ethernet switch if GNS3 offers that option.
4. Open **Edit > Preferences > Docker > Docker containers > New**. Create:
   - `campus-client`: image `campus-client:1.0`, 1 adapter.
   - `campus-sensor`: image `campus-sensor:1.0`, 1 adapter.
   Accept the default console settings unless your GNS3 version requires a
   specific console type. Both images are intentionally long-running.
5. Make sure the GNS3 **Cloud** node is available (it is under End devices).

## 4. Place the nodes

Drag these into the workspace and rename them exactly:

- R1, R2 (IOSv)
- SW1, SW2, SW3 (IOSvL2)
- STAFF-PC1, STAFF-PC2, STAFF-PC3 (campus-client)
- STUDENT-PC1, STUDENT-PC2, STUDENT-PC3 (campus-client)
- GUEST-PC1 (campus-client)
- SENSOR-TEMP, SENSOR-MOTION, SENSOR-HUMIDITY (campus-sensor)
- SERVER-CLOUD (Cloud)

A suggested layout is in `topology/topology.md`. Node positions do not affect
the configuration.

## 5. Cable the links

Use the Link tool and connect exactly these ports. GNS3 may label the Docker
side `eth0`; that is correct.

| # | From | To |
|---|---|---|
| 1 | R1 g0/0 | SW1 g0/0 |
| 2 | SW1 g0/1 | SW2 g0/0 |
| 3 | SW1 g0/2 | SW3 g0/0 |
| 4 | SW2 g0/1 | STAFF-PC1 eth0 |
| 5 | SW2 g0/2 | STAFF-PC2 eth0 |
| 6 | SW2 g0/3 | STAFF-PC3 eth0 |
| 7 | SW2 g0/4 | STUDENT-PC1 eth0 |
| 8 | SW2 g0/5 | STUDENT-PC2 eth0 |
| 9 | SW2 g0/6 | STUDENT-PC3 eth0 |
| 10 | SW3 g0/1 | GUEST-PC1 eth0 |
| 11 | SW3 g0/2 | SENSOR-TEMP eth0 |
| 12 | SW3 g0/3 | SENSOR-MOTION eth0 |
| 13 | SW3 g0/4 | SENSOR-HUMIDITY eth0 |
| 14 | R1 g0/1 | SERVER-CLOUD |
| 15 | R1 g0/2 | R2 g0/0 |

For link 14, right-click the Cloud node, choose **Configure**, and select
`br-srv` as the interface. If your GNS3 build lists bridges only after a
refresh, restart the GNS3 server once and reopen the project.

## 6. Configure the Docker endpoints

### 6.1 Sensor nodes

Open each sensor node's configuration and set the environment variables:

| Node | `SENSOR_ID` | `SENSOR_TYPE` | `SENSOR_MAC` |
|---|---|---|---|
| SENSOR-TEMP | `temp-01` | `temperature` | `0200.0000.4001` |
| SENSOR-MOTION | `motion-01` | `motion` | `0200.0000.4002` |
| SENSOR-HUMIDITY | `humidity-01` | `humidity` | `0200.0000.4003` |

The sensor MACs must match `radius/users`; MAB uses the Ethernet source MAC as
the RADIUS User-Name. Prefer the GNS3 Docker node's **MAC address** field if
your version offers one. Otherwise the container entrypoint normalises the
dotted `SENSOR_MAC` value to `02:00:00:00:40:01`, bounces `eth0`, and sets it;
this requires `NET_ADMIN` (GNS3 usually grants it; if not, set the MAC in GNS3
instead).

Leave `SENSOR_DHCP=1` so the container uses `udhcpc` on VLAN 40. The first
DHCP discover may be sent before MAB completes; `udhcpc` retries for 90 seconds.

### 6.2 Client nodes

Set these per node:

| Node | `WPA_CONF` | `CLIENT_NAME` |
|---|---|---|
| STAFF-PC1 | `/etc/wpa_supplicant/wpa_supplicant-staff1.conf` | `STAFF-PC1` |
| STAFF-PC2 | `/etc/wpa_supplicant/wpa_supplicant-staff2.conf` | `STAFF-PC2` |
| STAFF-PC3 | `/etc/wpa_supplicant/wpa_supplicant-staff3.conf` | `STAFF-PC3` |
| STUDENT-PC1 | `/etc/wpa_supplicant/wpa_supplicant-student1.conf` | `STUDENT-PC1` |
| STUDENT-PC2 | `/etc/wpa_supplicant/wpa_supplicant-student2.conf` | `STUDENT-PC2` |
| STUDENT-PC3 | `/etc/wpa_supplicant/wpa_supplicant-student3.conf` | `STUDENT-PC3` |
| GUEST-PC1 | `/etc/wpa_supplicant/wpa_supplicant-guest1.conf` | `GUEST-PC1` |

For the wrong-password fallback test, use a spare client node with
`WPA_CONF=/etc/wpa_supplicant/wpa_supplicant-wrongpass.conf`.

## 7. Start order

1. **Docker server segment** (step 1): RADIUS and MQTT first.
2. **SW1, SW2, SW3**.
3. **R1, R2**.
4. **All endpoint Docker containers** last, so DHCP and 802.1X see the finished
   switch/router configuration.

Starting everything at once usually works, but the order above makes the first
authentication attempt deterministic and keeps the test evidence clean.

## 8. Paste the configs

For each device: open its console, press Enter, then:

```
enable
configure terminal
```

Paste the entire corresponding file (`configs/SW1.cfg`, etc.). Wait for the
paste to finish. Watch for `% Invalid input` or `% Incomplete command` lines.
Then:

```
end
write memory
```

Recommended order: **SW1, SW2, SW3, R1, R2**. Saving each device before moving
on makes a failed paste easy to isolate.

### Syntax notes for IOSvL2

- `switchport trunk encapsulation dot1q` is accepted on most IOSvL2 images. If
  your image rejects it (some L2-only images only support dot1q and have no
  command), delete that line and re-paste the interface block.
- If `authentication ...` or `dot1x ...` commands are rejected, the image's
  feature set does not include 802.1X. Do **not** invent replacement syntax.
  Use the MAB-only fallback described in the README: keep the VLAN/trunk/DHCP
  design, use `mab` on all access ports, and document the limitation in the
  report. IOSvL2 and IOU L2 vary here; check `show dot1x all` after pasting.
- If `ip radius source-interface Vlan99` is rejected, use
  `ip radius source-interface Vlan 99` only if that is the syntax your image
  accepts; the normal IOS 15.2 form is `Vlan99`.

## 9. Verify before testing

On each switch:

```
show vlan brief
show interfaces trunk
show ip interface brief
show authentication sessions
show dot1x all
show access-lists
```

On R1:

```
show ip interface brief
show ip dhcp binding
show access-lists
show ip nat translations
show ip route
```

On R2:

```
show ip interface brief
show ip route
```

Then run the offline checker from the repo root (it does not need GNS3):

```sh
python3 tests/verify_configs.py
```

## 10. Common build problems

| Symptom | Likely cause | Fix |
|---|---|---|
| Cloud has no `br-srv` | GNS3 server is in a VM or bridge not created | Run `setup-server-bridge.sh` on the GNS3 server host; restart GNS3 server; use a local server |
| `radius` container exits immediately | Bad `clients.conf`/`users` mount or config | `docker logs radius`; run `docker run --rm -v ... freeradius/freeradius-server:3.2.3 freeradius -CX` |
| Containers cannot ping R1 | macvlan parent/veth/bridge not wired | Check `ip link` for `br-srv`, `srv-br`, `srv-mac`; ensure Cloud is on `br-srv` |
| Switch cannot reach RADIUS | Wrong SVI/VLAN 99/trunk or ACL | `ping 192.168.50.10` from switch; `show ip interface brief`; check `MGMT_IN` counters |
| `show authentication sessions` empty | 802.1X not enabled or port not access | `show dot1x all`; confirm `dot1x system-auth-control`; confirm `switchport mode access` |
| Sensor not in VLAN 40 | MAB MAC mismatch or RADIUS format | `debug authentication` / `radiusd -X`; compare User-Name format with `users` |
| Client stuck unauthorised | wpa_supplicant driver/profile | `docker exec ... cat /tmp/wpa_supplicant.log`; confirm `WPA_CONF` path |
| No MQTT messages | Sensor has no DHCP or ACL blocks 1883 | `docker logs` for sensor; `show access-lists` on R1; check `.20:1883` |
