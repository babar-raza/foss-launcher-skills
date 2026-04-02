"""Tests for scripts/config_loader.py — path resolution and config loading."""
import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from config_loader import (  # noqa: E402
    ConfigError,
    golden_corpus_config,
    load_config,
    resolve_content_path,
    resolve_content_repo,
    resolve_knowledge_path,
    resolve_knowledge_root,
    resolve_reports_root,
)


# ---------------------------------------------------------------------------
# load_config
# ---------------------------------------------------------------------------

def test_load_config_returns_dict():
    cfg = load_config()
    assert isinstance(cfg, dict)


def test_load_config_has_sites():
    cfg = load_config()
    assert "sites" in cfg, "config.yaml must define 'sites'"


def test_load_config_has_knowledge_path():
    cfg = load_config()
    assert "knowledge_path" in cfg


def test_load_config_has_forbidden_paths():
    cfg = load_config()
    assert "forbidden_paths" in cfg
    assert isinstance(cfg["forbidden_paths"], list)


def test_load_config_sites_keys():
    cfg = load_config()
    sites = cfg["sites"]
    for expected in ("docs", "blog", "kb", "products", "reference"):
        assert expected in sites, f"sites must contain '{expected}'"


# ---------------------------------------------------------------------------
# resolve_content_path
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("site_type", ["docs", "blog", "kb", "reference"])
def test_resolve_content_path_contains_family_and_platform(site_type, tmp_path, monkeypatch):
    monkeypatch.setenv("CONTENT_REPO_PATH", str(tmp_path))
    path = resolve_content_path(site_type, "words", "python")
    assert "words" in str(path)
    assert "python" in str(path)


def test_resolve_content_path_products_has_family(tmp_path, monkeypatch):
    monkeypatch.setenv("CONTENT_REPO_PATH", str(tmp_path))
    path = resolve_content_path("products", "words")
    assert "words" in str(path)


def test_resolve_content_path_unknown_raises():
    with pytest.raises(ValueError, match="Unknown site type"):
        resolve_content_path("nonexistent", "words", "python")


# ---------------------------------------------------------------------------
# resolve_knowledge_path
# ---------------------------------------------------------------------------

def test_resolve_knowledge_path_contains_family():
    path = resolve_knowledge_path("words", "python")
    assert "words" in str(path)


def test_resolve_knowledge_path_contains_platform():
    path = resolve_knowledge_path("words", "python")
    assert "python" in str(path)


def test_resolve_knowledge_path_returns_path_object():
    path = resolve_knowledge_path("cells", "dotnet")
    assert isinstance(path, Path)


# ---------------------------------------------------------------------------
# golden_corpus_config
# ---------------------------------------------------------------------------

def test_golden_corpus_config_returns_dict():
    cfg = golden_corpus_config()
    assert isinstance(cfg, dict)


def test_golden_corpus_config_sample_count():
    cfg = golden_corpus_config()
    assert "sample_count" in cfg
    assert isinstance(cfg["sample_count"], int)
    assert cfg["sample_count"] > 0


def test_golden_corpus_config_min_words():
    cfg = golden_corpus_config()
    assert "min_words" in cfg
    assert cfg["min_words"] > 0


def test_golden_corpus_config_profile_dir():
    cfg = golden_corpus_config()
    assert "profile_dir" in cfg
    assert cfg["profile_dir"]


# ---------------------------------------------------------------------------
# resolve_content_repo with env override
# ---------------------------------------------------------------------------

def test_resolve_content_repo_env_override(tmp_path, monkeypatch):
    monkeypatch.setenv("CONTENT_REPO_PATH", str(tmp_path))
    result = resolve_content_repo()
    assert result == tmp_path.resolve()


def test_resolve_content_repo_raises_without_config(monkeypatch):
    """ConfigError is raised when no content_repo is configured — no silent CWD fallback."""
    monkeypatch.delenv("CONTENT_REPO_PATH", raising=False)
    with pytest.raises(ConfigError):
        resolve_content_repo()


# ---------------------------------------------------------------------------
# resolve_knowledge_root
# ---------------------------------------------------------------------------

def test_resolve_knowledge_root_returns_path():
    result = resolve_knowledge_root()
    assert isinstance(result, Path)


def test_resolve_knowledge_root_contains_knowledge():
    result = resolve_knowledge_root()
    assert "knowledge" in str(result)


def test_resolve_knowledge_root_default_is_knowledge():
    """Default knowledge_root should be 'knowledge' (matches config.yaml)."""
    result = resolve_knowledge_root()
    assert result == Path("knowledge")


# ---------------------------------------------------------------------------
# resolve_reports_root
# ---------------------------------------------------------------------------

def test_resolve_reports_root_returns_path():
    result = resolve_reports_root()
    assert isinstance(result, Path)


def test_resolve_reports_root_contains_reports():
    result = resolve_reports_root()
    assert "reports" in str(result)


def test_resolve_reports_root_default_is_reports():
    """Default reports_path should be 'reports' (matches config.yaml)."""
    result = resolve_reports_root()
    assert result == Path("reports")
