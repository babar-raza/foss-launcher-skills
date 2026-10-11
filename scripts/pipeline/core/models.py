"""Unified data models for the pipeline.

Previously, ``token_ops.py`` and ``content_eval/models.py`` each defined a
``Finding`` class with incompatible fields.  This module provides a single
``Finding`` that works for both audit-style (positional) and eval-style
(keyword) call sites.

Migration
---------
* ``token_ops.Finding`` — positional: ``Finding("FAIL", path, 1, "msg")``
  still works (category="" and evaluator="" default to empty string).
* ``content_eval/models.Finding`` — keyword: ``Finding(level="WARN",
  category="AA", filepath=str(path), ...)`` still works.

Identity
--------
The stable ``id`` property excludes ``category`` and ``evaluator`` so that
audit.py and api_accuracy.py produce the *same* ID for the same underlying
problem.  Deduplication in aggregation layers must be applied explicitly.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path


@dataclass(frozen=True)
class Finding:
    """A single pipeline finding with a stable, deterministic ID.

    Parameters
    ----------
    level:
        Severity — one of ``"FAIL"``, ``"WARN"``, ``"INFO"``.
    filepath:
        Absolute or repo-relative path to the file this finding refers to.
        May be a ``Path`` or a ``str``; stored as provided.
    line_no:
        1-based line number, or 0 when no specific line applies.
    message:
        Human-readable description of the issue.
    suggestion:
        Optional remediation hint.
    category:
        Evaluator category code (e.g. ``"AA"``, ``"PT"``, ``"PIPELINE"``).
        Empty string for audit-style findings.
    evaluator:
        Name of the evaluator that produced this finding.
        Empty string for audit-style findings.
    """

    level: str
    filepath: Path | str
    line_no: int
    message: str
    suggestion: str = ""
    category: str = ""
    evaluator: str = ""

    @cached_property
    def id(self) -> str:
        """Deterministic 8-hex-char ID: ``CE-{hash}``."""
        raw = f"{self.level}|{self.filepath}|{self.line_no}|{self.message}"
        return "CE-" + hashlib.sha256(raw.encode()).hexdigest()[:8]
