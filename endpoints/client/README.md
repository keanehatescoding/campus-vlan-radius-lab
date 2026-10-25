# Wired 802.1X client image

One image contains all supplicant profiles; select the user with `WPA_CONF`.

```sh
docker build -t campus-client:1.0 endpoints/client
```

In GNS3 create a Docker template from `campus-client:1.0` with one adapter and
set the environment variable per node:

| GNS3 node | `WPA_CONF` | `CLIENT_NAME` |
|---|---|---|
| STAFF-PC1 | `/etc/wpa_supplicant/wpa_supplicant-staff1.conf` | STAFF-PC1 |
| STAFF-PC2 | `/etc/wpa_supplicant/wpa_supplicant-staff2.conf` | STAFF-PC2 |
| STAFF-PC3 | `/etc/wpa_supplicant/wpa_supplicant-staff3.conf` | STAFF-PC3 |
| STUDENT-PC1 | `/etc/wpa_supplicant/wpa_supplicant-student1.conf` | STUDENT-PC1 |
| STUDENT-PC2 | `/etc/wpa_supplicant/wpa_supplicant-student2.conf` | STUDENT-PC2 |
| STUDENT-PC3 | `/etc/wpa_supplicant/wpa_supplicant-student3.conf` | STUDENT-PC3 |
| GUEST-PC1 | `/etc/wpa_supplicant/wpa_supplicant-guest1.conf` | GUEST-PC1 |

For the failure test, use `wpa_supplicant-wrongpass.conf` on a spare node (or
rebuild a copy of the image with that path as `WPA_CONF`).

## Why EAP-MD5?

The stock FreeRADIUS 3.2 image enables `default_eap_type = md5` and ships a
self-signed server certificate, but EAP-MD5 needs no certificate exchange at
all. That makes the lab reproducible without generating or trusting a CA.
EAP-MD5 is deprecated for production Wi-Fi, but it is fine for a wired GNS3
lab that demonstrates RADIUS dynamic VLAN assignment. To switch to
PEAP/MSCHAPv2 later, add `ca_cert`, `phase2="auth=MSCHAPV2"` and use
`eap=PEAP` here.

The wired driver is used (`wpa_supplicant -D wired`). If an image does not
include it, the entrypoint retries with `wext`; check `/tmp/wpa_supplicant.log`
inside the container if authentication never starts.
