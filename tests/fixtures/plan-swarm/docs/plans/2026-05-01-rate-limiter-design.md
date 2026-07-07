# Rate limiter design

Status: approved.

## Problem

Services need per-process rate limiting without a shared store.

## Design

A token bucket: steady rate `MAX_REQUESTS_PER_MIN = 120`, burst
`BURST = 20`, class `TokenBucket` with an `allow()` method, all in
`src/limiter.py`.

## Alternatives considered

A Redis-backed shared limiter was rejected: operational overhead
disproportionate for single-node deploys. Revisit only if cross-worker
fairness becomes a measured problem.

## Sketch

    class TokenBucket:
        def allow(self): ...
