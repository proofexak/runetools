/**
 * End to end against the real server + built UI (see start-server.mjs for the data).
 * The tests share one server and run in order: first-run setup happens in the first.
 */
import fs from "node:fs";
import path from "node:path";
import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

const ROOT = process.env.E2E_ROOT!;
const PASSWORD = "correct horse";
const NEW_PASSWORD = "battery staple";
let appPassword = PASSWORD;

async function logIn(page: Page) {
  await page.goto("/");
  const setup = page.getByRole("button", { name: "Create login" });
  const login = page.getByRole("button", { name: "Log in" });
  await expect(setup.or(login)).toBeVisible();
  if (await setup.isVisible()) {
    await page.getByLabel("Password", { exact: true }).fill(PASSWORD);
    await page.getByLabel("Repeat password").fill(PASSWORD);
    await setup.click();
  } else {
    await page.getByLabel("Username").fill("admin");
    await page.getByLabel("Password").fill(appPassword);
    await login.click();
  }
  await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();
}

const nav = (page: Page, name: string) => page.getByRole("navigation").getByRole("link", { name }).click();

/** A bot session the way lib/events.py writes it: append the line, then POST it with its byte offset. */
function botSession(request: APIRequestContext, dir: string, bot: string) {
  const token = fs.readFileSync(path.join(ROOT, "data", "bot_token"), "utf8").trim();
  const p = (n: number, w = 2) => String(n).padStart(w, "0");
  const wall = (d: Date) => `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:` +
    `${p(d.getMinutes())}:${p(d.getSeconds())}.${p(d.getMilliseconds(), 3)}`;
  const stamp = wall(new Date()).slice(0, 19).replace(/[-:]/g, "").replace("T", "_");
  const key = `${dir}/log/${bot}_${stamp}.jsonl`;
  const file = path.join(ROOT, "repo", ...key.split("/"));
  fs.mkdirSync(path.dirname(file), { recursive: true });
  return async (event: Record<string, unknown>) => {
    const line = JSON.stringify({ ts: wall(new Date()), session: stamp, bot, ...event });
    const offset = fs.existsSync(file) ? fs.statSync(file).size : 0;
    fs.appendFileSync(file, `${line}
`);
    const res = await request.post("/api/ingest", {
      headers: { authorization: `Bearer ${token}` }, data: { file: key, offset, line },
    });
    expect(res.status()).toBe(200);
    expect(["applied", "duplicate"]).toContain((await res.json()).result);   // duplicate: the tailer was quicker
  };
}

/** A "Running now" card on the dashboard or an account page. */
const sessionCard = (page: Page, bot: string) => page.getByTestId("live-session").filter({ hasText: bot }).first();

test.describe.configure({ mode: "serial" });

test("first run: create the app login, then the dashboard shows the backfilled logs", async ({ page }) => {
  await logIn(page);
  await expect(page.getByText("Running now")).toBeVisible();
  const live = sessionCard(page, "Golden nuggets");
  await expect(live).toContainText("deposit");               // current step of the live session
  await expect(page.getByText("Hours per day")).toBeVisible();
  await expect(page.locator(".recharts-surface")).toBeVisible();
  await expect(page.getByText("Crashes, 7 days").locator("..")).toContainText("1");
  // the chart's table view lists yesterday's 2 h
  await page.getByRole("button", { name: "Table" }).click();
  await expect(page.getByRole("cell", { name: "2h" }).first()).toBeVisible();
});

test("sessions: filter, then a crashed session shows its traceback", async ({ page }) => {
  await logIn(page);
  await nav(page, "Sessions");
  await expect(page.getByText("3 sessions")).toBeVisible();
  await page.getByLabel("Status").selectOption("crashed");
  await expect(page.getByText("1 session", { exact: true })).toBeVisible();
  await page.locator("tbody tr a").first().click();
  await expect(page.getByText("TimeoutError").first()).toBeVisible();
  await expect(page.locator("pre")).toContainText("Ellis never answered");
});

