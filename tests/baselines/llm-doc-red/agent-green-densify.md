# bundlewatch

Bundle size enforcement tool.

## Setup

Requires Node 18+.

```
npm install
npm test
```

Reads `.bundlewatchrc` from project root on run.

## CLI flags

| Flag | Effect |
|------|--------|
| `--config <path>` | Use alternate config file |
| `--budget <value>` | Override budget from config |
| `--verbose` | Log each artifact as it is checked |
| `--json` | Machine-readable output instead of human report |
| `--help` / `-h` | Print all options |

## How it works

Reads each artifact into memory and gzips it in-memory (not streaming).

> UNVERIFIED: "under 50ms" measurement claim — source states it as a marketing assertion, not a measured benchmark with methodology.
