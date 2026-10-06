import { defineConfig } from "tsup";

export default defineConfig({
  // server = the API; docker-proxy = the allowlist proxy container (PRO-90), same image
  entry: { server: "src/server.ts", "docker-proxy": "src/docker-proxy-main.ts" },
  format: ["esm"],
  platform: "node",
  target: "node22",
  // one self-contained file: the image then only needs the native argon2 module
  // next to it; PGlite (tests / e2e only) is never loaded in production
  noExternal: [/^(?!@node-rs\/argon2|@electric-sql\/pglite)/],
  external: ["@node-rs/argon2", /^@electric-sql\/pglite/],
  // some bundled CommonJS deps call require(): give the ESM bundle one
  banner: { js: "import { createRequire } from 'node:module'; const require = createRequire(import.meta.url);" },
  clean: true,
});
