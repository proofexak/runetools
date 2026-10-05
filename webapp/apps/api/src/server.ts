import { buildApp } from "./app.js";
import { Bus } from "./bus.js";
import { loadConfig } from "./config.js";
import { openDb } from "./db/index.js";
import { Ingester } from "./ingest/ingester.js";
import { getLogRoots } from "./settings.js";

const config = loadConfig();
const { db, close } = await openDb(config.databaseUrl);
const bus = new Bus();
const ingester = new Ingester(db, () => getLogRoots(db, config), bus, (msg, err) => app.log.error({ err }, msg));
const app = await buildApp({ db, config, bus, ingester });

let stopping = false;
async function shutdown() {
  if (stopping) return;
  stopping = true;
  await ingester.stop();
  await app.close();
  await close();
  process.exit(0);
}
process.on("SIGINT", shutdown);
process.on("SIGTERM", shutdown);

await app.listen({ host: config.host, port: config.port });
ingester.start(config.pollMs);
