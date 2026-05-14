#!/usr/bin/env python3
"""Compatibility wrapper for scripts/gap-eval/src/run.py."""
from __future__ import annotations

import importlib.util
from pathlib import Path

_TARGET = Path(__file__).resolve().parent / "src" / "run.py"
_SPEC = importlib.util.spec_from_file_location("standalone_gap_eval_run", _TARGET)
if _SPEC is None or _SPEC.loader is None:  # pragma: no cover
    raise SystemExit(f"Unable to load {_TARGET}")
_MODULE = importlib.util.module_from_spec(_SPEC)
import sys
sys.modules[_SPEC.name] = _MODULE
_SPEC.loader.exec_module(_MODULE)

if __name__ == "__main__":
    raise SystemExit(_MODULE.main())
