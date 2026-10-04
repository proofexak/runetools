#!/bin/bash
set -e

RES="${XVFB_RESOLUTION:-1280x800x24}"
VNC_PASSWORD="${VNC_PASSWORD:-runetools}"

# No GLX: Mesa isn't installed (see Dockerfile). No window manager either —
# RuneLite runs fine without one (undecorated, centred), and fluxbox only added
# RAM plus a stray "can't set wallpaper" popup the bot could click on.
# A container restart leaves the previous Xvfb's lock behind ("Server is
# already active for display 1"), which would break coming back unattended.
rm -f "/tmp/.X${DISPLAY#:}-lock" "/tmp/.X11-unix/X${DISPLAY#:}"
Xvfb "$DISPLAY" -screen 0 "$RES" -extension GLX &

for i in $(seq 1 20); do
    xdpyinfo -display "$DISPLAY" >/dev/null 2>&1 && break
    sleep 0.5
done

# VNC to look into the virtual display (login, calibration, watching). VNC=0
# turns it off for fully unattended runs; it costs ~10 MB when idle.
if [ "${VNC:-1}" != "0" ]; then
    x11vnc -display "$DISPLAY" -forever -shared -rfbport 5900 -passwd "$VNC_PASSWORD" \
        -bg -o /tmp/x11vnc.log
fi

exec "$@"
