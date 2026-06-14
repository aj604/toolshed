// taskflow HTTP API. Requires DATABASE_URL and a completed migration.
import { createServer } from "node:http";
import { readFileSync, existsSync } from "node:fs";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { makeId, validateTask, normalizePriority } from "@taskflow/shared";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..", "..");
const STATE = resolve(root, ".taskflow-state.json");

// Gotcha: refuse to start if the migration has not run.
if (!existsSync(STATE)) {
  process.stderr.write("api: missing .taskflow-state.json — run `make migrate` first\n");
  process.exit(3);
}
if (!process.env.DATABASE_URL) {
  process.stderr.write("api: DATABASE_URL is required\n");
  process.exit(1);
}

const port = Number(process.env.PORT) || 8080;
const tasks = [];

const server = createServer((req, res) => {
  if (req.url === "/health") {
    res.writeHead(200, { "content-type": "application/json" });
    res.end(JSON.stringify({ ok: true, tasks: tasks.length }));
    return;
  }
  if (req.method === "POST" && req.url === "/tasks") {
    let body = "";
    req.on("data", (c) => (body += c));
    req.on("end", () => {
      let parsed;
      try {
        parsed = JSON.parse(body);
      } catch {
        res.writeHead(400);
        res.end("bad json");
        return;
      }
      if (!validateTask(parsed)) {
        res.writeHead(422);
        res.end("invalid task");
        return;
      }
      const task = { id: makeId(), title: parsed.title, priority: normalizePriority(parsed.priority) };
      tasks.push(task);
      res.writeHead(201, { "content-type": "application/json" });
      res.end(JSON.stringify(task));
    });
    return;
  }
  res.writeHead(404);
  res.end("not found");
});

server.listen(port, () => process.stdout.write(`api listening on :${port}\n`));
