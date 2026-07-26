#!/usr/bin/env python3
"""Entrypoint for running the engine from a plugin checkout with no setup:

    python3 <plugin>/engine/doc-lifecycle.py inventory --repo .

Python puts this script's directory on `sys.path`, so the sibling `doclifecycle`
package imports without PYTHONPATH. Identical behavior to `python3 -m
doclifecycle` — both call `cli.main()` and nothing else.
"""

import sys

from doclifecycle.cli import main

sys.exit(main())
