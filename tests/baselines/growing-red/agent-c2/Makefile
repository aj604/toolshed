# taskflow orchestration. Run `make setup` once, then `make migrate`, then `make dev`.
.PHONY: setup migrate dev api worker test lint clean

setup:
	npm install

# Creates .taskflow-state.json. The worker and api refuse to start without it.
migrate:
	node scripts/migrate.js

# Runs api and worker together (foreground). Requires migrate to have run.
dev: api worker

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
