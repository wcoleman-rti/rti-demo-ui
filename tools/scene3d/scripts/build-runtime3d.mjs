import { build } from "esbuild";
import { mkdir } from "node:fs/promises";
import { dirname, resolve } from "node:path";

const root = resolve(dirname(new URL(import.meta.url).pathname), "..");
await mkdir(resolve(root, "../../assets"), { recursive: true });
await build({
  entryPoints: [resolve(root, "src/runtime3d.js")],
  outfile: resolve(root, "../../assets/runtime3d.js"),
  bundle: true,
  format: "esm",
  platform: "browser",
  target: "es2020",
  legalComments: "none",
  logLevel: "info"
});
