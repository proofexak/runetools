# Running runetools in Docker (headless, background)

This runs RuneLite + the bot against a **virtual display inside the container**
(Xvfb), not your real screen — the bot's mouse/clicks never touch your actual
desktop, so it can run in the background while you use your PC normally. A VNC
viewer lets you look into that virtual display when you need to (calibration,
watching it), then you disconnect and it keeps running.

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

### 1. Get your Jagex login (`credentials.properties`)

The container logs in with RuneLite alone, using the Jagex session RuneLite saves
when it's started with `--insecure-write-credentials`. Get that file once on a
desktop and copy it in (step 4). Bolt no longer ships a Linux zip (Linux builds
are Flatpak only), so it isn't run inside the container.

- **Windows (Jagex Launcher):** Start menu → **RuneLite (configure)** → add
  `--insecure-write-credentials` to *Client arguments* → Save. Launch RuneLite from
  the Jagex Launcher and log in once. The file is
  `%USERPROFILE%\.runelite\credentials.properties`.
- **Linux:** Bolt's Flatpak (`flatpak install flathub com.adamcake.Bolt`) with the
  same argument in its RuneLite launch options → `~/.runelite/credentials.properties`.

Then remove the argument again, so the desktop RuneLite stops writing it.

### 2. Build and start

```
docker compose -f docker/docker-compose.yml build
docker compose -f docker/docker-compose.yml up -d
```

