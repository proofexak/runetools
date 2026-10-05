import { activeAccount, writeActiveFile } from "./accounts.js";
import { buildApp } from "./app.js";
import { Bus } from "./bus.js";
import { loadConfig } from "./config.js";
import { openDb } from "./db/index.js";
import { Ingester } from "./ingest/ingester.js";
import { getLogRoots } from "./settings.js";
import { Vault } from "./vault/vault.js";

const config = loadConfig();
const { db, close } = await openDb(config.databaseUrl);
const bus = new Bus();
const ingester = new Ingester(db, () => getLogRoots(db, config), bus, (msg, err) => app.log.error({ err }, msg));
const vault = new Vault(db, bus);
const app = await buildApp({ db, config, bus, ingester, vault });

// the database is the truth for the active account: bring data/active_account in line
try {
  await writeActiveFile(config.dataDir, await activeAccount(db));
} catch (err) {
  app.log.warn({ err }, `couldn't write ${config.dataDir}/active_account — new sessions won't be tagged`);
}

let stopping = false;
async function shutdown() {
  if (stopping) return;
  stopping = true;
  await ingester.stop();
  vault.lock();
  await app.close();
  await close();
  process.exit(0);
}
process.on("SIGINT", shutdown);
process.on("SIGTERM", shutdown);

await app.listen({ host: config.host, port: config.port });
ingester.start(config.pollMs);
