#!/usr/bin/env python3
"""Author an asciinema v2 .cast of a scripted doc-lifecycle drift audit.

Content mirrors tests/fixtures/taskflow + the detecting-doc-drift output
contract's worked example — no invented values.

Regenerate the README demo:
    python3 make_cast.py
    npx svg-term-cli --in demo.cast --out ../drift-audit-demo.svg --window --no-cursor
"""
import json

W, H = 80, 25
events = []
t = 0.0

# truecolor palette (matches the social card: green 3fb950, orange da7756)
GREEN = "\x1b[38;2;63;185;80m"
ORANGE = "\x1b[38;2;218;119;86m"
RED = "\x1b[38;2;248;81;73m"
DIM = "\x1b[38;2;125;133;144m"
FG = "\x1b[38;2;201;209;217m"
BOLD = "\x1b[1m"
R = "\x1b[0m"


def out(text, dt=0.0):
    global t
    t += dt
    events.append([round(t, 3), "o", text])


def type_out(text, cps=0.045):
    for ch in text:
        out(ch, cps)


def line(text, dt=0.15):
    out(text + "\r\n", dt)


# ---- scene ----
out(f"{GREEN}{BOLD}❯{R} ")
type_out(f"{FG}is the CLAUDE.md still accurate?{R}")
out("\r\n", 0.7)
line("", 0.1)

line(f"{ORANGE}⏺{R} {FG}Skill{R}{DIM}(doc-lifecycle:detecting-doc-drift){R}", 0.6)
line(f"  {DIM}⎿ extracting checkable claims from CLAUDE.md … 3 found{R}", 0.9)
line("", 0.1)

line(f"{ORANGE}⏺{R} {FG}Bash{R}{DIM}(grep -n \"^reset:\" Makefile){R}", 0.7)
line(f"  {DIM}⎿ no matches — Makefile has clean:, no reset target{R}", 0.5)
line(f"{ORANGE}⏺{R} {FG}Read{R}{DIM}(services/worker/worker.js:17-19){R}", 0.6)
line(f"  {DIM}⎿ if (schema !== 3) … process.exit(4){R}", 0.5)
line("", 0.2)

line(f"  {BOLD}{FG}drift report — CLAUDE.md{R}", 0.8)
rec = [
    ('  {', 0.06),
    (f'    {DIM}"claim":{R}    {FG}"Reset state = `make reset`"{R},', 0.06),
    (f'    {DIM}"location":{R} {FG}"CLAUDE.md:18"{R},', 0.06),
    (f'    {DIM}"kind":{R}     {FG}"command"{R},  {DIM}"tier":{R} {FG}1{R},', 0.06),
    (f'    {DIM}"verdict":{R}  {RED}"STALE"{R},', 0.35),
    (f'    {DIM}"evidence":{R} {FG}"Makefile has `clean:`, no `reset` target"{R},', 0.2),
    (f'    {DIM}"fix":{R}      {GREEN}"Reset state = `make clean`"{R}', 0.2),
    ('  }', 0.06),
]
for txt, dt in rec:
    line(txt, dt)
line(f"  {DIM}… 2 more records (1 STALE behavior, 1 UNVERIFIABLE quality claim){R}", 0.5)
line("", 0.2)

line(f"{GREEN}✓{R} {FG}validate-drift-output.py{R}", 0.8)
line(
    f'  {DIM}summary:{R} {FG}{{"verified": 0, "stale": 2, "unverifiable": 1}}{R}',
    0.3,
)
out("", 3.5)  # hold the final frame before the loop restarts

header = {
    "version": 2,
    "width": W,
    "height": H,
    "title": "doc-lifecycle — drift audit",
}
with open("demo.cast", "w") as f:
    f.write(json.dumps(header) + "\n")
    for ev in events:
        f.write(json.dumps(ev) + "\n")
print(f"wrote demo.cast: {len(events)} events, {t:.1f}s")
