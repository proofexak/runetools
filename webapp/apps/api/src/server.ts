import { buildApp } from "./app.js";
import { Bus } from "./bus.js";
import { loadConfig } from "./config.js";
import { openDb } from "./db/index.js";

const config = loadConfig();
const { db, close } = await openDb(config.databaseUrl);
const bus = new Bus();
const app = await buildApp({ db, config, bus });

let stopping = false;
async function shutdown() {
  if (stopping) return;
  stopping = true;
  await app.close();
  await close();
  process.exit(0);
}
process.on("SIGINT", shutdown);
process.on("SIGTERM", shutdown);

await app.listen({ host: config.host, port: config.port });
