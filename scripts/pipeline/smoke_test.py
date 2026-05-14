#!/usr/bin/env python3
"""Compatibility wrapper for commands.diagnostics.smoke_test."""
from __future__ import annotations

import runpy
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

if __name__ == "__main__":
    runpy.run_module("scripts.pipeline.commands.diagnostics.smoke_test", run_name="__main__", alter_sys=True)
