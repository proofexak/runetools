import { defineConfig } from "tsup";

export default defineConfig({
  entry: ["src/server.ts"],
  format: ["esm"],
  platform: "node",
  target: "node22",
  // the shared package is TypeScript source: bundle it, keep real deps external
  noExternal: ["@runetools/shared"],
  clean: true,
});
