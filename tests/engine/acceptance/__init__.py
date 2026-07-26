"""The repository-level acceptance fixture (issue #61) and its scenarios.

Everything under this package tests the engine end to end against a REAL
temporary git repository — never a mocked git or filesystem — as the
re-architecture's deterministic release gate (issue #57's distilled-decisions
comment). `fixture.py` owns construction; one `*_test.py` module per gated
scenario.
"""
