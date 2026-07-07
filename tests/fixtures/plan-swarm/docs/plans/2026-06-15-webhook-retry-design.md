# Webhook retry design

Status: draft.

## Problem

Outbound webhooks fail transiently and are currently dropped.

## Design

A `RetryQueue` with exponential backoff (`WEBHOOK_MAX_ATTEMPTS = 5`) in
`src/webhooks.py`, drained by a background thread.
