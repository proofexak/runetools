# RuneTools web app

Per-account bot stats and an encrypted login vault, in the browser:

- **Dashboard**: what is running right now (bot, the state it's in and for how long, paused or not, active time),
  hours and runs for today and the last 7 days,
  crashes, a 14-day hours-by-bot chart, today by bot, recent sessions. Everything can be filtered to one account.
- **Sessions**: a filterable list (account, bot, status, dates). Each session's page has its step timeline, time per
  state, failed steps and tracebacks.
- **Bot stats**: `python -m lib.logreport stats` as a page: runs/h, failure rate per state, recoveries/h, stop reasons
  and crash types.
- **Accounts**: add, rename and delete accounts, and pick the one new bot sessions are tagged with. The vault stores
  an email + password + notes per account, which you can see and copy once it's unlocked with the master password.
- **Settings**: app password, vault master password, reset the vault, and the folders whose logs are read.

## Run it

```
docker compose -f docker/docker-compose.yml up -d postgres webapp
```

Open <http://127.0.0.1:8778/>. On the first visit you create the login for the app. On Linux, create `data/` in the
repo first (`mkdir -p data`) so it belongs to you and not root.

Set `TZ` in `docker/.env` to the time zone the bots run in (e.g. `TZ=Europe/Warsaw`). The logs hold local wall time
with no zone, so this setting decides when "today" starts. "Running now" doesn't depend on it: it uses the log file's
modification time.

## How the data gets in

The session logs the bots write (`<bot>/log/*.jsonl` and `<group>/<bot>/log/*.jsonl`, see `lib/events.py`) are the
source of truth. The API **tails** them: it checks for changes every 2 s and reads only whole lines. Each file's read
position (cursor) is saved in the same transaction as the rows it produced. On the first start every existing log is
backfilled, and a restart picks up where it left off. The numbers follow the same rules as
`lib/logreport.summarize`.

For live status the bots also **push** each line right after writing it (`POST /api/ingest`), with the file's key
and the line's byte offset, so the dashboard shows a new state or a pause within about a second. A pushed line is
applied only if its offset is exactly the file's cursor: behind it, the tailer already had it; ahead of it, lines were
missed and the file is re-read. Either way nothing counts twice. The push never slows a bot down: it runs on a
background thread with a short timeout and no retries, and drops lines when the app is down (the tailer catches up
from the file). Bots push to `RUNETOOLS_APP_URL` (default `http://127.0.0.1:8778`; compose sets
`http://webapp:8778` for the bot container; empty turns pushing off) with the token the app writes to
`data/bot_token` on start. If there's no token, they don't push.

Sessions send a `heartbeat` every 30 s, so a session with no `session_end` is running while its log keeps being
written (killed after 90 s of silence). Logs from before heartbeats keep the old rule: running if the log was written
in the last 15 min.

The active account goes the other way. The app writes it to `data/active_account`, and `lib/accounts.py` reads it at
every session start and records it as `account` in `session_start`. `RUNETOOLS_ACCOUNT` overrides the file (one
container per account). Sessions logged without an account show as *Unassigned*. Renaming an account renames it in
the existing history too. Deleting one keeps its sessions under the old name.

## Security

- The server listens on 127.0.0.1 only (in Docker it binds 0.0.0.0, published on 127.0.0.1:8778 only). It refuses
  requests whose `Host` isn't one of its own addresses (DNS rebinding) and refuses to be framed
  (`X-Frame-Options: DENY`, CSP `frame-ancestors 'none'`).
- App login: argon2id password hash and a random session cookie (`httpOnly`, `SameSite=Strict`, only its SHA-256 is
  stored). Every mutating request also needs the session's CSRF token, and a same-site `Origin` when the browser sends
  one. Password endpoints are rate-limited.
- Vault: the master password goes through argon2id (64 MiB, 3 passes) to make an AES-256-GCM key. Each login is
  encrypted with a fresh nonce and bound to its account (AAD). The key lives only in the server's memory while the
  vault is unlocked. It locks after 10 minutes without use, on logout and on restart. **The master password can't be
  recovered.** If you forget it, Settings → *Reset the vault* deletes the stored logins (this needs the app password).
- `POST /api/ingest` is the one route without the login cookie: it takes the bot token (`data/bot_token`, 256 random
  bits, file mode 600) as `Authorization: Bearer …` instead, with no CSRF or Origin check, since bots send neither.
  The Host check still applies (compose adds `webapp:8778` for the bot container). It only accepts lines of a session
  log that exists under the first log folder.
- The bots never use the stored logins. They log in through RuneLite's saved Jagex session.

## Develop

Needs Node 22+ and pnpm 10 (`npm i -g pnpm`). Run from `webapp/`:

```
pnpm install
docker compose -f ../docker/docker-compose.yml up -d postgres   # Postgres on 127.0.0.1:5433
pnpm dev            # API on :8778 (tsx watch) + Vite on http://127.0.0.1:5173 (proxies /api)
pnpm test           # API tests on an in-memory PGlite (same SQL as Postgres) + web unit tests
pnpm e2e            # Playwright: builds the UI, runs the real server on generated logs
pnpm typecheck
```

`pnpm exec playwright install chromium` once, before the first `pnpm e2e`.

Layout:

```
packages/shared   zod schemas + API types used by both sides
apps/api          Fastify + Drizzle
  src/db/schema.ts      tables + the daily_activity view (hours/runs per account/bot/day, split at midnight)
  drizzle/              SQL migrations, applied at startup. After a schema change: pnpm db:generate
  src/ingest/           parse.ts (logreport's line rules), apply.ts (events → rows), ingester.ts (polling, cursors,
                        pushed lines)
  src/routes/ingest.ts  POST /api/ingest (bot token from src/bot-token.ts)
  src/stats.ts          overview / sessions / bot stats queries
  src/vault/            crypto.ts (argon2id + AES-GCM), vault.ts (in-memory key, auto-lock)
  src/accounts.ts       accounts + data/active_account
apps/web          React + Vite + TanStack Query + React Router + Tailwind (shadcn-style components in src/components/ui)
e2e/              Playwright specs + start-server.mjs
```

API settings (environment variables): `DATABASE_URL` (Postgres, or `pglite:memory` / `pglite:<dir>`), `HOST`, `PORT`
(8778), `LOG_ROOTS` (default: the repo; Settings can override it), `DATA_DIR` (default: `<repo>/data`),
`ALLOWED_HOSTS`, `POLL_MS`, `COOKIE_SECURE=1` behind HTTPS, `PASSWORD_RATE_LIMIT` (per minute).
