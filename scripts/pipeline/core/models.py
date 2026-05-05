"""Shared data models for pipeline scripts.

Ported from aspose.org scripts/pipeline/core/models.py.
Uses pure dataclasses; no aspose-specific fields.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class FileRecord:
    """Represents a single content file with metadata."""
    path: str
    family: str = ""
    platform: str = ""
    subdomain: str = ""
    grade: Optional[str] = None
    draft: bool = False


@dataclass
class RunState:
    """State for a pipeline run."""
    run_id: str
    family: str
    platform: str
    baseline_git_sha: str = ""
    status: str = "RUNNING"
    files_in_scope: List[str] = field(default_factory=list)
