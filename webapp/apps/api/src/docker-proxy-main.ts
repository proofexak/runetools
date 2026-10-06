/** Entry point of the docker proxy container (see docker-proxy.ts): `node dist/docker-proxy.js`. */
import { createDockerProxy } from "./docker-proxy.js";

const container = process.env.BOT_CONTAINER || "runetools-runetools-1";
const port = Number(process.env.PROXY_PORT || 2375);
const socketPath = process.env.DOCKER_SOCKET || "/var/run/docker.sock";

createDockerProxy({ container, upstream: { socketPath } }).listen(port, "0.0.0.0", () => {
  console.log(`docker proxy: ${container} (json/start/stop only) on :${port} -> ${socketPath}`);
});
for (const sig of ["SIGINT", "SIGTERM"] as const) process.on(sig, () => process.exit(0));
