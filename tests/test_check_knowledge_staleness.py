"""Tests for scripts/ci/checks/check_knowledge_staleness.py."""
import sys
from pathlib import Path

import pytest

# conftest.py adds scripts/ to sys.path; import the module from ci.checks
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from ci.checks.check_knowledge_staleness import parse_product, check_staleness, main


# ---------------------------------------------------------------------------
# parse_product tests
# ---------------------------------------------------------------------------

def test_parse_product_valid_docs_path():
    result = parse_product("content/docs.aspose.org/en/cells/python/overview.md")
    assert result == ("cells", "python")


def test_parse_product_valid_blog_path():
    result = parse_product("content/blog.aspose.org/en/words/java/getting-started.md")
    assert result == ("words", "java")


def test_parse_product_backslash_normalization():
    result = parse_product("content\\docs.aspose.org\\en\\cells\\python\\overview.md")
    assert result == ("cells", "python")


def test_parse_product_invalid_path():
    assert parse_product("scripts/ci/checks/some_file.py") is None


def test_parse_product_no_platform():
    assert parse_product("content/docs.aspose.org/en/cells/") is None


# ---------------------------------------------------------------------------
# check_staleness tests
# ---------------------------------------------------------------------------

def test_check_staleness_fresh(tmp_path, monkeypatch):
    """Fresh model (stale_since: null) returns None."""
    import ci.checks.check_knowledge_staleness as mod
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)

    model_dir = tmp_path / "knowledge" / "cells" / "python"
    model_dir.mkdir(parents=True)
    (model_dir / "model.yaml").write_text(
        "family: cells\nplatform: python\nstale_since: null\n", encoding="utf-8"
    )
    assert check_staleness("cells", "python") is None


def test_check_staleness_stale(tmp_path, monkeypatch):
    """Stale model returns the stale_since date string."""
    import ci.checks.check_knowledge_staleness as mod
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)

    model_dir = tmp_path / "knowledge" / "words" / "java"
    model_dir.mkdir(parents=True)
    (model_dir / "model.yaml").write_text(
        "family: words\nplatform: java\nstale_since: 2025-06-01\n", encoding="utf-8"
    )
    result = check_staleness("words", "java")
    assert result == "2025-06-01"


def test_check_staleness_missing_model(tmp_path, monkeypatch):
    """Missing model.yaml returns None (no error)."""
    import ci.checks.check_knowledge_staleness as mod
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)

    assert check_staleness("nonexistent", "family") is None


def test_check_staleness_no_stale_since_field(tmp_path, monkeypatch):
    """Model without stale_since field returns None."""
    import ci.checks.check_knowledge_staleness as mod
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)

    model_dir = tmp_path / "knowledge" / "email" / "python"
    model_dir.mkdir(parents=True)
    (model_dir / "model.yaml").write_text(
        "family: email\nplatform: python\nrepo_sha: abc123\n", encoding="utf-8"
    )
    assert check_staleness("email", "python") is None


# ---------------------------------------------------------------------------
# main() tests
# ---------------------------------------------------------------------------

def test_main_no_args():
    """No arguments returns 0 (nothing to check)."""
    assert main([]) == 0


def test_main_no_recognizable_paths():
    """Non-content paths return 0."""
    assert main(["scripts/foo.py", "README.md"]) == 0


def test_main_fresh_product(tmp_path, monkeypatch):
    """Fresh product returns 0 with OK message."""
    import ci.checks.check_knowledge_staleness as mod
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)

    model_dir = tmp_path / "knowledge" / "cells" / "python"
    model_dir.mkdir(parents=True)
    (model_dir / "model.yaml").write_text(
        "family: cells\nplatform: python\nstale_since: null\n", encoding="utf-8"
    )
    result = main(["content/docs.aspose.org/en/cells/python/overview.md"])
    assert result == 0


def test_main_stale_product(tmp_path, monkeypatch, capsys):
    """Stale product returns 0 (advisory) but prints warning."""
    import ci.checks.check_knowledge_staleness as mod
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)

    model_dir = tmp_path / "knowledge" / "cells" / "python"
    model_dir.mkdir(parents=True)
    (model_dir / "model.yaml").write_text(
        "family: cells\nplatform: python\nstale_since: 2025-01-15\n", encoding="utf-8"
    )
    result = main(["content/docs.aspose.org/en/cells/python/overview.md"])
    assert result == 0  # advisory, not blocking
    captured = capsys.readouterr()
    assert "staleness" in captured.out.lower() or "stale" in captured.out.lower()
