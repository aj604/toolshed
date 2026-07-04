# Worker queue failure handling — design

## Problem

Jobs fail transiently (network, upstream 5xx). Today a failed job is lost.
We need retries with a bound, and a decision about what happens to a job
that keeps failing.

## Options

**A. Dead-letter queue.** Park exhausted jobs in a DLQ for inspection.
Rejected: a DLQ only works when an operator drains it, and this system
deploys unattended — an unmonitored DLQ grows without bound and hides
failures better than dropping does. Revisit only if an operator rotation
ever exists for this service.

**B. Exponential backoff between attempts.** Rejected as needless for our
queue depth; re-entering at the tail already spaces attempts by roughly the
queue's drain time, so an explicit backoff schedule would double-delay.

**C. Per-job-type timeouts.** Give slow job types their own budget.
Rejected: one global `TIMEOUT_S` for every type, because per-type budgets
turn each new job type into a tuning decision nobody owns. We accept fast
types wasting budget under the global cap.

## Decision

Bounded retries, re-enter at tail, drop on exhaustion. Five attempts is
enough for transient upstream failures without wedging the queue; thirty
seconds per attempt covers the slowest current job type with headroom.

## Sketch

    MAX_ATTEMPTS = 5
    TIMEOUT_S = 30

    def handle_failure(queue, job):
        job.attempts += 1
        if job.attempts >= MAX_ATTEMPTS:
            queue.drop(job)
        else:
            queue.push_tail(job)
