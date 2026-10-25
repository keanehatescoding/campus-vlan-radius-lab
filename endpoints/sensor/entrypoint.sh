#!/bin/sh
# Sensor container startup: optional MAC override, DHCP, then MQTT loop.
set -eu

# MAB is keyed on the source MAC. Prefer setting the MAC in the GNS3 Docker
# node properties; SENSOR_MAC is a fallback for images/containers that have
# NET_ADMIN. If the set fails, the container keeps the MAC Docker/GNS3 gave it.
#
# SENSOR_MAC uses the Cisco dotted form (0200.0000.4001), but Linux `ip link`
# needs colon-separated hex (02:00:00:00:40:01). Normalise either form, and
# bounce the link so the switch starts MAB with the new MAC.
if [ -n "${SENSOR_MAC:-}" ]; then
    MAC_HEX=$(printf '%s' "$SENSOR_MAC" | tr 'A-F' 'a-f' | tr -d '.:-')
    case "$MAC_HEX" in
        *[!0-9a-f]*|"")
            echo "[entrypoint] WARNING: SENSOR_MAC=$SENSOR_MAC is not a 12-digit hex MAC; ignoring"
            ;;
        *)
            if [ "${#MAC_HEX}" -ne 12 ]; then
                echo "[entrypoint] WARNING: SENSOR_MAC=$SENSOR_MAC is not a 12-digit hex MAC; ignoring"
            else
                MAC_COLON=$(printf '%s' "$MAC_HEX" | sed 's/../&:/g; s/:$//')
                ip link set dev eth0 down 2>/dev/null || true
                if ip link set dev eth0 address "$MAC_COLON" 2>/dev/null; then
                    echo "[entrypoint] eth0 MAC set to $MAC_COLON"
                else
                    echo "[entrypoint] WARNING: could not set eth0 MAC to $MAC_COLON"
                    echo "[entrypoint] current MAC: $(cat /sys/class/net/eth0/address 2>/dev/null || echo unknown)"
                fi
                ip link set dev eth0 up 2>/dev/null || true
            fi
            ;;
    esac
fi

if [ "${SENSOR_DHCP:-1}" = "1" ]; then
    echo "[entrypoint] requesting DHCP on eth0"
    udhcpc -i eth0 -s /app/udhcpc.script -t 30 -T 3 -q -n -f || {
        echo "[entrypoint] WARNING: DHCP did not complete; continuing anyway"
    }
fi

exec python -u /app/sensor.py
