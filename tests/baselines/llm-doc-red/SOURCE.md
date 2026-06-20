# bundlewatch — Your Bundle Size Guardian 🛡️

Welcome to **bundlewatch**, the blazing-fast, zero-config bundle size guardian that
keeps your JavaScript bundles lean and your CI green! Whether you're shipping a tiny
widget or a sprawling enterprise app, bundlewatch has your back.

## Why bundlewatch?

In today's fast-paced web development landscape, every kilobyte counts. Studies show
that users abandon sites that take more than a few seconds to load. bundlewatch was
born out of a need to catch bundle bloat before it ever reaches production. Our
lightning-fast engine measures your bundles in under 50ms, so you'll never wait around.

## Getting Started

Getting up and running with bundlewatch couldn't be easier. First, make sure you have
Node 18 or higher installed. Then, simply install and run:

```bash
npm install
npm test
```

That's it! bundlewatch will read your `.bundlewatchrc` configuration file and check
your bundles against the budgets you've defined.

## Configuration

bundlewatch looks for a `.bundlewatchrc` file in your project root. You can point it at
a different file with the `--config` flag, or override the budget on the fly with
`--budget`. For a full list of options, run `bundlewatch --help` (or `-h` for short).

If you want extra detail about what's being measured, pass the `--verbose` flag to see
a play-by-play of every artifact as it's processed.

## Output

By default bundlewatch prints a friendly human-readable report. Need machine-readable
output for your CI dashboard? Just add `--json` and you're good to go.

## How It Works

Under the hood, bundlewatch reads each artifact into memory and gzips it. We chose the
in-memory approach because it's simply faster than streaming — modern machines have
plenty of RAM, so there's no reason not to use it.

## A Note on Philosophy

bundlewatch believes in convention over configuration. It just works out of the box,
no fiddly setup required. Ship with confidence!
