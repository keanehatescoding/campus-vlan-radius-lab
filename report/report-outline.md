# Report Outline

Use this as the structure for the written submission. The report should read
as a design-and-verification document, not as a list of commands. Put the raw
evidence in an appendix or in `report/evidence/`, and reference each item from
the relevant section.

## Title page

- Project title: **Segmented Campus Network with Firewall Policy and RADIUS
  Dynamic VLAN Assignment**
- Course/module, student name, date
- One-line scope statement: two routers, three switches, four user VLANs, an
  out-of-band management VLAN, a server segment, 802.1X/MAB, and an ACL
  firewall on R1.

## 1. Executive summary (1 page)

- What was built.
- How the brief is met: VLANs and device counts, firewall policy, RADIUS
  dynamic VLAN, IoT/MQTT.
- Headline test results (for example "all 20 tests passed except ...").
- The most important limitation: IOSvL2 802.1X/emulation caveats and the
  simulated Internet/DNS service.

## 2. Requirements and design decisions

- Restate the brief (a) VLAN segmentation and (b) firewall + dynamic VLAN.
- Explain the fixed design choices:
  - router-on-a-stick on R1 g0/0;
  - IOSvL2 access switches;
  - R1 as DHCP/NAT/firewall;
  - RADIUS and MQTT on an isolated server segment;
  - MGMT VLAN 99 for switch/radius control traffic;
  - 802.1X for user ports, MAB for headless sensors;
  - EAP-MD5 because stock FreeRADIUS supports it without certificates.
- State what is out of scope: real Internet, DNS service, production PKI,
  redundancy/HA, wireless.

## 3. Topology and physical/logical design

Include:

- GNS3 topology screenshot with all nodes and link labels.
- Logical diagram (VLANs/trunks/server segment).
- Node inventory table.
- Port map table (from `topology/topology.md`).
- Explanation of why SW1 is the spanning-tree root and why the server segment
  is routed rather than trunked.
- The Cloud/macvlan/veth plumbing for RADIUS and MQTT (one short paragraph and
  a simple diagram). Explain that R1, not Docker, is the server gateway.

**Screenshots/evidence:**

1. GNS3 workspace, zoomed to show node names and all links.
2. `show cdp neighbors` on R1 and SW1.
3. A photo/screenshot of the server-segment diagram from
   `topology/topology.md`.

## 4. Addressing and VLAN plan

Include the tables for:

- VLAN ID/name/subnet/gateway/DHCP range.
- Management addresses.
- R1-R2 link and 8.8.8.8 loopback.
- Server segment addresses.
- Fixed sensor MACs.

Explain:

- Why `.1-.20` are excluded from DHCP.
- Why VLAN 99 is management-only.
- Why the server segment is not NATed.
- How DHCP selects a pool on a router-on-a-stick subinterface.

**Screenshots/evidence:**

1. `show ip interface brief` on R1.
2. `show vlan brief` on SW1/SW2/SW3 (three screenshots).
3. `show ip dhcp binding` on R1.
4. `ip addr`/`ip route` on one endpoint per VLAN.

## 5. Layer 2 design and 802.1X/MAB

Explain:

- Trunk allowed lists and native VLAN choice.
- Access-port initial VLANs and dynamic VLAN override.
- `spanning-tree mode rapid-pvst`, SW1 root.
- 802.1X authenticator roles on SW2/SW3.
- MAB on IoT ports.
- Why IoT MAB failure is not sent to the guest VLAN (security rationale).
- Fallback behavior on user ports: `fail` and `no-response` -> VLAN 30.

**Screenshots/evidence:**

1. `show interfaces trunk` (all three switches).
2. `show spanning-tree vlan 10` on SW1 and SW2.
3. `show authentication sessions` on SW2 before/after a client connects.
4. `show dot1x all` on SW3.
5. The switch port block from `configs/SW2.cfg` and `configs/SW3.cfg` (code
   listing, not a screenshot).

## 6. RADIUS design and dynamic VLAN flow

Include a sequence diagram:

```
Supplicant --EAPOL--> Switch --RADIUS Access-Request--> FreeRADIUS
Supplicant <--EAP-- Switch <--Access-Accept (Tunnel-* attributes)-- FreeRADIUS
Switch applies Tunnel-Private-Group-Id, port moves to VLAN
```

Explain:

- `aaa new-model`, `aaa authentication dot1x`, `aaa authorization network`,
  `aaa accounting dot1x`.
- `radius server` entry, the named `CAMPUS-RADIUS` server group, `ip radius
  source-interface Vlan99`, shared secret.
- `clients.conf` entries for SW1/SW2/SW3.
- `users` entries: staff/student/guest and MAC users.
- The three Tunnel attributes and why `aaa authorization network` is required.
- EAP-MD5 trade-off versus PEAP/MSCHAPv2.
- How to change the shared secret consistently.

**Screenshots/evidence:**

1. `radiusd -X` Access-Accept for staff1, student1, guest1 and one MAC user,
   with the Tunnel attributes visible.
2. `show authentication sessions ... details` showing VLAN 10/20/30/40.
3. `show radius statistics` on SW2/SW3.
4. `clients.conf` and `users` excerpts.

## 7. Firewall policy and ACL rationale

Include the policy table from the brief and the implemented ACL table. For each
ACL explain:

- Direction: inbound on the R1 subinterface, so it filters client-originated
  traffic before routing.
- Ordering: DHCP/DNS/HTTP permits relative to the RFC1918 denies; MQTT permit
  before the 192.168/16 deny.
