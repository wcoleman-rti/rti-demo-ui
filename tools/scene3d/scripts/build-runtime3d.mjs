/*
 * (c) 2026 Copyright, Real-Time Innovations, Inc.  All rights reserved.
 *
 * RTI grants Licensee a license to use, modify, compile, and create derivative
 * works of the Software.  Licensee has the right to distribute object form
 * only for use with RTI products.  The Software is provided "as is", with no
 * warranty of any type, including any warranty for fitness for any purpose.
 * RTI is under no obligation to maintain or support the Software.  RTI shall
 * not be liable for any incidental or consequential damages arising out of the
 * use or inability to use the software.
 */

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
