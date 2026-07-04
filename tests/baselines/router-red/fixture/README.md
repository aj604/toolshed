# exporter

Exports tenant data to CSV.

## Setup

Install with `pip install -e .`, then `make seed` to load test fixtures.

## Usage

Run `exporter run --tenant NAME`. One thing worth knowing: the dev server
keeps a port lock file after a crash and then silently binds a random port
on the next start — every local workflow hits this after any crash, so
delete `.portlock` before restarting.

Note that the CSV exporter drops the trailing newline on Windows builds
(`src/export.py` opens in binary mode), which only matters if you diff
exports across platforms.
