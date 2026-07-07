> As of 2026-05-10 (src/limiter.py)

# Rate limiting overview

Ratekit chose a token bucket over a sliding window because the bucket
answers "may this request proceed" in O(1) with two integers of state.

A request first claims a token; when the bucket is empty the request is
rejected outright rather than queued — queuing would trade memory for
latency under exactly the load the limiter exists to shed.
