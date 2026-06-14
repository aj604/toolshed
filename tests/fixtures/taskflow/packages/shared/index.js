// Shared helpers used by both api and worker.

let counter = 0;
export function makeId(prefix = "task") {
  counter += 1;
  return `${prefix}_${counter}`;
}

export function validateTask(task) {
  if (!task || typeof task !== "object") return false;
  if (typeof task.title !== "string" || task.title.length === 0) return false;
  if (task.priority != null && !["low", "med", "high"].includes(task.priority)) return false;
  return true;
}

export function normalizePriority(p) {
  return p == null ? "med" : p;
}
