# jobrunner

A single-process background job worker. Jobs are pulled from the queue head,
run with a per-attempt timeout, and on failure re-enter at the tail.

## Usage

Enqueue a job object with a `run(timeout=)` method; the worker handles retries.
Failed jobs are retried up to `MAX_ATTEMPTS` (5) times (`src/worker.py:3`),
each attempt bounded by `TIMEOUT_S` (30s) (`src/worker.py:4`).
