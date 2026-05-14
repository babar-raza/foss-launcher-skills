#!/usr/bin/env python3
"""Compatibility wrapper for commands.diagnostics.repo_patrol."""
from __future__ import annotations

import runpy
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PIPELINE_ROOT = Path(__file__).resolve().parent
for path in (REPO_ROOT, PIPELINE_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

if __name__ == "__main__":
    runpy.run_module("commands.diagnostics.repo_patrol", run_name="__main__", alter_sys=True)
