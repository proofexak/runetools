# Running runetools in Docker (headless, background)

This runs RuneLite + the bot against a **virtual display inside the container**
(Xvfb), not your real screen — the bot's mouse/clicks never touch your actual
desktop, so it can run in the background while you use your PC normally. A VNC
viewer lets you look into that virtual display when you need to (Bolt login,
recalibration), then you disconnect and it keeps running.

Builds on the setup already validated in [OSRS_ON_UBUNTU.md](../OSRS_ON_UBUNTU.md)
(RuneLite + Bolt on X11) — same constraints apply (X11 only, not Wayland; that's
automatically true here since Xvfb *is* X11).

## Prerequisites

- **Docker Desktop** (WSL2 backend) — not currently installed on this machine.
  Install it, then in Docker Desktop → Settings → Resources, give the WSL2 VM at
  least ~2GB RAM (Xvfb + RuneLite's JVM + Python together idle around 400-600MB,
  headroom matters more once the bot is actively running).
- **A VNC viewer** on the host to look into the container's virtual display
  (TigerVNC, RealVNC Viewer, or any VNC client).

## One-time setup

### 1. Get Bolt (Jagex login)

Codeberg blocks automated downloads of Bolt's release assets (tarpits bot
requests — see OSRS_ON_UBUNTU.md), so this has to be a manual browser download,
same as before:

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

### 2. Build the image

```
docker compose -f docker/docker-compose.yml build
```

### 3. Start the container

```
docker compose -f docker/docker-compose.yml up -d
```

It boots Xvfb + a minimal window manager (fluxbox) + x11vnc, then idles — it
doesn't auto-launch anything.

### 4. Connect a VNC viewer

Point your VNC client at `localhost:5900`. Password is `runetools` by default —
override it by creating a `docker/.env` file with `VNC_PASSWORD=something-else`
before starting the container.

### 5. Log into Jagex via Bolt, launch RuneLite

Open a shell inside the container (separate from the VNC session — this is
where you type commands, the VNC window is where the GUI appears):

```
docker compose -f docker/docker-compose.yml exec runetools bash
```

Inside that shell (`DISPLAY=:1` is already set):

```
/opt/bolt/Bolt &          # adjust path to whatever `find` showed above
```

Log into your Jagex account in the VNC window, launch RuneLite from Bolt (or
run `java -jar /opt/RuneLite.jar &` directly once you have a session).

RuneLite's config and Bolt's login/session state live under `/root` in the
container, which is a named Docker volume (`runetools-home`) — it survives
`docker compose down` / restarts, so you shouldn't need to log in again after
the first time. (`down -v` would wipe it — don't use `-v` unless you mean to.)

### 6. Recalibrate

The virtual display defaults to 1280x800 (override with `XVFB_RESOLUTION` in
`docker/.env`, e.g. `XVFB_RESOLUTION=1920x1080x24`) — this almost certainly
doesn't match whatever resolution your existing `tanner/config.py` /
`lib/ge_config.py` / `lib/energy_config.py` / digit templates were calibrated
against on Windows. Redo calibration from inside the same exec shell:

```
python3 tanner/config_editor.py
```

(and `calibrate_energy_digits.py` for the stamina digit templates — see the
README's "Stamina potions" section). The repo is bind-mounted into `/app` in
the container, so these configs land back in your working tree on the host,
same gitignored files as before.

## Running the bot

From the same exec shell:

```
python3 tanner/run.py
```

Watch it via the VNC viewer if you want; otherwise just leave it running and
disconnect. Press **P** (sent through the VNC window, or `docker exec` +
`xdotool key p` if you want to pause without a VNC session open) to pause.

## Stopping

```
docker compose -f docker/docker-compose.yml down
```
