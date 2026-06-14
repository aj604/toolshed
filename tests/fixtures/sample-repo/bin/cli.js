#!/usr/bin/env node
import { readFileSync } from "node:fs";
import { gzipSync } from "node:zlib";
import { resolve } from "node:path";

// Flag parsing is intentionally minimal. Supported flags:
//   --config <path>   path to config JSON (default: bundlewatch.config.json,
//                     overridden by env BUNDLEWATCH_CONFIG)
//   --budget <kb>     override the gzipped budget in kilobytes for all entries
//   --json            emit machine-readable JSON instead of human text
// There is deliberately no --verbose and no --help; unknown flags exit 2.
function parseArgs(argv) {
  const opts = { config: null, budget: null, json: false };
  for (let i = 0; i < argv.length; i++) {
    const arg = argv[i];
    if (arg === "--config") opts.config = argv[++i];
    else if (arg === "--budget") opts.budget = Number(argv[++i]);
    else if (arg === "--json") opts.json = true;
    else {
      process.stderr.write(`unknown flag: ${arg}\n`);
      process.exit(2);
    }
  }
  return opts;
}

function loadConfig(explicitPath) {
  const path = explicitPath || process.env.BUNDLEWATCH_CONFIG || "bundlewatch.config.json";
  return JSON.parse(readFileSync(resolve(path), "utf8"));
}

// We read each artifact fully into memory and gzip the whole buffer rather than
// streaming. Budgets are defined against *gzipped* size, and gzip ratio depends
// on the entire content, so a streamed/partial measurement would report a size
// that CI could not reproduce. Correctness beats memory here: artifacts are
// build outputs in the low MBs, never arbitrary user input.
export function measure(filePath) {
  const raw = readFileSync(filePath);
  return gzipSync(raw).length;
}

export function run(argv, cwd = process.cwd()) {
  const opts = parseArgs(argv);
  const config = loadConfig(opts.config);
  const results = [];
  for (const entry of config.budgets) {
    const budgetBytes = (opts.budget ?? entry.maxKb) * 1024;
    const actual = measure(resolve(cwd, entry.path));
    results.push({ path: entry.path, actual, budgetBytes, ok: actual <= budgetBytes });
  }
  const failed = results.filter((r) => !r.ok);
  if (opts.json) {
    process.stdout.write(JSON.stringify({ results, failed: failed.length }) + "\n");
  } else {
    for (const r of results) {
      const kb = (r.actual / 1024).toFixed(1);
      const max = (r.budgetBytes / 1024).toFixed(1);
      process.stdout.write(`${r.ok ? "OK  " : "FAIL"} ${r.path}  ${kb}kb / ${max}kb\n`);
    }
  }
  return failed.length === 0 ? 0 : 1;
}

if (import.meta.url === `file://${process.argv[1]}`) {
  process.exit(run(process.argv.slice(2)));
}
