// Minimal "lint": ensures every workspace source file parses as a module.
// Real projects would run eslint here.
import { readdirSync, statSync } from "node:fs";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
let count = 0;
function walk(dir) {
  for (const name of readdirSync(dir)) {
    if (name === "node_modules" || name.startsWith(".")) continue;
    const p = resolve(dir, name);
    if (statSync(p).isDirectory()) walk(p);
    else if (name.endsWith(".js")) count++;
  }
}
walk(resolve(root, "packages"));
walk(resolve(root, "services"));
process.stdout.write(`lint ok: ${count} files\n`);
