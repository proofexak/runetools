# Running runetools in Docker (headless, background)

This runs RuneLite + the bot against a **virtual display inside the container**
(Xvfb), not your real screen — the bot's mouse/clicks never touch your actual
desktop, so it can run in the background while you use your PC normally. A VNC
viewer lets you look into that virtual display when you need to (Bolt login,
recalibration), then you disconnect and it keeps running.

Builds on the setup already validated in [OSRS_ON_UBUNTU.md](../OSRS_ON_UBUNTU.md)
(RuneLite + Bolt on X11) — same constraints apply (X11 only, not Wayland; that's
automatically true here since Xvfb *is* X11).

## Footprint

Measured with `docker/measure.sh` on an Ubuntu 20.04 host (4 cores, 8 GB),
RuneLite at its login screen (logged-in numbers will be somewhat higher):

| | image | RAM idle | RAM client | CPU client |
|---|---|---|---|---|
| before (Ubuntu openjdk-17-jre, Mesa, fluxbox) | 1,087 MB | 27 MiB | 591 MiB | ~160 % |
| **now** (defaults below) | **438 MB** | **19 MiB** | **395 MiB** | **~43 %** |

Where it came from (each step measured separately):

| change | effect |
|---|---|
| two-stage build: compiler only in the build stage | −150 MB image (it also fixes the build: pynput's `evdev` needs gcc + kernel headers) |
| Eclipse Temurin 17 JRE instead of Ubuntu's `openjdk-17-jre` | −300 MB image — Ubuntu's package drags in GTK2/3, icon themes, ghostscript, CUPS |
| no window manager (fluxbox) | a little RAM; also removes a stray "can't set wallpaper" popup the bot could click on |
| Mesa removed, Xvfb started with `-extension GLX` | −190 MB image, CPU ~160 % → ~53 % — with software OpenGL available, RuneLite's GPU plugin renders on the CPU |
| FPS cap (RuneLite FPS Control plugin) | CPU ~53 % → ~37 % at 20 FPS (default is 30: ~43 %) |
| JVM `-Xmx512m -XX:+UseSerialGC` | RAM ~460 → ~395 MiB |

Re-measure any image yourself: `docker/measure.sh <image>` (see the script's header
for knobs). **Keep RuneLite's GPU plugin off in a container** — there's no GPU, so
it would run on software OpenGL and burn ~1.5 cores; this image can't run it at all.

## Prerequisites

### Ubuntu (tested on 20.04)

```
sudo apt-get update && sudo apt-get install -y docker.io docker-compose-v2 docker-buildx
sudo usermod -aG docker $USER      # then log out/in (or prefix commands with: sg docker -c "...")
```

The container runs as your user (UID/GID 1000 by default) so everything the bots
write into the repo — logs, saved calibration — stays owned by you. If `id -u` /
`id -g` aren't 1000, put `RUNETOOLS_UID=…` and `RUNETOOLS_GID=…` in `docker/.env`.

### Windows

- **Docker Desktop** (WSL2 backend). In Settings → Resources give the WSL2 VM at
  least ~1.5 GB RAM. Note that Docker Desktop's VM itself costs RAM on top of the
  container (see "Alternatives" below).

### Both

- **A VNC viewer** on the host (TigerVNC, RealVNC Viewer, Remmina on Ubuntu, …).

## One-time setup

### 1. Get Bolt (Jagex login)

Codeberg blocks automated downloads of Bolt's release assets (tarpits bot
requests — see OSRS_ON_UBUNTU.md), so this has to be a manual browser download:

1. In a browser, go to https://codeberg.org/Adamcake/Bolt/releases and download
   the Linux zip (`Bolt-Linux.zip`) from the latest release.
2. Unzip it into `docker/bolt/` in this repo, so the `Bolt` executable ends up
   somewhere under there. Find it with:
   ```
   find docker/bolt -maxdepth 2 -type f
   ```
