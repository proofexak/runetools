FROM ubuntu:24.04

# Ubuntu 24.04 is required (not 20.04, see OSRS_ON_UBUNTU.md): Bolt's raw Linux binary
# needs GLIBC_2.34+ and GLIBCXX_3.4.32+ (from gcc-13), which 24.04 ships by default.
# This lets us skip Flatpak entirely, which is impractical inside a minimal container
# (needs a D-Bus session + OSTree storage).

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
        xvfb \
        x11vnc \
        fluxbox \
        x11-utils \
        libxtst6 \
        libxrender1 \
        libxext6 \
        libxi6 \
        libffi8 \
        fonts-dejavu-core \
        openjdk-17-jre \
        python3 \
        python3-pip \
        python3-venv \
        unzip \
        wget \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# RuneLite launcher jar — public GitHub release, fetched at build time.
RUN wget -q -O /opt/RuneLite.jar \
        https://github.com/runelite/launcher/releases/latest/download/RuneLite.jar

# Bolt (Jagex login) is NOT fetched here: Codeberg tarpits automated requests to its
# release asset URLs (see OSRS_ON_UBUNTU.md "What didn't work"). Download
# Bolt-Linux.zip manually via a browser and drop it in docker/bolt/ on the host —
# it's bind-mounted into the container at /opt/bolt (see docker-compose.yml).

RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:${PATH}"
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

ENV DISPLAY=:1
WORKDIR /app

COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
CMD ["sleep", "infinity"]
