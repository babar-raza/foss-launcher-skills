"""Global constants for pipeline scripts.

Ported from aspose.org scripts/pipeline/core/constants.py with aspose-specific paths removed.
"""
import os
import pathlib

# Repo root (3 levels up from this file: core/ -> pipeline/ -> scripts/ -> repo root)
REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]

# Default pipeline config
DEFAULT_RUNS_ROOT = REPO_ROOT / "runs"
DEFAULT_REPORTS_ROOT = REPO_ROOT / "reports"

# Environment variable names (foss-launcher uses config_loader as primary)
CONTENT_ROOT_ENV = "CONTENT_ROOT"
KNOWLEDGE_ROOT_ENV = "KNOWLEDGE_ROOT"
