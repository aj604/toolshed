# 2026-01-10 — Retry behavior for `send_alert`

## Problem

`send_alert` currently fails permanently on the first delivery error. Channel
outages tend to be transient — a few seconds of network blip, a momentary
rate limit on the receiving side — and giving up immediately means callers
have to implement their own retry wrapper, which several already do,
inconsistently. We want retry handling built into `send_alert` itself so
every caller gets the same behavior for free.

## Options considered

**Option A: Fixed number of retries, fixed backoff.** Retry a set number of
times with a constant delay between attempts. Simple to implement and easy
to reason about. Downside: doesn't adapt to slow channels, and a constant
delay can hammer a channel that's recovering from an outage.

**Option B: Exponential backoff with jitter.** Standard approach for
distributed retry logic — delay doubles each attempt, with random jitter to
avoid thundering-herd effects when many callers retry at once. More robust,
but adds complexity (jitter source, max-delay cap, tests for backoff timing)
that seems disproportionate for a small internal alerting library with a
handful of callers.

**Option C: Caller-supplied retry policy object.** Let callers pass in their
own retry strategy (max attempts, delay function) so the library stays
unopinionated. Rejected: this just pushes the decision back onto every
caller, which is the problem we're trying to solve in the first place. Also
expands the public API surface for a benefit only one caller (the batching
feature, still unimplemented) would plausibly need.

## Decision

Going with Option A. Simplicity wins for a library this small, and we can
always upgrade to backoff later if a channel starts showing retry storms in
practice. After going back and forth, three attempts felt like the right
balance — enough to ride out a typical few-second blip without letting a
truly dead channel hang the caller for too long. On the timeout side, ten
seconds per attempt gives slow channels enough headroom to respond without
letting a single hung request block the whole retry loop for an unreasonable
amount of time.

## Sketch

```python
def send_alert(channel, msg):
    for attempt in range(MAX_RETRIES):
        try:
            return channel.deliver(msg, timeout=TIMEOUT_S)
        except DeliveryError:
            if attempt == MAX_RETRIES - 1:
                raise AlertFailed(channel, msg)
    raise AlertFailed(channel, msg)
```

## Open questions

None — ready to implement.