3. `docker/bolt/*.zip` and the unzipped folder are gitignored — this is
   per-machine, not checked in.

Ubuntu 24.04 (the container's base image) ships glibc/libstdc++ new enough for
Bolt's raw binary, so unlike the bare-Ubuntu-20.04 case in OSRS_ON_UBUNTU.md,
no Flatpak workaround is needed here.

### 2. Build and start

```
docker compose -f docker/docker-compose.yml build
docker compose -f docker/docker-compose.yml up -d
```

It boots Xvfb + x11vnc, then idles — it doesn't auto-launch anything.

### 3. Connect a VNC viewer

Point your VNC client at `localhost:5900` (bound to localhost only). Password is
`runetools` by default — override it in `docker/.env` with `VNC_PASSWORD=…`
before starting the container.

### 4. Log into Jagex via Bolt, launch RuneLite

Open a shell inside the container (separate from the VNC session — this is where
you type commands, the VNC window is where the GUI appears):

```
docker compose -f docker/docker-compose.yml exec runetools bash
```

Inside that shell (`DISPLAY=:1` is already set):

```
/opt/bolt/Bolt &          # adjust path to whatever `find` showed above
```

Log into your Jagex account in the VNC window and launch RuneLite from Bolt — or
start it directly with `runelite &` once you have a session. `runelite` applies
the container defaults (FPS cap, JVM flags, GPU plugin off) on a fresh RuneLite
profile; see "Settings" below.

RuneLite's and Bolt's state live in `/home/runetools`, a named Docker volume
(`runetools-userhome`) — it survives `docker compose down` / restarts, so you
shouldn't need to log in again. (`down -v` would wipe it — don't use `-v` unless
you mean to.)

### 5. Recalibrate

The virtual display defaults to 1280x800 (`XVFB_RESOLUTION` in `docker/.env`,
e.g. `XVFB_RESOLUTION=1920x1080x24`; keep the depth at 24 — the bots match exact
colours). Without a window manager RuneLite opens undecorated and centred, so
positions won't match configs calibrated on a normal desktop. Start the menu
from the exec shell and use each bot's **⚙ Configure** (and GE / Energy Config):

```
python3 run.py
```

