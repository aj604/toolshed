// Minimal stand-in "build": concatenates src/*.js into dist/bundle.js so the
// CLI has an artifact to measure. Real projects would invoke esbuild/rollup here.
// `--lint-only` runs the syntax check without emitting (used by `npm run lint`).
import { readdirSync, readFileSync, writeFileSync, mkdirSync } from "node:fs";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const srcDir = resolve(root, "src");
const lintOnly = process.argv.includes("--lint-only");

const files = readdirSync(srcDir).filter((f) => f.endsWith(".js"));
let out = "";
for (const f of files) {
  const code = readFileSync(resolve(srcDir, f), "utf8");
  out += `// ${f}\n${code}\n`;
}

if (!lintOnly) {
  mkdirSync(resolve(root, "dist"), { recursive: true });
  writeFileSync(resolve(root, "dist", "bundle.js"), out);
  process.stdout.write(`built dist/bundle.js (${out.length} bytes)\n`);
} else {
  process.stdout.write(`lint ok: ${files.length} files\n`);
}
