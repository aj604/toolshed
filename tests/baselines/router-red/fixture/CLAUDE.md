# CLAUDE.md

## Gotchas

- **Run `make seed` before any test run** — without the seed fixtures every test
  fails with an unrelated-looking `KeyError: tenant` (`Makefile:4`).
- The API client retries twice on 503 before raising (`src/client.py:3`).

## Regenerating the golden files

When an export test fails on golden mismatch, regenerate them: run
`python tools/regen-goldens.py --suite export`, inspect the diff of
`tests/goldens/` by hand (the script does not validate, it only rewrites),
then run `make test-export` twice — the first run after regeneration
rebuilds the cache and can pass spuriously, only the second run counts.
