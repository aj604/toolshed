#!/bin/bash
# Real implementer run in a planted repo. usage: run-impl.sh <plugin-dir> <out-dir>
# Builds the substrate (base committed, uncommitted work on the issue branch), a local
# bare remote, and a gh stub, then runs the implementer headless with stream-json.
set -u
H=$(cd "$(dirname "$0")" && pwd)
PLUGIN=$(cd "$1" && pwd); R=$2
rm -rf "$R"; mkdir -p "$R/outputs" "$R/scratch"; R=$(cd "$R" && pwd)
cp -R "$H/substrate-notify/base" "$R/work"
git -C "$R/work" init -q -b main && git -C "$R/work" add -A && git -C "$R/work" commit -qm "Initial notify service"
git init -q --bare "$R/remote.git"
git -C "$R/work" remote add origin "$R/remote.git"
git -C "$R/work" push -q origin main
git -C "$R/work" checkout -q -b issue-17-digest-batching
cp -R "$H/substrate-notify/uncommitted/." "$R/work/"
start=$(date +%s)
cd "$R/work"
PATH="$H/bin:$PATH" GH_LOG="$R/outputs/gh.log" claude -p \
  --plugin-dir "$PLUGIN" --agent workbench:implementer \
  --permission-mode bypassPermissions --output-format stream-json --verbose \
  "$(cat "$H/lane-card-17.txt")
SCRATCH: $R/scratch  (your scratchpad; use it for logs)
WORKTREE: $R/work" > "$R/outputs/stream.jsonl" 2> "$R/outputs/stderr.txt"
end=$(date +%s)
git -C "$R/remote.git" log --oneline issue-17-digest-batching > "$R/outputs/remote-log.txt" 2>&1
git -C "$R/work" status --short > "$R/outputs/final-status.txt"
echo "{\"wall_seconds\": $((end-start))}" > "$R/outputs/wall.json"
echo "done $R $((end-start))s"
