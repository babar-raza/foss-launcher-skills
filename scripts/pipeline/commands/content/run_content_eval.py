# Adapted from aspose.org
"""run_content_eval.py — Wrapper entrypoint for content_eval.

Allows invoking content_eval from the repo root without any PYTHONPATH prefix:

    python scripts/pipeline/commands/content/run_content_eval.py [args...]

This is the durable alternative to the ad hoc workaround:
    PYTHONPATH=scripts/pipeline python -m content_eval [args...]

When Python runs a script directly it adds the script's directory to sys.path,
so scripts/pipeline/ is always available here without any manual configuration.
"""
import sys
from pathlib import Path

# Python adds this script's directory (scripts/pipeline/) to sys.path automatically
# when invoked directly — all sibling packages (core, content_eval, extraction, …)
# are therefore importable without any PYTHONPATH prefix.
_HERE = Path(__file__).resolve().parent
_PIPELINE = _HERE.parents[1]
_SCRIPTS = _HERE.parents[2]
for _path in (_SCRIPTS, _PIPELINE):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from config_loader import resolve_content_repo  # noqa: E402

from content_eval.cli import main

if __name__ == "__main__":
    main()