- Why `deny ip any any log` is explicit.
- Why `established` and echo-reply rules are present for return traffic while
  the policy remains one-way for new sessions.
- Why the server subnet and MGMT are not NATed.
- Why NAT is not a security control by itself.

Also discuss what a production design would add: stateful zone firewall,
default-deny on the server segment, RADIUS CoA, DHCP snooping/DAI, port
security, private VLAN/port isolation for same-VLAN peers, and logging to a
collector.

**Screenshots/evidence:**

1. `show access-lists` on R1 with counters after the matrix.
2. `show ip nat translations`.
3. `show logging` excerpt for a denied flow.
4. A table of actual pass/fail results copied from the test plan.

## 8. IoT and MQTT design

Explain:

- Three Docker sensors, one per type, publishing JSON every 5 seconds.
- Topic scheme `campus/iot/<id>`.
- Broker at 192.168.50.20, anonymous lab access.
- IoT ACL: DHCP, DNS to 8.8.8.8, MQTT 1883 to the broker, everything else
  denied.
- Why MAB is appropriate for headless devices and why the MAC is the identity.
- The MAC-format caveat.

**Screenshots/evidence:**

1. `docker ps` showing three sensor containers.
2. Sensor log showing published JSON.
3. `mosquitto_sub` output with all three sensor IDs.
4. Failed `ping 8.8.8.8` from a sensor.
5. `show authentication sessions` for the three IoT ports.

## 9. Test methodology and results

- State that testing was performed in GNS3; include GNS3 version, image
  versions, host OS and Docker version.
- Summarize the test plan: 20 tests, grouped by baseline, RADIUS, firewall,
  MQTT, supporting.
- Include the pass/fail summary sheet.
- For each failed or partially verified test, explain the cause and whether it
  is a design issue or an emulator/service limitation.
- Include the offline checks: `python3 tests/verify_configs.py` output,
  `freeradius -CX`, `docker compose config`, and the MQTT local test.

**Screenshots/evidence:**

1. `verify_configs.py` final output (0 failed).
2. `docker compose ps`.
3. `freeradius -CX` output.
4. The completed pass/fail sheet.

## 10. Limitations and threats to validity

State clearly:

- IOSvL2 802.1X can be flaky or unavailable depending on the image/feature
  set. If it was unavailable, the fallback was MAB-only and the report must say
  so; this still demonstrates RADIUS VLAN assignment but not EAP.
- GNS3 is not a production switch; timing, MAC learning and EAPOL behavior
  differ from hardware.
- EAP-MD5 is lab-only; production should use PEAP/MSCHAPv2 or EAP-TLS.
- The simulated Internet is R2 8.8.8.8; HTTP is available but DNS/HTTPS are not.
  DNS/HTTPS tests therefore verify ACL permits, not application success.
- Anonymous MQTT and a shared RADIUS secret are lab choices, not production
  security.
- The RADIUS/MQTT containers are external to GNS3 and depend on the host
  bridge/macvlan setup; a GNS3 VM needs the same plumbing inside the VM.
- Offline checks cannot prove Cisco IOS syntax or end-to-end behavior.

## 11. Conclusion

- Re-state how the brief is satisfied.
- What was learned about segmentation, 802.1X/MAB, RADIUS attributes, and
  firewall ordering.
- What would be improved in a second iteration (stateful firewall, CoA,
  PEAP/EAP-TLS, redundant links, monitoring).

## Appendix A - Full configurations

Include the five files from `configs/` as code listings. Do not paste
screenshots of configs; text is easier to mark.

## Appendix B - RADIUS files

`clients.conf`, `users` (redact the shared secret/passwords if the report is
public), and `secrets.env` key names.

## Appendix C - Evidence index

| Figure | File | Captured from | Test |
|---|---|---|---|
| 1 | `T01-topology.png` | GNS3 | T01 |
| 2 | `T02-show-vlan-sw1.png` | SW1 | T02 |
| ... | ... | ... | ... |

## Appendix D - Command reference

The exact verification commands used, copied from `tests/test-plan.md`:

```text
show vlan brief
show interfaces trunk
show ip interface brief
show ip dhcp binding
show authentication sessions
show authentication sessions interface <port> details
show dot1x all
show access-lists
show ip nat translations
show radius statistics
show spanning-tree vlan 10
```

## Screenshot checklist (minimum)

- [ ] GNS3 topology with all nodes and links
- [ ] `show vlan brief` x3 switches
- [ ] `show interfaces trunk` x3 switches
- [ ] `show spanning-tree vlan 10` on SW1 and SW2
- [ ] `show authentication sessions` for staff1, student1, guest1
- [ ] `show authentication sessions` for the three sensor MACs
- [ ] staff1 moved to a second port, still VLAN 10
- [ ] wrong password -> VLAN 30
- [ ] RADIUS stopped -> VLAN 30
- [ ] RADIUS debug Access-Accept with all three Tunnel attributes
- [ ] RADIUS debug Access-Reject for the wrong password
- [ ] `show ip dhcp binding` per VLAN
- [ ] ACL matrix command outputs (pass and fail rows)
- [ ] `show access-lists` counters
- [ ] `show ip nat translations`
- [ ] `mosquitto_sub` output from all three sensors
- [ ] sensor failed Internet ping
- [ ] `verify_configs.py` 0 failures
- [ ] `freeradius -CX` success
- [ ] `docker compose ps` healthy
