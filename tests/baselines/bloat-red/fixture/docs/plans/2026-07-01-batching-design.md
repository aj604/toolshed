# 2026-07-01 — Batching design for `send_alert`

## Problem

Callers that emit many alerts in a tight loop (e.g. a monitoring sweep that
finds several failing checks at once) currently send one request per alert,
which can trip channel rate limits.

## Proposal

Add a `send_batch(channel, msgs)` helper that groups pending messages and
delivers them as a single request when possible, falling back to individual
`send_alert` calls for channels that don't support batch delivery.

## Status

Not yet implemented. Needs a decision on max batch size before work starts.