It boots Xvfb + x11vnc, then idles in manual mode (`lib/manual.py`) — it doesn't auto-launch anything.
The web app's **Bot container → Start** launches RuneLite and the bot menu in it (and starts the container
if it's stopped); the commands below do the same by hand. See
[webapp/README.md](../webapp/README.md#bot-container-start--stop).

### 3. Connect a VNC viewer

Point your VNC client at `localhost:5900` (bound to localhost only). Password is
`runetools` by default — override it in `docker/.env` with `VNC_PASSWORD=…`
before starting the container.

The web app shows the same screen on the running account's page (**Watch live**, view only; **Take control**
pauses the bot first — see [webapp/README.md](../webapp/README.md#live-view)). It connects
to x11vnc over the compose network, so it needs `VNC=1`.

### 4. Copy the login in, launch RuneLite

From the repo folder (PowerShell on Windows — Git Bash rewrites the container
paths), then delete the desktop copy:

```
docker compose -f docker/docker-compose.yml exec runetools mkdir -p /home/runetools/.runelite
docker compose -f docker/docker-compose.yml cp <path to>/credentials.properties runetools:/home/runetools/.runelite/credentials.properties
docker compose -f docker/docker-compose.yml exec -u 0 runetools chown -R 1000:1000 /home/runetools/.runelite
docker compose -f docker/docker-compose.yml exec runetools chmod 600 /home/runetools/.runelite/credentials.properties
```

⚠ That file holds your session tokens **in plain text**. Inside the container it
lives only in the local `runetools-userhome` Docker volume; don't keep other copies.
Deleting it (or `docker compose down -v`) logs the container out.

Start RuneLite (it appears in the VNC window; click **Play Now** — no Jagex login
prompt):

```
docker compose -f docker/docker-compose.yml exec -d runetools runelite
```

`runelite` applies the container defaults (FPS cap, JVM flags, GPU plugin off) —
or, if `docker/runelite-profile/` exists, your saved RuneLite and game settings —
on a fresh RuneLite home; see "Keeping RuneLite's settings" below.

RuneLite's state lives in `/home/runetools`, a named Docker volume
(`runetools-userhome`) — it survives `docker compose down` / restarts, so you
shouldn't need to log in again. (`down -v` would wipe it — don't use `-v` unless
you mean to.)

### 5. Recalibrate

The virtual display defaults to 1280x800 (`XVFB_RESOLUTION` in `docker/.env`,
e.g. `XVFB_RESOLUTION=1920x1080x24`; keep the depth at 24 — the bots match exact
colours). Without a window manager RuneLite opens undecorated and centred, so
positions won't match configs calibrated on a normal desktop — and pin the window
position before calibrating ("Window position" below). Start the menu and use
each bot's **⚙ Configure** (and GE / Energy Config):

```
docker compose -f docker/docker-compose.yml exec -d runetools python3 run.py
```

The repo is bind-mounted at `/app`, so configs land back in your working tree,
same gitignored files as before. Energy digit templates: `python3
calibrate_energy_digits.py` (see the main README's "Stamina potions" section).

## Running the bot

Start the menu (as above, or **Start** in the web app's Bot container panel), pick a bot in the overlay
(via VNC or the web app's live view). Then
disconnect VNC and leave it running. Press **O** in the VNC window to pause,
**P** to force-stop. Session logs land in `<bot>/log/` in your working tree —
`python -m lib.logreport` on the host reads them.

## Unattended mode

Set a bot in `docker/.env` and the container runs it with nobody watching:
`lib.headless` keeps RuneLite logged in, runs the bot, restarts it after crashes
and logouts, and comes back by itself after a container or host restart. After
every fresh login it zooms the camera all the way out and tilts it to look from
the top (`lib.camera.zoom_out_top_down`) — the view to calibrate the bots in.

### One-time setup

1. **Save your login** — `credentials.properties` in the container, see
   "One-time setup" steps 1 and 4 above.
2. **Capture the login templates** (once, and again if Jagex restyles a screen):
   `python3 run.py` → **⚙ Client Templates**, then drag a rectangle (via VNC) over
   each element while it is on screen:

   | template | what to select |
   |---|---|
   | `terms_accept` | the terms dialog's **Accept** button (first start of a fresh profile only; optional) |
   | `login_play` | the login screen's **Play Now** button |
   | `welcome_play` | the red **CLICK HERE TO PLAY** button after logging in |
   | `in_game` | a **fixed** in-game element: the bottom row of side-panel tab icons works (it still matches whichever tab is open). **Not the compass** (it rotates with the camera, which the bots turn) and nothing with changing numbers (orbs, XP) |

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
| `docker/botctl pause` / `resume` | pause / resume (each is a no-op if already in that state) |
| `docker/botctl stop` | finish the current trip, then idle |
| `docker/botctl kill` | stop right now (same as P), then idle |
| `docker/botctl start` | resume, or leave idle: log in if needed and start the bot |
| `docker/botctl status` | recent sessions + supervisor events |
| `docker/botctl profile-save` / `profile-load` | save / restore RuneLite's plugins + settings (see "Keeping RuneLite's settings") |
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

## Testing on Windows

Same container, Docker Desktop instead of Ubuntu's Docker. Use **Git Bash** (comes
with Git for Windows) for the commands below.

1. **Get the code** — `git clone https://github.com/proofexak/runetools` (or
   `git pull`). If this clone existed *before* `.gitattributes` was added, re-check
   out the container scripts once so they get LF line endings (CRLF breaks them
   with `bad interpreter: /bin/bash^M`):
   ```
   rm docker/entrypoint.sh docker/runelite docker/botctl docker/measure.sh
   git checkout -- docker/
   ```
2. **Docker Desktop** (WSL2 backend) running; Settings → Resources: ≥ 1.5 GB RAM.
3. **Build and start in manual mode** (no `BOT` in `docker/.env` yet):
   `docker compose -f docker/docker-compose.yml up -d --build`, then connect a VNC
   viewer to `localhost:5900` (password `runetools`). `RUNETOOLS_UID/GID` don't
   matter on Windows.
4. **One-time setup**: your login into the container ("One-time setup" steps 1
   and 4 — RuneLite (configure) + Jagex Launcher), capture the 4 client templates,
   set `BOT` / `LAUNCH` in `docker/.env`, `docker compose … up -d`.
5. **The test** (PRO-85's "done when"):
   - leave it running **1 h+** while you use the PC normally;
   - `docker/botctl pause`, `resume`, `stop`, `start` — each should do what it says;
   - `docker compose -f docker/docker-compose.yml restart` — it should relaunch
     RuneLite, log back in and start the bot by itself, configs intact.
6. **Bring back** (paste into the Claude chat on the Ubuntu machine):
   ```
   docker/botctl status
   docker compose -f docker/docker-compose.yml exec runetools python3 -m lib.logreport session latest
   docker compose -f docker/docker-compose.yml logs --tail 50
   ```
   The `.jsonl` session logs are also in your working tree (`<bot>/log/`).

## Settings (`docker/.env`)

| variable | default | |
|---|---|---|
| `VNC` | `1` | `0` = no VNC server (fully unattended; the web app's live view goes dark) |
| `VNC_PASSWORD` | `runetools` | also handed to the web app for its live view |
| `XVFB_RESOLUTION` | `1280x800x24` | keep depth 24 |
| `RUNELITE_FPS` | `30` | frame cap seeded on a fresh RuneLite profile; `0` = no cap |
| `RUNELITE_JAVA_OPTS` | `-Xmx512m -XX:+UseSerialGC` | client JVM flags |
| `RUNETOOLS_UID` / `RUNETOOLS_GID` | `1000` | your `id -u` / `id -g` on Linux |
| `BOT` / `LAUNCH` / `VALUE` | unset | unattended mode (see above); unset = manual mode |
| `TZ` | `UTC` | web app: the zone the bots' logs are in (decides when "today" starts) |
| `POSTGRES_PASSWORD` | `runetools` | web app database (only reachable on localhost) |

The compose file also has the web app (`postgres` + `webapp`, [webapp/README.md](../webapp/README.md)):
`docker compose up -d` starts it along with the bot container; `up -d postgres webapp` starts only it.

`RUNELITE_FPS` and "GPU plugin off" only apply to a **fresh** profile (RuneLite
reads them once from `settings.properties`); on an existing one, set them in
RuneLite's settings (FPS Control plugin, GPU plugin).

## Keeping RuneLite's settings across containers

RuneLite's profile — which plugins are on, every plugin's settings, the Plugin
Hub list (RuneLite re-downloads those plugins itself), window/game size — lives
in the `runetools-userhome` volume, so a new volume (new machine, `down -v`)
starts from scratch. Save it into the repo once it's how you want it:

```
docker/botctl profile-save    # → docker/runelite-profile/ (gitignored, per user)
```

RuneLite writes changed settings to disk with a delay — close it, or wait ~30 s
after the last change, before saving. A container whose RuneLite home is fresh
starts with the saved profile automatically (`RUNELITE_FPS` is then not applied —
the saved FPS Control settings are). To put it back into an existing container:
close RuneLite, `docker/botctl profile-load`, start RuneLite. Either way the GPU
plugin is forced off.

**Window position.** Calibrated points are absolute screen coordinates, so the
RuneLite window must open in the same place every time. RuneLite only stores its
position on a normal window close (never in a container, where it's stopped by a
signal), so without a stored position it opens centred — wherever the window
happened to be when you calibrated is lost on the next restart. Pin it in the
saved profile, `x\:y\:width\:height` as `xwininfo` reports the window:

```
docker compose -f docker/docker-compose.yml exec runetools sh -c 'xwininfo -root -tree | grep "RuneLite -"'
# … 1231x668+369+199 …  →  in docker/runelite-profile/default-*.properties:
runelite.clientBounds=369\:199\:1231\:668
```

Profile files from a desktop RuneLite (`%USERPROFILE%\.runelite\profiles2\` on
Windows) can be dropped into `docker/runelite-profile/` the same way — copy the
whole folder (`profiles.json` + all `.properties`), never `credentials.properties`.

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