test("accounts: create, set active → data/active_account for the bots", async ({ page }) => {
  await logIn(page);
  await nav(page, "Accounts");
  // Zezima is in the logs already: offered as a one-click add
  await page.getByRole("button", { name: "Zezima" }).click();
  await page.getByRole("button", { name: "Add", exact: true }).click();
  await expect(page.getByRole("cell", { name: /Zezima\s*active/ })).toBeVisible();

  await page.getByRole("button", { name: "Add account" }).click();
  await page.getByLabel("Name").fill("Lynx Titan");
  await page.getByRole("button", { name: "Add", exact: true }).click();
  await expect(page.getByRole("cell", { name: "Lynx Titan", exact: true })).toBeVisible();

  const file = path.join(ROOT, "data", "active_account");
  await expect.poll(() => fs.readFileSync(file, "utf8")).toBe("Zezima\n");
  await page.getByLabel("Active account").selectOption({ label: "Lynx Titan" });
  await expect.poll(() => fs.readFileSync(file, "utf8")).toBe("Lynx Titan\n");
  await page.getByLabel("Active account").selectOption({ label: "No account (unassigned)" });
  await expect.poll(() => fs.existsSync(file)).toBe(false);
  await page.getByLabel("Active account").selectOption({ label: "Zezima" });
  await expect.poll(() => fs.existsSync(file)).toBe(true);
});

test("vault: set a master password, store a login, lock, unlock, show and copy", async ({ page }) => {
  await logIn(page);
  await nav(page, "Accounts");
  await page.getByLabel("New master password").fill("vault master pw");
  await page.getByLabel("Repeat it").fill("vault master pw");
  await page.getByRole("button", { name: "Create vault" }).click();
  await expect(page.getByText(/^Unlocked\./)).toBeVisible();

  const row = page.getByRole("row", { name: /Zezima/ });
  await row.getByRole("button", { name: "Add login" }).click();
  await page.getByLabel("Email / username").fill("zezima@example.com");
  await page.getByLabel("Password", { exact: true }).fill("hunter2");
  await page.getByRole("button", { name: "Save" }).click();

  await page.getByRole("button", { name: "Lock now" }).click();
  await expect(row).toContainText("Stored");
  await page.getByLabel("Master password").fill("wrong password");
  await page.getByRole("button", { name: "Unlock" }).click();
  await expect(page.getByText("wrong master password")).toBeVisible();
  await page.getByLabel("Master password").fill("vault master pw");
  await page.getByRole("button", { name: "Unlock" }).click();

  await row.getByRole("button", { name: "Show" }).click();
  await expect(row).toContainText("zezima@example.com");
  await expect(row).not.toContainText("hunter2");            // masked until clicked
  await row.getByTitle("Show password").click();
  await expect(row).toContainText("hunter2");
  await row.getByRole("button", { name: "Copy password" }).click();
  expect(await page.evaluate(() => navigator.clipboard.readText())).toBe("hunter2");
});

test("account page: that account's stats, sessions and login", async ({ page }) => {
  await logIn(page);
  await nav(page, "Accounts");
  await page.getByRole("link", { name: "Zezima" }).click();
  await expect(page.getByRole("heading", { name: "Zezima" })).toBeVisible();
  // Zezima's two sessions (yesterday + today's crash), not the unassigned live miner
  await expect(page.getByText("Nothing running on Zezima right now.")).toBeVisible();
  await expect(page.getByText("Crashes, 7 days").locator("..")).toContainText("1");
  await expect(page.locator("tbody tr")).toHaveCount(2);
  // unlock right here if the vault is locked, then the login shows
  const master = page.getByLabel("Master password");
  const show = page.getByRole("button", { name: "Show" });
  await expect(master.or(show)).toBeVisible();
  if (await master.isVisible()) {
    await master.fill("vault master pw");
    await page.getByRole("button", { name: "Unlock" }).click();
  }
  await show.click();
  await expect(page.getByText("zezima@example.com")).toBeVisible();
  await expect(page.getByRole("link", { name: "All sessions" })).toHaveAttribute("href", "/sessions?account=Zezima");
});

