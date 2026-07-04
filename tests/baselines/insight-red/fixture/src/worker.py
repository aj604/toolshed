"""Background job worker: pull, run, requeue on failure."""

MAX_ATTEMPTS = 5   # attempts per job before it is dropped
TIMEOUT_S = 30     # one global per-attempt timeout, all job types


class JobError(Exception):
    pass


def run_attempt(job):
    return job.run(timeout=TIMEOUT_S)


def handle_failure(queue, job):
    job.attempts += 1
    if job.attempts >= MAX_ATTEMPTS:
        queue.drop(job)        # dropped outright
    else:
        queue.push_tail(job)   # failed jobs re-enter at the tail
