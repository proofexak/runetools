# syntax=docker/dockerfile:1
#
# Two stages: everything that needs a compiler or a download happens in `build`;
# the runtime image only gets what RuneLite + the bots need. Footprint numbers
# and how to reproduce them: docker/README.md, docker/measure.sh.
#
# Ubuntu 24.04 is required for the runtime (not 20.04, see OSRS_ON_UBUNTU.md):
# Bolt's raw Linux binary needs GLIBC_2.34+ and GLIBCXX_3.4.32+ (gcc-13's
# libstdc++). Debian 12 is too old for that, Debian 13 isn't smaller, and Alpine
# (musl) can't run Bolt at all.

# ── build ─────────────────────────────────────────────────────────────────────
FROM ubuntu:24.04 AS build
ENV DEBIAN_FRONTEND=noninteractive

# gcc + kernel headers: pynput's `evdev` dependency builds a C extension.
RUN apt-get update && apt-get install -y --no-install-recommends \
        python3 python3-venv python3-dev gcc linux-libc-dev wget ca-certificates

COPY requirements.txt /tmp/requirements.txt
RUN python3 -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir -r /tmp/requirements.txt \
    && /opt/venv/bin/pip uninstall -y pip setuptools

# RuneLite launcher jar — public GitHub release.
RUN wget -q -O /opt/RuneLite.jar \
        https://github.com/runelite/launcher/releases/latest/download/RuneLite.jar

# Eclipse Temurin 17 JRE instead of Ubuntu's openjdk-17-jre: Ubuntu's package
# drags in GTK2/3, icon themes, ghostscript, CUPS and Mesa (~400 MB) that
# RuneLite never uses.
RUN mkdir /opt/jre \
    && wget -q -O- "https://api.adoptium.net/v3/binary/latest/17/ga/linux/x64/jre/hotspot/normal/eclipse" \
        | tar -xz -C /opt/jre --strip-components=1 \
    && rm -rf /opt/jre/legal /opt/jre/man

# Mozilla's APT key: the runtime gets Firefox from Mozilla's repository (Ubuntu's
# firefox package is a snap wrapper, and snaps don't run in a container).
RUN wget -q -O /opt/packages.mozilla.org.asc https://packages.mozilla.org/apt/repo-signing-key.gpg

# Bolt (Jagex login) is NOT fetched here: Codeberg tarpits automated requests to
# its release assets (see OSRS_ON_UBUNTU.md). Download Bolt-Linux.zip in a
# browser into docker/bolt/ on the host — bind-mounted at /opt/bolt.

# ── runtime ───────────────────────────────────────────────────────────────────
FROM ubuntu:24.04
ENV DEBIAN_FRONTEND=noninteractive

# Xvfb pulls in Mesa (software OpenGL, ~190 MB incl. LLVM) through libgl1.
# RuneLite needs no OpenGL — its GPU plugin must stay off in a container (on
# software GL it burns ~1.5 CPU cores; docker/runelite forces it off). Firefox
# does: a browser without WebGL stands out, so with BROWSER=1 Mesa stays (WebGL on
# its CPU renderer, through EGL) and Xvfb gets GLX (entrypoint.sh); with
# BROWSER=0 it's removed right after install and Xvfb runs without GLX. Side effect then: dpkg reports
# libgl1's dependency as unmet; don't apt-get install on top of this image,
# extend the Dockerfile instead.
#
# BROWSER=1 (default): Firefox for signing up / logging in from inside the container
# (docker/botctl <account> browser, docker/README.md "Web browser") with what an
# Ubuntu laptop's has — its fonts (Ubuntu, Noto, colour emoji) and a Polish language
# pack; BROWSER=0 builds without it.
# tzdata: TZ (docker/.env) only takes effect with it — without, everything is UTC.
ARG BROWSER=1
COPY --from=build /opt/packages.mozilla.org.asc /etc/apt/keyrings/packages.mozilla.org.asc
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates \
    && if [ "$BROWSER" = 1 ]; then \
        echo "deb [signed-by=/etc/apt/keyrings/packages.mozilla.org.asc] https://packages.mozilla.org/apt mozilla main" \
            > /etc/apt/sources.list.d/mozilla.list \
        && printf 'Package: *\nPin: origin packages.mozilla.org\nPin-Priority: 1000\n' > /etc/apt/preferences.d/mozilla \
        && apt-get update; \
    fi \
    && apt-get install -y --no-install-recommends \
        xvfb x11vnc x11-utils \
        libxtst6 libxrender1 libxext6 libxi6 libxrandr2 libxinerama1 \
        libxcb-render0 libxcb-shm0 libxcb-xfixes0 libxcb-randr0 \
        libfreetype6 libfontconfig1 fonts-dejavu-core \
        python3 python3-tk libffi8 unzip tzdata \
        $(if [ "$BROWSER" = 1 ]; then echo firefox firefox-l10n-pl fonts-liberation \
            fonts-ubuntu fonts-noto-core fonts-noto-color-emoji libegl1 libegl-mesa0; fi) \
    && if [ "$BROWSER" != 1 ]; then \
        dpkg --purge --force-depends libllvm20 mesa-libgallium libgbm1 libglx-mesa0 libgl1-mesa-dri 2>/dev/null; \
    fi; \
    rm -rf /var/lib/apt/lists/*

# Firefox's defaults: Polish, DNS over HTTPS through the proxy (docker/firefox-prefs.js)
COPY docker/firefox-prefs.js /usr/lib/firefox/defaults/pref/laptop.js

COPY --from=build /opt/venv /opt/venv
COPY --from=build /opt/jre /opt/jre
COPY --from=build /opt/RuneLite.jar /opt/RuneLite.jar

# Runs as the host user's UID (docker/bot.yml), whose passwd entry is the account's
# own user (docker/accounts/<account>/passwd, home /home/<user>). The account's volume
# is mounted at /home/runetools and the entrypoint links /home/<user> to it — so
# /home is world-writable (sticky) for that.
RUN mkdir -p /home/runetools && chmod 1777 /home/runetools /home
ENV PATH="/opt/venv/bin:/opt/jre/bin:${PATH}" \
    DISPLAY=:1 \
    HOME=/home/runetools

COPY docker/entrypoint.sh /entrypoint.sh
COPY docker/runelite /usr/local/bin/runelite
COPY docker/browser /usr/local/bin/browser
COPY docker/check-ip /usr/local/bin/check-ip
RUN chmod 755 /entrypoint.sh /usr/local/bin/runelite /usr/local/bin/browser /usr/local/bin/check-ip

WORKDIR /app
ENTRYPOINT ["/entrypoint.sh"]
CMD ["sleep", "infinity"]
