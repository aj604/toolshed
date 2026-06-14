// Writes the local state file that the api and worker require to start.
// In a real system this would run DB migrations; here it stamps a state file.
import { writeFileSync } from "node:fs";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const state = { migratedAt: "fixture-stamp", schema: 3 };
writeFileSync(resolve(root, ".taskflow-state.json"), JSON.stringify(state, null, 2));
process.stdout.write("migrated: wrote .taskflow-state.json (schema 3)\n");
