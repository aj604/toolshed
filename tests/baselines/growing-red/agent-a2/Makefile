# taskflow orchestration. Run `make setup` once, then `make migrate`, then `make dev`.
.PHONY: setup migrate dev api worker test lint clean check-migrated

setup:
	npm install

# Creates .taskflow-state.json. The worker and api refuse to start without it.
migrate:
	node scripts/migrate.js

# Fail fast before backgrounding: the services exit 3 without the state file,
# but `&` would let make report success anyway and the error scroll past.
check-migrated:
	@test -f .taskflow-state.json || { \
		echo "error: .taskflow-state.json missing — run 'make migrate' first (see README Setup)" >&2; \
		exit 3; \
	}

# Runs api and worker together (foreground). Requires migrate to have run.
dev: api worker

api: check-migrated
	node services/api/server.js &

worker: check-migrated
	node services/worker/worker.js &

# Runs the whole test suite across workspaces via the Node test runner.
# Only @taskflow/shared has tests today.
test:
	node --test packages/*/test/

lint:
	node scripts/lint.js

clean:
	rm -f .taskflow-state.json
