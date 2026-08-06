"""Fixture builders shared by the sync library and command suites."""

import json
import os

from support import RepoTestCase

from doclifecycle import PLUGIN_VERSION, RULESET_VERSION
from doclifecycle.inventory import build_inventory
from doclifecycle.segment import segment_document
from doclifecycle.sync import DEFAULT_LEDGER_PATH


REGISTRY = json.dumps({
    "schema_version": 1,
    "roots": ["docs"],
    "rules": [
        {"glob": "docs/*.md", "kind": "living"},
        {"glob": "docs/guides/*.md", "kind": "narrative"},
        {"glob": "docs/plans/*.md", "kind": "planning"},
    ],
})

FILES = {
    ".doc-lifecycle/registry.json": REGISTRY,
    "docs/architecture.md": "# Architecture\n\nThe service is stable.\n",
    "docs/guides/history.md": (
        "> As of 2026-08-06 (initial context)\n\nNarrative prose.\n"
    ),
    "docs/plans/next.md": "# Next\n\n> Status: pending-implementation\n",
}


class SyncRepoTestCase(RepoTestCase):
    def write(self, repo, path, contents):
        absolute = os.path.join(repo, path)
        os.makedirs(os.path.dirname(absolute), exist_ok=True)
        with open(absolute, "w", encoding="utf-8") as fh:
            fh.write(contents)

    def ledger_records(self, repo):
        inventory = build_inventory(repo)
        unit = next(
            unit for unit in segment_document(
                repo, "docs/architecture.md"
            ).units if unit.assertion_capable
        )
        header = {
            "record": "ledger-header",
            "schema": 1,
            "ruleset": RULESET_VERSION,
            "registry_digest": inventory.registry_digest,
            "plugin_version": PLUGIN_VERSION,
            "established": {
                "report_digest": "a" * 64,
                "commit": "b" * 40,
                "date": "2026-08-06",
            },
            "covered": ["docs/architecture.md"],
            "uncovered": [],
        }
        entry = {
            "record": "assertion",
            "doc": "docs/architecture.md",
            "unit": unit.digest,
            "class": "factual",
            "obligation": "evidence",
            "strategy": "on-change",
            "provenance": "judged",
            "lineage": {
                "report_digest": "a" * 64,
                "commit": "b" * 40,
                "plugin_version": PLUGIN_VERSION,
                "model": "sonnet",
                "date": "2026-08-06",
            },
            "status": "active",
        }
        return [header, entry]

    def write_ledger(self, repo, records=None):
        records = records if records is not None else self.ledger_records(repo)
        text = "".join(
            json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n"
            for record in records
        )
        self.write(repo, DEFAULT_LEDGER_PATH, text)
        return text

    def sync_repo(self, config=None):
        repo = self.repo(FILES)
        self.write_ledger(repo)
        if config is not None:
            self.write(repo, ".doc-lifecycle/config.json", config)
        return repo
