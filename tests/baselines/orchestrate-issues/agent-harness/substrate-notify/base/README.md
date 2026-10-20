# notify
Notification service.

## Testing
- Unit tests for one module: `python3 -m unittest tests.test_<module> -q` (seconds).
- Full suite: `./scripts/full_suite.sh` — unit + integration + replay, takes ~15 minutes. Must pass before a PR.
