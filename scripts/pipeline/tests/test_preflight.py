"""Tests for scripts/pipeline/preflight.py."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_PREFLIGHT = _REPO_ROOT / "scripts" / "pipeline" / "commands" / "launch" / "preflight.py"


def _run(path: str, *, json_mode: bool = False) -> subprocess.CompletedProcess:
    cmd = [sys.executable, str(_PREFLIGHT)]
    if json_mode:
        cmd.append("--json")
    cmd.append(path)
    return subprocess.run(cmd, capture_output=True, text=True, cwd=str(_REPO_ROOT))


class TestPathGuard:
    def test_allowed_knowledge_path(self):
        result = _run("knowledge/cells/net/merged/model.yaml")
        assert result.returncode == 0
        assert "ALLOW" in result.stdout

    def test_forbidden_agents_md(self):
        result = _run("AGENTS.md")
        assert result.returncode == 1
        assert "DENY" in result.stdout
        assert "path_guard" in result.stdout

    def test_forbidden_themes(self):
        result = _run("themes/something.html")
        assert result.returncode == 1
        assert "DENY" in result.stdout

    def test_allowed_content_path_denied_by_content_gate(self):
        """Content path passes path_guard but fails content_gate (no marker)."""
        result = _run("content/docs.aspose.org/en/cells/net/test-page.md")
        assert result.returncode == 1
        assert "content_gate" in result.stdout
        # Should NOT have path_guard failure
        assert "path_guard" not in result.stdout

    def test_allowed_scripts_pipeline(self):
        result = _run("scripts/pipeline/some_new_script.py")
        assert result.returncode == 0
        assert "ALLOW" in result.stdout


class TestJsonOutput:
    def test_json_deny(self):
        result = _run("AGENTS.md", json_mode=True)
        assert result.returncode == 1
        data = json.loads(result.stdout)
        assert data["decision"] == "DENY"
        assert len(data["failures"]) >= 1
        assert data["failures"][0]["check"] == "path_guard"

    def test_json_allow(self):
        result = _run("knowledge/cells/net/merged/model.yaml", json_mode=True)
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert data["decision"] == "ALLOW"
        assert data["failures"] == []


class TestPythonPlacement:
    def test_repo_root_py_blocked(self):
        result = _run("bad_script.py")
        assert result.returncode == 1
        # path_guard will deny it first (not in allowlist)
        assert "DENY" in result.stdout

    def test_sanctioned_pipeline_py_allowed(self):
        result = _run("scripts/pipeline/new_tool.py")
        assert result.returncode == 0


class TestNormalization:
    def test_forward_slashes(self):
        result = _run("knowledge/cells/net/merged/model.yaml")
        assert result.returncode == 0

    def test_leading_dotslash(self):
        result = _run("./knowledge/cells/net/merged/model.yaml")
        assert result.returncode == 0
        assert "ALLOW" in result.stdout
