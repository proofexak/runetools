#!/bin/bash
set -e

RES="${XVFB_RESOLUTION:-1280x800x24}"
VNC_PASSWORD="${VNC_PASSWORD:-runetools}"

Xvfb "$DISPLAY" -screen 0 "$RES" &

for i in $(seq 1 20); do
    xdpyinfo -display "$DISPLAY" >/dev/null 2>&1 && break
    sleep 0.5
done

fluxbox &

x11vnc -display "$DISPLAY" -forever -shared -rfbport 5900 -passwd "$VNC_PASSWORD" -bg -o /var/log/x11vnc.log

exec "$@"
