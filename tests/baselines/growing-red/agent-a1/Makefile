# taskflow orchestration. Run `make setup` once, then `make migrate`, then `make dev`.
.PHONY: setup migrate dev migrated api worker test lint clean

setup:
	npm install

# Creates .taskflow-state.json. The worker and api refuse to start without it.
migrate:
	node scripts/migrate.js

# Runs api and worker together (foreground). Requires migrate to have run.
dev: migrated api worker

# Fail fast if `make migrate` hasn't been run: api and worker are backgrounded,
# so their own exit-3 message is easy to miss and `make dev` would exit 0 anyway.
migrated:
	@test -f .taskflow-state.json || { \
		echo "make dev: .taskflow-state.json missing — run 'make migrate' first" >&2; \
		exit 3; \
	}

api:
	node services/api/server.js &

worker:
	node services/worker/worker.js &

# Runs the whole test suite across workspaces via the Node test runner.
# Only @taskflow/shared has tests today.
test:
	node --test packages/*/test/

lint:
	node scripts/lint.js

clean:
	rm -f .taskflow-state.json
