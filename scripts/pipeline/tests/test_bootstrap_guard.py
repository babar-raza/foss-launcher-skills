"""test_bootstrap_guard.py — Verify pipeline package entry points self-bootstrap.

Healing Sprint (F-3) regression test: confirms that packages invocable as
`python -m <package>` work from repo root without any PYTHONPATH prefix.
Previously, `python -m content_eval` failed because __main__.py had no
sys.path bootstrap, requiring the operator to set PYTHONPATH=scripts/pipeline.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]  # scripts/pipeline/tests/ → repo root
PIPELINE_DIR = REPO_ROOT / "scripts" / "pipeline"


def _run_module(module: str, args: list[str] | None = None) -> subprocess.CompletedProcess:
    """Run `python -m {module}` from repo root with a clean environment (no PYTHONPATH)."""
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    cmd = [sys.executable, "-m", module] + (args or [])
    return subprocess.run(
        cmd,
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )


def _run_wrapper(wrapper: str, args: list[str] | None = None) -> subprocess.CompletedProcess:
    """Run a pipeline command script from repo root with a clean environment."""
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    script = PIPELINE_DIR / wrapper
    cmd = [sys.executable, str(script)] + (args or [])
    return subprocess.run(
        cmd,
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )


class TestContentEvalBootstrap:
    """F-3: content_eval must be invocable without PYTHONPATH prefix.

    The durable fix has two parts:
    1. run_content_eval.py wrapper — invokable as `python scripts/pipeline/run_content_eval.py`
       without any PYTHONPATH prefix (Python auto-adds the script's dir to sys.path).
    2. content_eval/__main__.py bootstrap — adds scripts/pipeline/ to sys.path so that
       inner imports (from core.markdown, etc.) work when the package IS already found.
    """

    def test_wrapper_importable_without_pythonpath(self):
        """Regression test for the PYTHONPATH=scripts/pipeline workaround.

        Before the fix: operator had to prepend PYTHONPATH=scripts/pipeline.
        After the fix: python scripts/pipeline/run_content_eval.py --help works directly.
        """
        result = _run_wrapper("commands/content/run_content_eval.py", ["--help"])
        assert result.returncode == 0, (
            f"python scripts/pipeline/run_content_eval.py --help failed without PYTHONPATH.\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )
        combined = result.stdout + result.stderr
        assert "content_eval" in combined.lower() or "usage" in combined.lower(), (
            "Expected usage output from run_content_eval.py --help"
        )

    def test_module_invocable_from_pipeline_dir(self):
        """python -m content_eval --help must work when cwd is scripts/pipeline/."""
        env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
        result = subprocess.run(
            [sys.executable, "-m", "content_eval", "--help"],
            cwd=str(PIPELINE_DIR),
            capture_output=True,
            text=True,
            env=env,
            timeout=30,
        )
        assert result.returncode == 0, (
            f"python -m content_eval --help failed from pipeline dir.\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )


class TestApiSurfaceKindValues:
    """F-6: api_surface.py must emit the tree-sitter node type names that S-62 now documents.

    These tests catch any future rename of _CLASS_TYPES constants that would
    silently break the batch-reference filter without a test failure.
    """

    def _get_class_types(self) -> dict:
        """Import _CLASS_TYPES from tree_helpers without touching sys.path (conftest does it)."""
        sys.path.insert(0, str(PIPELINE_DIR))
        from extraction.tree_helpers import _CLASS_TYPES
        return _CLASS_TYPES

    def test_net_kinds_match_skill_spec(self):
        """S-62 spec lists class_declaration, interface_declaration, enum_declaration,
        struct_declaration for .NET — verify tree_helpers emits these."""
        ct = self._get_class_types()
        net_kinds = ct["csharp"]
        assert "class_declaration" in net_kinds
        assert "interface_declaration" in net_kinds
        assert "enum_declaration" in net_kinds
        assert "struct_declaration" in net_kinds

    def test_java_kinds_match_skill_spec(self):
        """S-62 spec lists class_declaration, interface_declaration, enum_declaration for Java."""
        ct = self._get_class_types()
        java_kinds = ct["java"]
        assert "class_declaration" in java_kinds
        assert "interface_declaration" in java_kinds
        assert "enum_declaration" in java_kinds

    def test_python_kind_is_class_definition(self):
        """S-62 spec says Python classes have kind == 'class_definition' (not 'class')."""
        ct = self._get_class_types()
        python_kinds = ct["python"]
        assert "class_definition" in python_kinds
        assert "class" not in python_kinds  # old simplified name must not appear

    def test_cpp_kinds_are_specifiers(self):
        """S-62 spec says C++ classes are class_specifier / enum_specifier."""
        ct = self._get_class_types()
        cpp_kinds = ct["cpp"]
        assert "class_specifier" in cpp_kinds
        assert "enum_specifier" in cpp_kinds
        # Should NOT contain the declaration form used by Java/C#
        assert "class_declaration" not in cpp_kinds

    def test_typescript_kinds_match_skill_spec(self):
        """S-62 spec lists class_declaration, interface_declaration, enum_declaration for TS."""
        ct = self._get_class_types()
        ts_kinds = ct["typescript"]
        assert "class_declaration" in ts_kinds
        assert "interface_declaration" in ts_kinds
        assert "enum_declaration" in ts_kinds
