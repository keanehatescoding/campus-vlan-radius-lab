#!/bin/sh
# 802.1X supplicant + DHCP client for a wired GNS3 Docker endpoint.
set -eu

CONF="${WPA_CONF:-/etc/wpa_supplicant/wpa_supplicant-staff1.conf}"
NAME="${CLIENT_NAME:-client}"
LOG=/tmp/wpa_supplicant.log
mkdir -p /var/run/wpa_supplicant
: > "$LOG"

echo "[$NAME] using supplicant config $CONF"
echo "[$NAME] MAC before 802.1X: $(cat /sys/class/net/eth0/address 2>/dev/null || echo unknown)"

# The wired driver is the correct one for an Ethernet port. Fall back to wext
# only for unusual images; wired is what IOSvL2 expects.
# Note: wpa_supplicant 2.10 has no -f option; redirect its output instead.
if ! wpa_supplicant -i eth0 -D wired -c "$CONF" -B >>"$LOG" 2>&1; then
    echo "[$NAME] wired driver failed, retrying with wext"
    wpa_supplicant -i eth0 -D wext -c "$CONF" -B >>"$LOG" 2>&1 || true
fi

# Give the switch and RADIUS time to finish EAP before asking for DHCP. If the
# authentication fails and the switch applies the guest fallback VLAN, udhcpc
# still retries long enough to obtain a lease in VLAN 30.
for _ in $(seq 1 20); do
    STATE=$(wpa_cli -i eth0 status 2>/dev/null | sed -n 's/^wpa_state=//p')
    echo "[$NAME] wpa_state=${STATE:-unknown}"
    [ "$STATE" = "COMPLETED" ] && break
    sleep 2
done

echo "[$NAME] requesting DHCP"
udhcpc -i eth0 -s /usr/local/bin/udhcpc.script -t 30 -T 3 -q -n -f || {
    echo "[$NAME] WARNING: no DHCP lease yet; leaving container running"
}

echo "[$NAME] interface state:"
ip addr show eth0 || true

# Keep the container alive and stream supplicant state to the GNS3 console.
exec tail -f "$LOG"
