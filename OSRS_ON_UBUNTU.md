# Installing Old School RuneScape on Ubuntu

Getting OSRS running on Ubuntu (tested on 20.04 LTS, X11 — see the note at the bottom about
Wayland) needs two things:

1. **RuneLite** — the actual game client, and required anyway for `runetools`' bot
   automation, which relies on RuneLite's NPC/tile highlight colours.
2. **A way to log in with a Jagex account** — the official Jagex Launcher is a Windows app
   and doesn't run reliably here (see "What didn't work" below). Use **Bolt**, a native
   third-party launcher, instead.

## 1. Install RuneLite

```bash
sudo snap install runelite
```

Launch it any time with:

```bash
runelite
```

or search "RuneLite" in GNOME Activities.

## 2. Install Bolt (Jagex account login + client launcher)

Bolt (https://github.com/Adamcake/Bolt, maintained by the same person who publishes
RuneLite) logs into a Jagex account and can launch RuneLite/the official client/HDOS with
that session — it replaces the official Jagex Launcher, which doesn't run here.

### 2a. Ubuntu 20.04's stock `flatpak` is too old — upgrade it first

Flathub's package index is now too large for Ubuntu 20.04's default `flatpak` (1.6.5) to
parse (`error: Unable to load summary from remote flathub: URI ... exceeded maximum size`).
Fix: pull a newer `flatpak` from the official Flatpak PPA.

```bash
sudo add-apt-repository -y ppa:flatpak/stable
sudo apt update
sudo apt install -y flatpak
```

**If `add-apt-repository` fails with `Error: retrieving gpg key timed out`** (the
Launchpad keyserver is flaky), fetch the key manually over HTTPS instead of the keyserver
protocol:

```bash
curl -sL "https://keyserver.ubuntu.com/pks/lookup?op=get&options=mr&search=0x5C6D153A17C02C337EF6C663B8B9D41229DFA5F5" \
  | gpg --dearmor | sudo tee /etc/apt/trusted.gpg.d/flatpak-ppa.gpg > /dev/null
sudo apt update
sudo apt install -y flatpak
```

(That fingerprint is the official `ppa:flatpak/stable` signing key — verify it still
matches the one shown at https://launchpad.net/~flatpak/+archive/ubuntu/stable before
trusting it, in case it's ever rotated.)

Confirm the upgrade worked (should print 1.16.x or newer, not 1.6.5):

```bash
flatpak --version
```

### 2b. Add Flathub and install Bolt

```bash
flatpak remote-add --if-not-exists flathub https://flathub.org/repo/flathub.flatpakrepo
flatpak install -y flathub com.adamcake.Bolt
```

This pulls down a sandboxed CEF/Chromium runtime plus Bolt itself — a few hundred MB, give
it a few minutes.

### 2c. Run it

```bash
flatpak run com.adamcake.Bolt
```

Log in with your Jagex account inside Bolt, then use it to launch RuneLite (or the
official/HDOS client). It'll also show up as an app named "Bolt Launcher" in GNOME
Activities.

## What didn't work (skip unless troubleshooting from scratch)

Documented so a future attempt doesn't repeat the same dead ends:

- **Official Jagex Launcher installer via Proton/Wine**: the installer immediately errors
  with *"The version of Internet Explorer on this machine is not supported."* This is a
  known, unfixable-in-practice issue — the installer's embedded IE/mshtml version check
  fails under Wine regardless of registry hacks (`svcVersion`/`Version` keys under
  `HKLM\Software\Microsoft\Internet Explorer`). Confirmed via the WineHQ forums and the
  community tracker at https://github.com/TormStorm/jagex-launcher-linux.
- **Bolt's raw Linux binary release** (`Bolt-Linux.zip` from
  https://codeberg.org/Adamcake/Bolt/releases, not via Flatpak): fails to start —
  `error while loading shared libraries: libffi.so.8: cannot open shared object file`, and
  after manually supplying `libffi.so.8`, a deeper wall: it needs `GLIBC_2.34`+ and
  `GLIBCXX_3.4.32`+, but Ubuntu 20.04 only ships glibc 2.31. Unlike `libffi`, glibc itself
  can't safely be swapped out on a running system — this path is a dead end on 20.04
  without a full OS upgrade. The Flatpak route sidesteps this entirely because Flatpak
  bundles its own compatible runtime inside the sandbox, independent of the host's glibc
  version — hence installing Bolt through Flatpak (§2) instead of the raw binary.
- **Codeberg blocks automated/bot HTTP requests** to release download pages (returns a
  deliberate garbage tarpit page with a message addressed to "AI scrapers"). The Bolt zip
  had to be downloaded manually via a real browser (Firefox), not `curl`.

## Environment notes

- **X11 required, not Wayland.** `runetools`' mouse/keyboard automation (`pyautogui`,
  `pynput`) and screen capture (`mss`) depend on X11 protocols (XTest for input synthesis)
  that don't work the same way under Wayland. Check with `echo $XDG_SESSION_TYPE`.
- Proton/Steam automation *would* work fine for input injection and screen capture on an
  X11 setup in principle (Wine windows are ordinary X11 windows) — the blocker here was
  specifically the Jagex Launcher installer's broken IE version check, not X11/Proton
  compatibility in general.
