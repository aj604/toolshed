// taskflow background worker. Polls the state file and processes due work.
// Requires a completed migration; exits if the state file is absent.
import { existsSync, readFileSync } from "node:fs";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..", "..");
const STATE = resolve(root, ".taskflow-state.json");

if (!existsSync(STATE)) {
  process.stderr.write("worker: missing .taskflow-state.json — run `make migrate` first\n");
  process.exit(3);
}

const { schema } = JSON.parse(readFileSync(STATE, "utf8"));
// Gotcha: the worker only understands schema 3. A stale migration breaks it.
if (schema !== 3) {
  process.stderr.write(`worker: state schema ${schema} unsupported (need 3)\n`);
  process.exit(4);
}

const intervalMs = Number(process.env.WORKER_INTERVAL_MS) || 5000;
process.stdout.write(`worker: started, polling every ${intervalMs}ms\n`);
setInterval(() => {
  // process due tasks here
}, intervalMs);
