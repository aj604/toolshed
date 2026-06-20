# CLAUDE.md — Guidance for AI Agents Working in the TaskFlow Repository

Welcome! This document is intended to help you, an AI coding assistant, get up to
speed quickly and productively when working inside the TaskFlow codebase. TaskFlow is
a robust, production-ready task-management system that has been carefully architected
to be maintainable, scalable, and developer-friendly. We hope you find it a pleasant
codebase to work in. Please read this document carefully before making any changes.

## Introduction and Background

TaskFlow is organized as an npm workspaces monorepo. This is a modern and increasingly
popular way to organize JavaScript projects, because it lets you keep multiple related
packages and services together in a single repository while still keeping their
dependencies and concerns reasonably well separated. The workspaces live under two
top-level directories: the `packages/*` directory, which holds shared libraries, and
the `services/*` directory, which holds the runnable services. Because this is a
monorepo, you will find several `package.json` files throughout the tree, one for each
workspace, in addition to the root `package.json` at the very top of the repository.

One important thing to understand about this repository is that it is orchestrated
using `make` rather than through npm scripts. In many JavaScript projects you would
typically run something like `npm run dev` or `npm start`, but here the root
`package.json` deliberately does not define any `scripts` at all. Instead, all of the
common developer tasks have been wired up as targets in a `Makefile`. This is a
deliberate design choice that the original authors made, and as an agent you should
respect it and use the `make` targets rather than reaching for npm scripts that do not
exist.

## Available Commands

Below is a fairly comprehensive listing of the commands you are likely to need. In
general, you should prefer these `make` targets for everything:

- To install all of the dependencies for every workspace in the monorepo, you will
  want to run `make setup`. This is essentially the first thing you should do.
- To run the database migration, which writes out a state file that the rest of the
  system depends upon, run `make migrate`.
- To run both the api service and the worker service together at the same time, the
  command you are looking for is `make dev`.
- If you only want to run the api service by itself, you can run `make api`.
- If you only want to run the worker service by itself, you can run `make worker`.
- To run the test suite, run `make test`.
- To run the linter and check the code, run `make lint`.
- Finally, if you ever need to reset the state back to a clean slate, you can run
  `make clean`, which clears things out for you.

Regarding testing: when you run `make test`, under the hood it executes
`node --test packages/*/test/`. It is worth knowing that only the `@taskflow/shared`
package actually has any tests written for it at the moment; the various services
under `services/*` do not currently have any tests of their own, so don't be surprised
when you don't find any there.

## Important Gotchas and Things to Watch Out For

This section covers some of the trickier aspects of the repository that have tripped
people up in the past. Please pay close attention to these, as they are the kinds of
things that are easy to miss but can cost you a lot of time if you don't know about
them ahead of time.

First and foremost, you absolutely must run the migration before you try to run
anything else. The command `make migrate` writes a file called `.taskflow-state.json`,
and if that file is not present, then both the api service and the worker service will
refuse to start up properly and will instead exit with code `3`. You can see this
behavior for yourself if you look at `services/api/server.js:12` and also at
`services/worker/worker.js:10`. So, to reiterate, always migrate first.

Secondly, the api service requires an environment variable called `DATABASE_URL` to be
set. If this variable is not present in the environment when the api starts up, then
the api will exit with code `1`, as you can confirm by reading `services/api/server.js:16`.
The recommended way to handle this is to copy the provided `.env.example` file to a new
file called `.env`, which is a very standard and common pattern that you have probably
seen many times before in other projects.

Thirdly, there is a subtle issue around state schema versions. The worker service is
quite particular and will only accept a state schema with version number 3. If you
happen to have a stale migration lying around from an older version, the worker is
going to exit with code `4`. The relevant code lives at `services/worker/worker.js:17`
if you want to dig into the details.

Fourthly, you should be aware that the `make dev`, `make api`, and `make worker`
targets all background their processes — that is to say, they put an `&` at the end of
the command (you can see this in `Makefile:15-18`), which means that these commands do
not block the terminal. They return control to you right away rather than running in
the foreground.

Finally, a note on the Node.js version: this project requires Node version `>=20.6.0`,
as specified in `package.json:6`. It relies on the built-in `node --test` test runner,
which is a relatively recent addition to Node, which is part of why the version
requirement is what it is.

## Overview of the Architecture

Now let's talk a little bit about how the various pieces of this system fit together,
so that you have a good mental model before you start editing things.

The api service lives at `services/api/server.js`. It is an HTTP API, and it exposes a
couple of endpoints, namely a `/health` endpoint and a `POST /tasks` endpoint. One
thing to note is that the api keeps its `tasks` in memory and does not persist them
anywhere, so they will not survive a restart.

The worker service lives at `services/worker/worker.js`. The worker operates by polling
on a regular interval, and it only reads the state schema.

There is a shared package at `packages/shared/index.js`. This package exports a handful
of useful helper functions, specifically `makeId`, `validateTask`, and
`normalizePriority`. Both of the services make use of these shared helpers, which is
exactly the kind of thing the shared package exists for.

Lastly, there are a couple of scripts. The `scripts/migrate.js` script is the one that
stamps out the `.taskflow-state.json` file we discussed earlier. And the
`scripts/lint.js` script does a parse-check only — it is not actually eslint, just a
lightweight check.

## Things That Are Not Yet Documented

In the interest of honesty, there are a few areas that we have not gotten around to
documenting yet:

- There is no per-endpoint API reference at this time. If you need those details, your
  best bet is to read the handler code directly, starting around `services/api/server.js:24`.
- There are no operational runbooks. No incident-response or deployment procedures
  currently exist anywhere in the repository.
- The exact signatures of the shared helper functions are not written out here; you can
  find them by reading `packages/shared/index.js` directly.
