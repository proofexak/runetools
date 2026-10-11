#!/bin/bash
set -e

# The account's user (docker/accounts/<account>/passwd) has its home at /home/<user>;
# its files live in the account's volume, mounted at /home/runetools.
if [ "$HOME" != /home/runetools ] && [ ! -e "$HOME" ]; then
    ln -s /home/runetools "$HOME"
fi

RES="${XVFB_RESOLUTION:-1280x800x24}"
VNC_PASSWORD="${VNC_PASSWORD:-runetools}"

# No GLX: Mesa isn't installed (see Dockerfile). No window manager either —
# RuneLite runs fine without one (undecorated, centred), and fluxbox only added
# RAM plus a stray "can't set wallpaper" popup the bot could click on.
# A container restart leaves the previous Xvfb's lock behind ("Server is
# already active for display 1"), which would break coming back unattended.
rm -f "/tmp/.X${DISPLAY#:}-lock" "/tmp/.X11-unix/X${DISPLAY#:}"
# GLX only when Mesa is in the image (BROWSER=1: Firefox's WebGL needs it); RuneLite's
# GPU plugin stays forced off either way (docker/runelite).
GLX="-extension GLX"
ls /usr/lib/*/libGLX_mesa.so.0 >/dev/null 2>&1 && GLX=""
# shellcheck disable=SC2086  # GLX: empty or two words
Xvfb "$DISPLAY" -screen 0 "$RES" $GLX &

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
