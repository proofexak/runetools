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

# Bolt (Jagex login) is NOT fetched here: Codeberg tarpits automated requests to
# its release assets (see OSRS_ON_UBUNTU.md). Download Bolt-Linux.zip in a
# browser into docker/bolt/ on the host — bind-mounted at /opt/bolt.

# ── runtime ───────────────────────────────────────────────────────────────────
FROM ubuntu:24.04
ENV DEBIAN_FRONTEND=noninteractive

# Xvfb pulls in Mesa (software OpenGL, ~190 MB incl. LLVM) through libgl1.
# Nothing here needs OpenGL — RuneLite's GPU plugin must stay off in a
# container anyway (on software GL it burns ~1.5 CPU cores) — so Mesa is
# removed right after install and Xvfb runs with -extension GLX (entrypoint.sh).
# Side effect: dpkg reports libgl1's dependency as unmet; don't apt-get install
# on top of this image, extend the Dockerfile instead.
RUN apt-get update && apt-get install -y --no-install-recommends \
        xvfb x11vnc x11-utils \
        libxtst6 libxrender1 libxext6 libxi6 libxrandr2 libxinerama1 \
        libxcb-render0 libxcb-shm0 libxcb-xfixes0 libxcb-randr0 \
        libfreetype6 libfontconfig1 fonts-dejavu-core \
        python3 python3-tk libffi8 unzip ca-certificates \
    && dpkg --purge --force-depends libllvm20 mesa-libgallium libgbm1 libglx-mesa0 libgl1-mesa-dri 2>/dev/null; \
    rm -rf /var/lib/apt/lists/*

COPY --from=build /opt/venv /opt/venv
COPY --from=build /opt/jre /opt/jre
COPY --from=build /opt/RuneLite.jar /opt/RuneLite.jar

# Runs as the host user's UID (docker-compose.yml), which has no passwd entry —
# so HOME is a world-writable dir and Java is told where it is explicitly.
RUN mkdir -p /home/runetools && chmod 1777 /home/runetools
ENV PATH="/opt/venv/bin:/opt/jre/bin:${PATH}" \
    DISPLAY=:1 \
    HOME=/home/runetools \
    JAVA_TOOL_OPTIONS="-Duser.home=/home/runetools"

COPY docker/entrypoint.sh /entrypoint.sh
COPY docker/runelite /usr/local/bin/runelite
RUN chmod 755 /entrypoint.sh /usr/local/bin/runelite

WORKDIR /app
ENTRYPOINT ["/entrypoint.sh"]
CMD ["sleep", "infinity"]
