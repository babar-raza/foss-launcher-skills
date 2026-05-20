# Adapted from aspose.org
"""Prerequisite checker for pipeline entry points.

Provides clear, actionable error messages when required artifacts are missing,
instead of cryptic Python tracebacks.

Public API::

    check_venv()                            -> PrerequisiteResult
    check_clone_cache(family, platform)     -> PrerequisiteResult
    check_knowledge_model(family, platform) -> PrerequisiteResult
    check_api_surface(family, platform)     -> PrerequisiteResult
    check_all(family, platform, ...)        -> list[PrerequisiteResult]  (failures only)
    require_all(family, platform, ...)      -> None  (exits on failure)
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

_DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[3]
_REPO_ROOT = _DEFAULT_REPO_ROOT


def configure(*, repo_root: "Path | str | None" = None) -> None:
    """Override module-level path constants for testing."""
    global _REPO_ROOT
    _REPO_ROOT = Path(repo_root) if repo_root is not None else _DEFAULT_REPO_ROOT


@dataclass
class PrerequisiteResult:
    """Result of a single prerequisite check."""

    ok: bool
    message: str = ""

    @classmethod
    def success(cls) -> "PrerequisiteResult":
        return cls(ok=True)

    @classmethod
    def fail(cls, message: str) -> "PrerequisiteResult":
        return cls(ok=False, message=message)


def check_venv() -> PrerequisiteResult:
    """Check that the Python venv is present."""
    venv_python = _REPO_ROOT / ".venv" / "Scripts" / "python.exe"
    if not venv_python.exists():
        venv_python = _REPO_ROOT / ".venv" / "bin" / "python"
    if not venv_python.exists():
        return PrerequisiteResult.fail(
            f"Python venv not found at {_REPO_ROOT / '.venv'}. "
            f"Run: python -m venv .venv && .venv/Scripts/pip install -r requirements.txt"
        )
    return PrerequisiteResult.success()


def check_clone_cache(family: str, platform: str) -> PrerequisiteResult:
    """Check that clone cache exists for the given family/platform."""
    env_override = os.environ.get("ASPOSE_CLONE_CACHE", "")
    if env_override:
        cache_root = Path(env_override)
    else:
        cache_root = _REPO_ROOT / "runs" / ".clone_cache"

    cache_dir = cache_root / f"aspose_{family}_{platform}"
    if not cache_dir.exists():
        cache_dir = cache_root / f"Aspose.{family.capitalize()}-for-{platform.capitalize()}"
        if not cache_dir.exists():
            return PrerequisiteResult.fail(
                f"Clone cache not found for {family}/{platform}. "
                f"Expected at: {cache_root / f'aspose_{family}_{platform}'}. "
                f"Run /getting-started step 4 to populate the clone cache, "
                f"or set ASPOSE_CLONE_CACHE to the correct location."
            )
    return PrerequisiteResult.success()


def check_knowledge_model(family: str, platform: str) -> PrerequisiteResult:
    """Check that knowledge model exists."""
    model_path = _REPO_ROOT / "knowledge" / family / platform / "merged" / "model.yaml"
    if not model_path.exists():
        return PrerequisiteResult.fail(
            f"Knowledge model not found at {model_path}. "
            f"Run /knowledge-bootstrap {family} {platform} first."
        )
    return PrerequisiteResult.success()


def check_api_surface(family: str, platform: str) -> PrerequisiteResult:
    """Check that api_surface.json exists."""
    api_path = _REPO_ROOT / "knowledge" / family / platform / "merged" / "api_surface.json"
    if not api_path.exists():
        return PrerequisiteResult.fail(
            f"api_surface.json not found at {api_path}. "
            f"Run /knowledge-bootstrap {family} {platform} first."
        )
    return PrerequisiteResult.success()


def check_all(
    family: str,
    platform: str,
    needs_clone_cache: bool = False,
) -> list[PrerequisiteResult]:
    """Run all prerequisite checks, return list of failures only."""
    checks = [
        check_venv(),
        check_knowledge_model(family, platform),
        check_api_surface(family, platform),
    ]
    if needs_clone_cache:
        checks.append(check_clone_cache(family, platform))
    return [r for r in checks if not r.ok]


def require_all(
    family: str,
    platform: str,
    needs_clone_cache: bool = False,
) -> None:
    """Check all prerequisites, exit with clear message if any fail."""
    failures = check_all(family, platform, needs_clone_cache=needs_clone_cache)
    if failures:
        for f in failures:
            print(f"PREREQUISITE FAILED: {f.message}", file=sys.stderr)
        print(
            f"\nRun /getting-started to set up the environment.",
            file=sys.stderr,
        )
        sys.exit(1)