test("live: a new log line shows up without reloading", async ({ page }) => {
  await logIn(page);
  await expect(page.getByText("Running now")).toBeVisible();
  const dir = path.join(ROOT, "repo", "miner", "golden_nuggets", "log");
  const file = path.join(dir, fs.readdirSync(dir)[0]!);
  const last = JSON.parse(fs.readFileSync(file, "utf8").trim().split("\n").at(-1)!);
  fs.appendFileSync(file, JSON.stringify({ ...last, state: "walk_back", run: 3 }) + "\n");
  await expect(sessionCard(page, "Golden nuggets")).toContainText("walk_back", { timeout: 10_000 });
});

test("live status: a bot's pushed state and pause show within a second", async ({ page, request }) => {
  await logIn(page);
  const emit = botSession(request, "choc", "choc");

  // started while Zezima is the active account (lib/accounts.py tags session_start)
  await emit({ event: "session_start", params: {}, pid: 9, account: "Zezima" });
  await emit({ event: "heartbeat", state: "starting", run: 0, paused: false });
  await emit({ event: "state_enter", state: "grind", run: 0 });
  const card = sessionCard(page, "Choc");
  await expect(card.getByTestId("live-state")).toContainText("grind", { timeout: 2000 });
  await expect(card).toContainText("Zezima");

  // another account's page: not its bot
  await nav(page, "Accounts");
  await page.getByRole("link", { name: "Lynx Titan" }).click();
  await expect(page.getByText("Nothing running on Lynx Titan right now.")).toBeVisible();

  // the account's own page shows it, live
  await nav(page, "Accounts");
  await page.getByRole("link", { name: "Zezima" }).click();
  await expect(page.getByRole("heading", { name: "Zezima" })).toBeVisible();
  await expect(card.getByTestId("live-state")).toContainText("grind");
  await emit({ event: "step", state: "grind", result: "ok", seconds: 1, run: 1 });
  await emit({ event: "state_enter", state: "bank", run: 1 });
  await expect(card.getByTestId("live-state")).toContainText("bank", { timeout: 2000 });

  await emit({ event: "pause_start", state: "bank" });
  await expect(card.getByText("Paused")).toBeVisible({ timeout: 2000 });
  await emit({ event: "pause_end", state: "bank" });
  await expect(card.getByText("Paused")).toBeHidden({ timeout: 2000 });

  await emit({ event: "session_end", final: "stopped", reason: null, last_step: "bank", stats: { run: 1 },
    active_seconds: 2, paused_seconds: 0 });
  await expect(page.getByText("Nothing running on Zezima right now.")).toBeVisible({ timeout: 2000 });

  // a push without the bot token is refused
  const res = await request.post("/api/ingest", { data: { file: "choc/log/x.jsonl", offset: 0, line: "{}" } });
  expect(res.status()).toBe(401);
});

