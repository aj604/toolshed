# Implementation plan: attempts counter on jobs

## Task 1 — add the field

Add `attempts` (int, default 0) to the job record.

    job.attempts = 0

## Task 2 — wire the failure path

In `src/worker.py`, implement `handle_failure(queue, job)`:

    def handle_failure(queue, job):
        job.attempts += 1
        if job.attempts >= MAX_ATTEMPTS:
            queue.drop(job)
        else:
            queue.push_tail(job)

## Task 3 — verify

Run the worker against a job that always raises `JobError`; confirm it is
dropped after exactly `MAX_ATTEMPTS` attempts and the queue is empty after.