The repo is bind-mounted at `/app`, so configs land back in your working tree,
same gitignored files as before. Energy digit templates: `python3
calibrate_energy_digits.py` (see the main README's "Stamina potions" section).

## Running the bot

From the exec shell: `python3 run.py`, pick a bot in the overlay (via VNC). Then
disconnect VNC and leave it running. Press **O** in the VNC window to pause,
**P** to force-stop. Session logs land in `<bot>/log/` in your working tree —
`python -m lib.logreport` on the host reads them.

## Unattended mode

Set a bot in `docker/.env` and the container runs it with nobody watching:
`lib.headless` keeps RuneLite logged in, runs the bot, restarts it after crashes
and logouts, and comes back by itself after a container or host restart.

### One-time setup

1. **Save your login.** RuneLite can store the Jagex session it gets from Bolt so
   it can log in later without Bolt: launch RuneLite **once from Bolt with the
   extra RuneLite argument `--insecure-write-credentials`** (in Bolt's RuneLite
   launch options). Check it worked from the exec shell:
   ```
   ls ~/.runelite/credentials.properties
   ```
   ⚠ That file holds your session tokens **in plain text**. It lives only in the
   local `runetools-userhome` Docker volume; don't copy it anywhere. Deleting it
   (or `docker compose down -v`) logs the container out.
2. **Capture the login templates** (once, and again if Jagex restyles a screen):
   `python3 run.py` → **⚙ Client Templates**, then drag a rectangle (via VNC) over
   each element while it is on screen:

   | template | what to select |
   |---|---|
   | `terms_accept` | the terms dialog's **Accept** button (first start of a fresh profile only; optional) |
   | `login_play` | the login screen's **Play Now** button |
   | `welcome_play` | the red **CLICK HERE TO PLAY** button after logging in |
   | `in_game` | something always visible in game, e.g. the compass or minimap frame |

   Crops land in `lib/client_templates/` (gitignored, per user). Select only the
   element, with nothing on top of it.
3. **Pick the bot** in `docker/.env` — names as shown in the menu:
   ```
   BOT=Tanning
   LAUNCH=Green Dragonhide
   # VALUE=500      # only for launches that ask for a number (Choco Grind)
   ```
   then `docker compose -f docker/docker-compose.yml up -d`. Remove `BOT` to go
   back to manual mode (the container just idles, as before).

### Control: `docker/botctl`

| command | effect |
|---|---|
| `docker/botctl pause` / `resume` | pause / resume (same as O) |
| `docker/botctl stop` | finish the current trip, then idle |
| `docker/botctl kill` | stop right now (same as P), then idle |
| `docker/botctl start` | leave idle: log in if needed and start the bot |
| `docker/botctl status` | recent sessions + supervisor events |
| `docker compose … stop` / `down` | stop now and exit cleanly |

### What it does when a session ends

| how it ended | supervisor |
|---|---|
| crashed (unexpected error) | logs back in if needed, waits, restarts |
| stopped by the bot while **logged out** | logs back in, restarts (the logout explains it) |
| stopped by the bot while still logged in (out of hides, no glory charges, …) | **idles** — a human is needed |
| done (job finished) | idles |
| stopped via `botctl stop` / `kill` | idles |

Waits before automatic restarts grow 30 s → 1 min → 2 min … up to 10 min (reset
after a session of 10+ minutes); at most **5 automatic restarts per hour** and
**3 failed logins in a row** before it idles. Idle never exits — the container
and VNC stay up; `botctl start` resumes. Everything is logged to
`log/launcher.jsonl`: `python -m lib.logreport supervisor` (or `botctl status`).

## Settings (`docker/.env`)

| variable | default | |
|---|---|---|
| `VNC` | `1` | `0` = no VNC server (fully unattended) |
| `VNC_PASSWORD` | `runetools` | |
| `XVFB_RESOLUTION` | `1280x800x24` | keep depth 24 |
| `RUNELITE_FPS` | `30` | frame cap seeded on a fresh RuneLite profile; `0` = no cap |
| `RUNELITE_JAVA_OPTS` | `-Xmx512m -XX:+UseSerialGC` | client JVM flags |
| `RUNETOOLS_UID` / `RUNETOOLS_GID` | `1000` | your `id -u` / `id -g` on Linux |
| `BOT` / `LAUNCH` / `VALUE` | unset | unattended mode (see above); unset = manual mode |

`RUNELITE_FPS` and "GPU plugin off" only apply to a **fresh** profile (RuneLite
reads them once from `settings.properties`); on an existing one, set them in
RuneLite's settings (FPS Control plugin, GPU plugin).

## Alternatives considered

- **Slimmer base images:** Debian 12 is too old for Bolt (needs GLIBCXX_3.4.32 /
  gcc-13); Debian 13 isn't meaningfully smaller than Ubuntu 24.04; Alpine (musl)
  can't run Bolt's glibc binary.
- **Podman:** runs this same Dockerfile, rootless, on Ubuntu — a drop-in if you'd
  rather not run the Docker daemon. Not measured separately; the container
  footprint is the same.
- **LXC:** a full system container — more to set up and maintain for no footprint
  gain here.
- **Windows: WSL2 distro + Xvfb, no Docker Desktop:** the lightest option on
  Windows — Docker Desktop's own VM/daemon overhead goes away and the same
  packages run directly in a WSL2 Ubuntu 24.04. Not measured (no Windows host
  here); worth trying if Docker Desktop's RAM use matters.

## Stopping

```
docker compose -f docker/docker-compose.yml down
```
