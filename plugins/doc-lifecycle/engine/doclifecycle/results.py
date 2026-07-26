"""Typed results: every run resolves to a named state, never a bare exception.

An audited run resolves to exactly one of five result states. Only `clean`
means the declared scope was examined successfully under the named mode and
rules — every other state is a reason not to act on the run as if it were:

- `clean`    the declared scope was examined; nothing was found.
- `findings` the declared scope was examined; records were found.
- `partial`  the declared scope was *not* fully examined, so the absence of a
             record proves nothing. The run names what it did not examine.
- `stale`    the run's lineage no longer matches the repository it describes.
             Structurally sound, but about a state that no longer exists.
- `invalid`  the run cannot be trusted. Carries problems and *no* output.

A producing run declares one of the first three; `stale` and `invalid` are
verdicts a validator reaches about an artifact, never self-declared.
`Inventory` predates the model and reports the simpler `ok`/`invalid` pair.
"""

from dataclasses import dataclass
from typing import Optional, Tuple

from . import ARTIFACT_SCHEMA_VERSION

STATUS_OK = "ok"
STATUS_INVALID = "invalid"

STATE_CLEAN = "clean"
STATE_FINDINGS = "findings"
STATE_PARTIAL = "partial"
STATE_STALE = "stale"
STATE_INVALID = STATUS_INVALID

RESULT_STATES = (
    STATE_CLEAN, STATE_FINDINGS, STATE_PARTIAL, STATE_STALE, STATE_INVALID,
)
# The states a producing run may declare for itself. `stale` and `invalid` are
# reached by a validator comparing the artifact to the world, so a run that
# declared either would be asserting a judgment it is not in a position to make.
DECLARABLE_STATES = (STATE_CLEAN, STATE_FINDINGS, STATE_PARTIAL)


@dataclass(frozen=True)
class Problem:
    """One reason a run cannot be trusted, with where and what to do."""

    code: str
    message: str
    location: Optional[str] = None


@dataclass(frozen=True)
class Invalid:
    problems: Tuple[Problem, ...]
    status: str = STATUS_INVALID

    def to_dict(self):
        return {
            "status": self.status,
            "schema_version": ARTIFACT_SCHEMA_VERSION,
            "problems": [
                {"code": p.code, "message": p.message, "location": p.location}
                for p in self.problems
            ],
        }
