"""Tests for core.prereqs — prerequisite checker for pipeline entry points."""
import pytest
from pathlib import Path


def test_prerequisite_result_factory():
    """PrerequisiteResult factory methods produce correct instances."""
    from core.prereqs import PrerequisiteResult

    ok = PrerequisiteResult.success()
    assert ok.ok is True
    assert ok.message == ""

    fail = PrerequisiteResult.fail("test error")
    assert fail.ok is False
    assert fail.message == "test error"


def test_check_venv_finds_existing(tmp_path):
    """check_venv should succeed when .venv/Scripts/python.exe exists."""
    from unittest.mock import patch
    from core.prereqs import check_venv

    # Create a fake venv structure
    venv_python = tmp_path / ".venv" / "Scripts" / "python.exe"
    venv_python.parent.mkdir(parents=True)
    venv_python.touch()

    with patch("core.prereqs._REPO_ROOT", tmp_path):
        result = check_venv()
    assert result.ok


def test_check_venv_missing(tmp_path):
    """check_venv should fail when .venv does not exist."""
    from unittest.mock import patch
    from core.prereqs import check_venv

    with patch("core.prereqs._REPO_ROOT", tmp_path):
        result = check_venv()
    assert not result.ok
    assert ".venv" in result.message


def test_check_knowledge_model_missing():
    """Missing model.yaml should return failure with actionable message."""
    from core.prereqs import check_knowledge_model

    result = check_knowledge_model("nonexistent", "fake")
    assert not result.ok
    assert "model.yaml" in result.message
    assert "nonexistent" in result.message


def test_check_api_surface_missing():
    """Missing api_surface.json should return failure with actionable message."""
    from core.prereqs import check_api_surface

    result = check_api_surface("nonexistent", "fake")
    assert not result.ok
    assert "api_surface.json" in result.message


def test_check_clone_cache_missing():
    """Missing clone cache should return failure with actionable message."""
    from core.prereqs import check_clone_cache

    result = check_clone_cache("nonexistent", "fake")
    assert not result.ok
    assert "Clone cache" in result.message
    assert "nonexistent" in result.message


def test_check_all_returns_failures_only():
    """check_all should return only the failing checks."""
    from core.prereqs import check_all

    failures = check_all("nonexistent", "fake")
    # venv check may pass, but knowledge model and api_surface will fail
    assert len(failures) >= 2
    messages = " ".join(f.message for f in failures)
    assert "model.yaml" in messages
    assert "api_surface.json" in messages


def test_check_all_with_clone_cache():
    """check_all with needs_clone_cache adds clone cache check."""
    from core.prereqs import check_all

    without = check_all("nonexistent", "fake", needs_clone_cache=False)
    with_cache = check_all("nonexistent", "fake", needs_clone_cache=True)
    assert len(with_cache) > len(without)


def test_require_all_exits_on_failure():
    """require_all should call sys.exit(1) when prerequisites fail."""
    from core.prereqs import require_all

    with pytest.raises(SystemExit) as exc_info:
        require_all("nonexistent", "fake")
    assert exc_info.value.code == 1