test("live view: Watch live on the running account's page; take control waits for the bot's pause", async ({ page, request }) => {
  await logIn(page);
  // not on the dashboard any more: only behind a running session's "Watch live"
  await expect(page.getByText("Running now")).toBeVisible();
  await expect(page.locator("[data-slot=card]", { hasText: "Live view" })).toHaveCount(0);
  await expect(sessionCard(page, "Golden nuggets").getByRole("link", { name: "Watch live" })).toHaveCount(0);  // unassigned

  const emit = botSession(request, "miner/varrock_exp", "varrock_exp");
  await emit({ event: "session_start", params: {}, pid: 11, account: "Zezima" });
  await emit({ event: "state_enter", state: "mine", run: 0 });
  await sessionCard(page, "Varrock exp").getByRole("link", { name: "Watch live" }).click();
  await expect(page.getByRole("heading", { name: "Zezima" })).toBeVisible();
  const card = page.locator("[data-slot=card]", { hasText: "Live view" });
  await expect(card.getByText("Can't reach the bot's screen")).toBeVisible({ timeout: 10_000 });   // no VNC here

  // collapsed again, then opened from the account page itself
  await card.getByRole("button", { name: "Stop watching" }).click();
  await expect(card.getByText("Can't reach the bot's screen")).toBeHidden();
  await card.getByRole("button", { name: "Watch live" }).click();
  await expect(card.getByText("Can't reach the bot's screen")).toBeVisible({ timeout: 10_000 });

  // a bot answers (what lib/live_control.py writes): busy first, then parked in its pause
  const data = path.join(ROOT, "data");
  await card.getByRole("button", { name: "Take control" }).click();
  await expect(card.getByText("Pausing the bot")).toBeVisible();
  const asked = JSON.parse(fs.readFileSync(path.join(data, "live_control.json"), "utf8"));
  expect(asked.held).toBe(true);
  const ack = (safe: boolean) => fs.writeFileSync(path.join(data, "live_control_ack.json"),
    JSON.stringify({ id: asked.id, held: true, safe, pid: 1 }));
  ack(false);
  await page.waitForTimeout(4000);                           // past the no-answer window: still waiting
  await expect(card.getByText("Pausing the bot")).toBeVisible();
  ack(true);
  await expect(card.getByText("the bot is paused until you release it")).toBeVisible();
  await expect(card.getByText("In control")).toBeVisible();

  await card.getByRole("button", { name: "Release" }).click();
  await expect(card.getByRole("button", { name: "Take control" })).toBeVisible();
  expect(JSON.parse(fs.readFileSync(path.join(data, "live_control.json"), "utf8")).held).toBe(false);

  // nobody answers: no bot is running, so control is handed over anyway
  await card.getByRole("button", { name: "Take control" }).click();
  await expect(card.getByText("no bot answered")).toBeVisible({ timeout: 6000 });
  await card.getByRole("button", { name: "Release" }).click();
  await expect(card.getByRole("button", { name: "Take control" })).toBeVisible();

  // another account's page has no screen: it isn't that account's bot
  await nav(page, "Accounts");
  await page.getByRole("link", { name: "Lynx Titan" }).click();
  await expect(page.getByText("Nothing running on Lynx Titan right now.")).toBeVisible();
  await expect(page.locator("[data-slot=card]", { hasText: "Live view" })).toHaveCount(0);

  await emit({ event: "session_end", final: "stopped", reason: null, last_step: "mine", stats: { run: 0 },
    active_seconds: 5, paused_seconds: 0 });
});

test("settings: change the app password; the old one stops working", async ({ page }) => {
  await logIn(page);
  await nav(page, "Settings");
  const card = page.locator("[data-slot=card]", { hasText: "App password" });
  await card.getByLabel("Current").fill(PASSWORD);
  await card.getByLabel("New", { exact: true }).fill(NEW_PASSWORD);
  await card.getByLabel("Repeat new").fill(NEW_PASSWORD);
  await card.getByRole("button", { name: "Change" }).click();
  await expect(card.getByText("Changed.")).toBeVisible();
  await page.getByTitle("Log out").click();
  await page.getByLabel("Username").fill("admin");
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Log in" }).click();
  await expect(page.getByText("wrong username or password")).toBeVisible();
  appPassword = NEW_PASSWORD;
  await logIn(page);
});

test("security headers: the app refuses to be framed", async ({ request }) => {
  const res = await request.get("/");
  expect(res.headers()["x-frame-options"]).toBe("DENY");
  expect(res.headers()["content-security-policy"]).toContain("frame-ancestors 'none'");
});
