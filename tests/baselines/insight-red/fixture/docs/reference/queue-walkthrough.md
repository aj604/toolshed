# How a job moves through the queue

> As of 2026-03-05 (src/worker.py:3-20)

A job starts at the head of the queue. The worker pulls it and calls
`run_attempt`, which runs the job's own `run` method under the global
thirty-second timeout. If it returns, the job is done and nothing else
happens to it.

If it raises `JobError`, the interesting part starts. `handle_failure`
bumps the job's attempt counter and looks at it once: a job that has now
failed five times is dropped on the spot — there is no parking lot for it —
while anything younger goes back in at the tail. Re-entering at the tail
matters: the job waits behind everything already queued, so by the time it
runs again the transient condition that failed it has usually cleared.
