# CLAUDE.md

- Jobs that exhaust `MAX_ATTEMPTS` are dropped, not parked (`src/worker.py:18`).
- The attempt timeout is global — one `TIMEOUT_S` for every job type (`src/worker.py:4`).
