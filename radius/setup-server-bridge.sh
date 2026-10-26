#!/usr/bin/env bash
#
# Create the Linux-side plumbing for the 192.168.50.0/24 server segment.
#
#   br-srv (Linux bridge)  <-- GNS3 Cloud node -- R1 g0/1
#      |
#   srv-br (veth peer)
#      |
#   srv-mac (veth end used as the Docker macvlan parent)
#      |
#   radius .10 / mqtt .20
#
# Why the veth pair? Docker macvlan needs a parent interface, while GNS3's
# Cloud node wants a bridge. Putting a veth pair between them gives each side
# the interface type it expects.
#
# Run as your normal user; the script uses sudo where required.
set -euo pipefail

BRIDGE="${SERVER_BRIDGE:-br-srv}"
MAC_PARENT="${SERVER_MACVLAN_PARENT:-srv-mac}"
# Keep the documented peer name (srv-br), not "${MAC_PARENT}-br" (srv-mac-br).
# The peer name is independent of the macvlan parent name.
PEER="${SERVER_VETH_PEER:-srv-br}"

if [ "$(id -u)" -eq 0 ]; then
    SUDO=""
else
    SUDO="sudo"
fi

if ! command -v ip >/dev/null 2>&1; then
    echo "ERROR: the 'ip' command is required." >&2
    exit 1
fi

if ! ip link show "$BRIDGE" >/dev/null 2>&1; then
    echo "Creating bridge $BRIDGE"
    $SUDO ip link add "$BRIDGE" type bridge
else
    echo "Bridge $BRIDGE already exists"
fi
$SUDO ip link set "$BRIDGE" up

if ip link show "$MAC_PARENT" >/dev/null 2>&1; then
    echo "Interface $MAC_PARENT already exists"
    if ! ip link show "$PEER" >/dev/null 2>&1; then
        echo "ERROR: $MAC_PARENT exists but its expected peer $PEER does not." >&2
        echo "       Remove $MAC_PARENT or set SERVER_MACVLAN_PARENT to a new name." >&2
        exit 1
    fi
else
    if ip link show "$PEER" >/dev/null 2>&1; then
        echo "ERROR: $PEER exists but $MAC_PARENT does not." >&2
        echo "       Remove $PEER or set SERVER_VETH_PEER to a new name." >&2
        exit 1
    fi
    echo "Creating veth pair $MAC_PARENT <-> $PEER"
    $SUDO ip link add "$MAC_PARENT" type veth peer name "$PEER"
fi

if ! ip -o link show "$PEER" | grep -q "master $BRIDGE"; then
    $SUDO ip link set "$PEER" master "$BRIDGE"
fi
$SUDO ip link set "$PEER" up
$SUDO ip link set "$MAC_PARENT" up

echo
echo "Server-segment plumbing is ready:"
echo "  bridge      : $BRIDGE   (attach the GNS3 Cloud node here)"
echo "  macvlan base: $MAC_PARENT (used by docker compose)"
echo
echo "Next:"
echo "  cd $(cd "$(dirname "$0")" && pwd)"
echo "  docker compose up -d"
echo
echo "To remove it later:"
echo "  docker compose down"
echo "  sudo ip link del $MAC_PARENT   # also removes $PEER"
echo "  sudo ip link del $BRIDGE"
