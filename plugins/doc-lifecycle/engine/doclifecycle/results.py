"""Typed results: every run resolves to a named state, never a bare exception.

`Invalid` is the state this slice needs — a run whose inputs cannot be trusted,
which reports problems and *no* partial output. The full five-state result model
(clean / findings / partial / stale / invalid) belongs to the report contract.
"""

from dataclasses import dataclass
from typing import Optional, Tuple

STATUS_OK = "ok"
STATUS_INVALID = "invalid"


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
        from . import SCHEMA_VERSION

        return {
            "status": self.status,
            "schema_version": SCHEMA_VERSION,
            "problems": [
                {"code": p.code, "message": p.message, "location": p.location}
                for p in self.problems
            ],
        }
