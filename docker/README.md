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

⚠ Both log the account in from your desktop — its launcher and your home IP. For an
account that should only ever be seen from its proxy ("Accounts" below), this login
has to happen inside its container instead; that path isn't built yet.

Then remove the argument again, so the desktop RuneLite stops writing it.

### 2. Build and start

The web app stack (`postgres` + `webapp`, which owns the `runetools-net` network)
runs once; every account's bot is its own stack ("Accounts" below):

```
docker compose -f docker/docker-compose.yml up -d --build
docker/botctl new <account>      # → docker/accounts/<account>.env: fill in its PROXY + EXPECT_IP
docker/botctl <account> up
```

The bot container boots Xvfb + x11vnc, then idles in manual mode (`lib/manual.py`) — it doesn't auto-launch anything.
The web app's **Bot container → Start** launches RuneLite and the bot menu in it (and starts the container
if it's stopped); the commands below do the same by hand. See
[webapp/README.md](../webapp/README.md#bot-container-start--stop).

### 3. Connect a VNC viewer

Point your VNC client at `localhost:<VNC_PORT>` — the account file's, 5900 for the
first account (bound to localhost only). Password is
`runetools` by default — override it in `docker/.env` with `VNC_PASSWORD=…`
before starting the container.

The web app shows the same screen on the running account's page (**Watch live**, view only; **Take control**
pauses the bot first — see [webapp/README.md](../webapp/README.md#live-view)). It connects
to x11vnc over the compose network, so it needs `VNC=1`.

### 4. Copy the login in, launch RuneLite

From the repo folder (PowerShell on Windows — Git Bash rewrites the container
paths), then delete the desktop copy:

```
docker/botctl <account> compose exec runetools mkdir -p /home/runetools/.runelite
docker/botctl <account> compose cp <path to>/credentials.properties runetools:/home/runetools/.runelite/credentials.properties
docker/botctl <account> compose exec -u 0 runetools chown -R 1000:1000 /home/runetools/.runelite
docker/botctl <account> compose exec runetools chmod 600 /home/runetools/.runelite/credentials.properties
```

⚠ That file holds your session tokens **in plain text**. Inside the container it
lives only in the account's home volume (`rt-<account>_userhome`); don't keep other
copies. Deleting it (or `docker/botctl <account> compose down -v`) logs the container out.

Start RuneLite (it appears in the VNC window; click **Play Now** — no Jagex login
prompt):

```
docker/botctl <account> compose exec -d runetools runelite
```

`runelite` applies the container defaults (FPS cap, JVM flags, GPU plugin off) —
or, if `docker/runelite-profile/` exists, your saved RuneLite and game settings —
on a fresh RuneLite home; see "Keeping RuneLite's settings" below.

RuneLite's state lives in `/home/runetools`, the account's named Docker volume
(`rt-<account>_userhome`) — it survives `docker/botctl <account> down` / restarts, so you
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
docker/botctl <account> compose exec -d runetools python3 run.py
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

Set a bot in an account's file and its container runs it with nobody watching:
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
3. **Pick the bot** in `docker/accounts/<account>.env` — names as shown in the menu:
   ```
   BOT=Tanning
   LAUNCH=Green Dragonhide
   VALUE=Al Kharid  # launches that ask: Tanning "Where are you?" (Al Kharid / GE), Choco Grind a number
   ```
   then `docker/botctl <account> up`. Remove `BOT` to go back to manual mode (the
   container just idles, as before).

### Control: `docker/botctl`

| command | effect |
|---|---|
| `docker/botctl accounts` | every account: IP, MAC, hostname, VNC port, running? |
| `docker/botctl new <account>` | a new account file with a fresh MAC, hostname and VNC port ("Accounts" below) |
| `docker/botctl <account> up` / `down` | check the account file, then build + start its stack / stop and remove it (exits cleanly; the home volume stays) |
| `docker/botctl <account> pause` / `resume` | pause / resume (each is a no-op if already in that state) |
| `docker/botctl <account> stop` | finish the current trip, then idle |
| `docker/botctl <account> kill` | stop right now (same as P), then idle |
| `docker/botctl <account> start` | resume, or leave idle: log in if needed and start the bot |
| `docker/botctl <account> status` | recent sessions + supervisor events |
| `docker/botctl <account> ip` | the public IP (and ISP) its container goes out with |
| `docker/botctl <account> browser [url]` | Firefox on its virtual display ("Web browser" below) |
| `docker/botctl <account> profile-save` / `profile-load` | save / restore RuneLite's plugins + settings (see "Keeping RuneLite's settings") |
| `docker/botctl <account> compose …` | any `docker compose` command on its stack (`exec`, `logs`, `ps`, …) |

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

### Schedule mode (PRO-102)

Instead of one bot until it stops, the container can play the account's **schedule** from the web app (account
page → Schedule: hours a month, timezone, activities): put `SCHEDULE=1` in `docker/accounts/<account>.env` instead
of `BOT` / `LAUNCH` / `VALUE`, then `docker/botctl <account> up`.

- The web app writes the plan to `data/schedules/<account>.json`; the container re-reads it at least every minute,
  so an edit or Regenerate needs no restart.
- Between blocks RuneLite is closed (logged out). When a block starts it logs in and runs that block's bot and
  launch; at the block's end the bot gets the soft stop (it finishes its trip), and 20 min later a hard stop if
  it's still going.
- A crash inside a block restarts as above; one after the block's end doesn't. A bot that ends `done` sits out
  the rest of its block. A block naming a bot or launch the menu doesn't have is skipped (`schedule_skip`).
- `botctl stop` / `kill` still idle it until `botctl start`; the schedule's Off switch keeps it logged out.
- `botctl status` / `python -m lib.logreport supervisor` show `schedule_wait`, `schedule_block`,
  `schedule_logout`, `schedule_skip`.

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
3. **Build and start in manual mode** (no `BOT` in the account file yet): step 2 of
   "One-time setup", then connect a VNC viewer to `localhost:5900` (password `runetools`). `RUNETOOLS_UID/GID` don't
   matter on Windows.
4. **One-time setup**: your login into the container ("One-time setup" steps 1
   and 4 — RuneLite (configure) + Jagex Launcher), capture the 4 client templates,
   set `BOT` / `LAUNCH` in the account file, `docker/botctl <account> up`.
5. **The test** (PRO-85's "done when"):
   - leave it running **1 h+** while you use the PC normally;
   - `docker/botctl <account> pause`, `resume`, `stop`, `start` — each should do what it says;
   - `docker/botctl <account> compose restart` — it should relaunch
     RuneLite, log back in and start the bot by itself, configs intact.
6. **Bring back** (paste into the Claude chat on the Ubuntu machine):
   ```
   docker/botctl <account> status
   docker/botctl <account> compose exec runetools python3 -m lib.logreport session latest
   docker/botctl <account> compose logs --tail 50
   ```
   The `.jsonl` session logs are also in your working tree (`<bot>/log/`).

## Settings (`docker/.env`)

Shared by the web app stack and every account's bot. An account's file
(`docker/accounts/<account>.env`) can set any of them for that account alone — it's
read after `docker/.env` — and holds what must differ per account ("Accounts" below).

| variable | default | |
|---|---|---|
| `VNC` | `1` | `0` = no VNC server (fully unattended; the web app's live view goes dark) |
| `VNC_PASSWORD` | `runetools` | also handed to the web app for its live view |
| `XVFB_RESOLUTION` | `1280x800x24` | keep depth 24 |
| `RUNELITE_FPS` | `30` | frame cap seeded on a fresh RuneLite profile; `0` = no cap |
| `RUNELITE_JAVA_OPTS` | `-Xmx512m -XX:+UseSerialGC` | client JVM flags |
| `RUNETOOLS_UID` / `RUNETOOLS_GID` | `1000` | your `id -u` / `id -g` on Linux |
| `BOT` / `LAUNCH` / `VALUE` | unset | unattended mode (see above), in the account file; unset = manual mode |
| `SCHEDULE` | unset | `1` = schedule mode (the web app's plan for the account, "Schedule mode" above), in the account file |
| `BOT_ACCOUNT` | unset | the account whose bot the web app's live view and Start / Stop control |
| `TZ` | `UTC` | bot container + web app: the zone the logs are written in (the app's "today") and the browser's clock — set it to the proxy's country |
| `POSTGRES_PASSWORD` | `runetools` | web app database (only reachable on localhost) |

`docker/docker-compose.yml` is the web app stack (`postgres` + `webapp` + `dockerproxy`,
[webapp/README.md](../webapp/README.md)); the bots are `docker/bot.yml`, one stack per account.

`RUNELITE_FPS` and "GPU plugin off" only apply to a **fresh** profile (RuneLite
reads them once from `settings.properties`); on an existing one, set them in
RuneLite's settings (FPS Control plugin, GPU plugin).

## Accounts

Each account has its own IP, identity and home — `docker/accounts/<account>.env`
(gitignored: the proxy password is in it; template `account.env.example`), run as its
own stack, compose project `rt-<account>` (`docker/bot.yml`):

| in the account file | |
|---|---|
| `PROXY` | the proxy all its traffic goes through ("Fixed IP through a proxy") |
| `EXPECT_IP` | the IP that proxy gives it; RuneLite and Firefox won't start from any other |
| `BOT_MAC` / `BOT_HOSTNAME` | a fixed, ordinary-looking identity instead of Docker's `02:42:…` MAC and a hostname that changes with every recreate |
| `VNC_PORT` | its VNC port on 127.0.0.1 |
| `BOT` / `LAUNCH` / `VALUE` | unattended mode |
| `SCHEDULE=1` | schedule mode instead of `BOT` |

```
docker/botctl new alt2        # fresh MAC (Intel's 10:F0:05 + 3 random bytes), Ubuntu-style hostname, next VNC port
docker/botctl accounts        # who has which IP / MAC / hostname / port, which are running
docker/botctl alt2 up
```

`up` refuses an account whose `PROXY` / `EXPECT_IP` aren't filled in, or whose
`PROXY`, `EXPECT_IP`, `BOT_MAC`, `BOT_HOSTNAME` or `VNC_PORT` is another account's.
Its home volume `rt-<account>_userhome` holds its RuneLite login and browser profile;
its session logs are tagged with the account name (`RUNETOOLS_ACCOUNT`). A fresh home is
seeded from the saved RuneLite profile without its per-account file (`$rsprofile*`).
The MAC never leaves the local network — it only matters to software reading it
inside the container. Never use your own card's MAC or your PC's name.

**One account runs at a time for now:** the bots share `data/` (the web app's
Take control / Start hand-over files), so `up` refuses while another account's stack is
running, and the web app controls only `BOT_ACCOUNT` (`docker/.env`; after changing it,
`docker compose -f docker/docker-compose.yml up -d`).

## Fixed IP through a proxy

The bot container has no network of its own: it uses its `proxy` service's
(tun2socks), which sends **all** its traffic — RuneLite, its launcher, Firefox,
anything else — through `PROXY`. If the proxy goes down, connections fail; they never
fall back to the host's IP. `runetools-net` stays direct (web app push, live view,
VNC). DNS lookups go through Docker's resolver, i.e. the host's — the game servers
never see those.

In the account file:

```
PROXY=socks5://USER:PASSWORD@HOST:PORT
EXPECT_IP=203.0.113.7
```

`PROXY` from the provider's dashboard (URL-encode `@ : / #` in the password: `%40 %3A
%2F %23`), `EXPECT_IP` the IP it gives you; no comments after a value. Then
`docker/botctl <account> up`, and check — this must show `EXPECT_IP` and the proxy's
ISP, not your own:

```
docker/botctl <account> ip
```

`runelite` and `browser` check the public IP first (`docker/check-ip`) and refuse to
start on any other answer (unattended mode then retries with its backoff).

## Looking like a laptop

What the bot container shows the programs in it, made to look like an ordinary Ubuntu
laptop rather than a Docker container:

| | instead of Docker's | done by |
|---|---|---|
| a Linux user of its own (`BOT_USER`, default the hostname's first part), home `/home/<user>` | `ubuntu` (a cloud server's default), home `/home/runetools`, `JAVA_TOOL_OPTIONS` | `botctl <account> up` → `docker/accounts/<account>/passwd` + `group`; the entrypoint links the home to the volume |
| its own `/etc/machine-id`, made once | the image's, the same in every container | `docker/accounts/<account>/machine-id` |
| network `enp0s31f6` on a home-router range (`192.168.88.x`), tunnel `tun0` on `10.8.0.2` | `eth0` on `172.x`, tunnel on `198.18.0.1` | `docker/proxy-start`, `NIC_NAME`; the subnet in `docker-compose.yml` |
| RuneLite and Firefox start with a clean, desktop-like environment | every container setting (`BOT`, `VNC_PASSWORD`, `EXPECT_IP`, …) | `docker/runelite`, `docker/browser` |
| Java's `os.version` = an Ubuntu 24.04 kernel (`OS_VERSION`, default `6.8.0-85-generic`) | Docker Desktop's `…-microsoft-standard-WSL2` | `docker/runelite` |
| Firefox: Polish, the Ubuntu + Noto + emoji fonts, WebGL (CPU renderer), DNS over HTTPS through the proxy | English, 6 fonts, no WebGL, DNS through the host's resolver | `docker/Dockerfile`, `docker/firefox-prefs.js` |

Left as Docker's: `/.dockerenv`, `docker` paths in `/proc/self/mountinfo`, the CPU's
`hypervisor` flag and no DMI hardware info (Docker Desktop's VM), no window manager
(a page's `screen.availHeight` = the full screen), and the process list (Xvfb,
x11vnc, the bot's Python). None of that reaches a website.

## Web browser

The image has Firefox (from Mozilla's repository; build with `--build-arg
BROWSER=0` to leave it out) for things that should come from the container's IP,
not your desktop's — signing up an account, the Jagex login:

```
docker/botctl <account> browser [url]
```

It appears on the virtual display (VNC / the web app's live view). Like RuneLite,
it goes through `PROXY` and won't start unless the IP is `EXPECT_IP`. Its profile
(cookies, logins) lives in the home volume. Set `TZ` in `docker/.env` to the proxy's
country (e.g. `Europe/Warsaw`): the browser reports its clock's zone, and the web app
uses the same `TZ`.

**Not while a bot runs**: it covers the game, and **O** / **P** typed into it pause /
stop the bot. Use manual mode (`BOT` unset in the account file) with the menu closed, and close
Firefox before starting a bot.

## Keeping RuneLite's settings across containers

RuneLite's profile — which plugins are on, every plugin's settings, the Plugin
Hub list (RuneLite re-downloads those plugins itself), window/game size — lives
in the account's home volume, so a new volume (new account, new machine, `down -v`)
starts from scratch. Save it into the repo once it's how you want it:

```
docker/botctl <account> profile-save    # → docker/runelite-profile/ (gitignored, per user)
```

RuneLite writes changed settings to disk with a delay — close it, or wait ~30 s
after the last change, before saving. A container whose RuneLite home is fresh
starts with the saved profile automatically (`RUNELITE_FPS` is then not applied —
the saved FPS Control settings are). To put it back into an existing container:
close RuneLite, `docker/botctl <account> profile-load`, start RuneLite. Either way the GPU
plugin is forced off.

**Window position.** Calibrated points are absolute screen coordinates, so the
RuneLite window must open in the same place every time. RuneLite only stores its
position on a normal window close (never in a container, where it's stopped by a
signal), so without a stored position it opens centred — wherever the window
happened to be when you calibrated is lost on the next restart. Pin it in the
saved profile, `x\:y\:width\:height` as `xwininfo` reports the window:

```
docker/botctl <account> compose exec runetools sh -c 'xwininfo -root -tree | grep "RuneLite -"'
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
docker/botctl <account> down                       # one account's bot
docker compose -f docker/docker-compose.yml down   # the web app stack
```
