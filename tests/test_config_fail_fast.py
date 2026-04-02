"""Tests for hardened config_loader.py behavior.

Verifies:
  1. Missing content_repo raises ConfigError (no silent CWD fallback)
  2. Bad path in env var raises ConfigError with clear message
  3. Bad path in config.yaml raises ConfigError
  4. Missing required config keys raises ConfigError at load time
  5. Valid config resolves correctly and logs source to stderr
"""
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import config_loader
from config_loader import ConfigError, resolve_content_repo, load_config


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_config(tmp_path, data: dict) -> Path:
    """Write a config.yaml to tmp_path and return the path."""
    import yaml
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(yaml.dump(data), encoding="utf-8")
    return cfg_path


_MINIMAL_VALID_CONFIG = {
    "content_repo": "",  # empty — will be set per test
    "sites": {
        "docs": {"content_path": "content/docs.aspose.org/en/{family}/{platform}/"},
    },
    "knowledge_root": "knowledge",
    "reports_path": "reports",
}


# ---------------------------------------------------------------------------
# No CWD fallback
# ---------------------------------------------------------------------------

class TestNoCWDFallback:
    def test_no_env_no_config_raises_config_error(self, tmp_path, monkeypatch):
        """Without env var or config setting, must raise ConfigError — not return CWD."""
        monkeypatch.delenv("CONTENT_REPO_PATH", raising=False)

        cfg = dict(_MINIMAL_VALID_CONFIG)
        cfg["content_repo"] = ""  # empty
        _write_config(tmp_path, cfg)

        with patch.object(config_loader, "_find_config", return_value=tmp_path / "config.yaml"):
            with pytest.raises(ConfigError, match="not configured"):
                resolve_content_repo()

    def test_raises_not_returns_cwd(self, tmp_path, monkeypatch):
        """The return value must never be Path.cwd() from the fallback path."""
        monkeypatch.delenv("CONTENT_REPO_PATH", raising=False)
        cfg = dict(_MINIMAL_VALID_CONFIG)
        cfg["content_repo"] = ""
        _write_config(tmp_path, cfg)

        with patch.object(config_loader, "_find_config", return_value=tmp_path / "config.yaml"):
            try:
                result = resolve_content_repo()
                # If it didn't raise, it must not have returned CWD
                assert result != Path.cwd().resolve(), (
                    "Regression: resolve_content_repo() returned CWD fallback"
                )
            except ConfigError:
                pass  # Expected


# ---------------------------------------------------------------------------
# Env var validation
# ---------------------------------------------------------------------------

class TestEnvVarValidation:
    def test_valid_env_path_resolved(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setenv("CONTENT_REPO_PATH", str(tmp_path))
        result = resolve_content_repo()
        assert result == tmp_path.resolve()

    def test_valid_env_path_logs_source(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setenv("CONTENT_REPO_PATH", str(tmp_path))
        resolve_content_repo()
        captured = capsys.readouterr()
        assert "env:CONTENT_REPO_PATH" in captured.err

    def test_nonexistent_env_path_raises(self, tmp_path, monkeypatch):
        nonexistent = str(tmp_path / "does_not_exist")
        monkeypatch.setenv("CONTENT_REPO_PATH", nonexistent)
        with pytest.raises(ConfigError, match="CONTENT_REPO_PATH"):
            resolve_content_repo()

    def test_nonexistent_env_path_error_includes_var_name(self, tmp_path, monkeypatch):
        bad_path = str(tmp_path / "ghost_dir")
        monkeypatch.setenv("CONTENT_REPO_PATH", bad_path)
        with pytest.raises(ConfigError) as exc_info:
            resolve_content_repo()
        # Error message must reference the env var name so operator knows what to fix
        assert "CONTENT_REPO_PATH" in str(exc_info.value)


# ---------------------------------------------------------------------------
# Config.yaml path validation
# ---------------------------------------------------------------------------

class TestConfigYamlPathValidation:
    def test_valid_config_path_resolved(self, tmp_path, monkeypatch):
        monkeypatch.delenv("CONTENT_REPO_PATH", raising=False)
        cfg = dict(_MINIMAL_VALID_CONFIG)
        cfg["content_repo"] = str(tmp_path)
        _write_config(tmp_path, cfg)

        with patch.object(config_loader, "_find_config", return_value=tmp_path / "config.yaml"):
            result = resolve_content_repo()
        assert result == tmp_path.resolve()

    def test_nonexistent_config_path_raises(self, tmp_path, monkeypatch):
        monkeypatch.delenv("CONTENT_REPO_PATH", raising=False)
        cfg = dict(_MINIMAL_VALID_CONFIG)
        cfg["content_repo"] = str(tmp_path / "does_not_exist")
        _write_config(tmp_path, cfg)

        with patch.object(config_loader, "_find_config", return_value=tmp_path / "config.yaml"):
            with pytest.raises(ConfigError, match="content_repo"):
                resolve_content_repo()

    def test_valid_config_path_logs_source(self, tmp_path, monkeypatch, capsys):
        monkeypatch.delenv("CONTENT_REPO_PATH", raising=False)
        cfg = dict(_MINIMAL_VALID_CONFIG)
        cfg["content_repo"] = str(tmp_path)
        _write_config(tmp_path, cfg)

        with patch.object(config_loader, "_find_config", return_value=tmp_path / "config.yaml"):
            resolve_content_repo()
        captured = capsys.readouterr()
        assert "config.yaml" in captured.err


# ---------------------------------------------------------------------------
# Required config keys
# ---------------------------------------------------------------------------

class TestRequiredConfigKeys:
    def test_valid_config_loads_successfully(self, tmp_path):
        _write_config(tmp_path, _MINIMAL_VALID_CONFIG)
        with patch.object(config_loader, "_find_config", return_value=tmp_path / "config.yaml"):
            cfg = load_config()
        assert cfg is not None

    def test_missing_sites_raises(self, tmp_path):
        cfg = dict(_MINIMAL_VALID_CONFIG)
        del cfg["sites"]
        _write_config(tmp_path, cfg)
        with patch.object(config_loader, "_find_config", return_value=tmp_path / "config.yaml"):
            with pytest.raises(ConfigError, match="sites"):
                load_config()

    def test_missing_knowledge_root_raises(self, tmp_path):
        cfg = dict(_MINIMAL_VALID_CONFIG)
        del cfg["knowledge_root"]
        _write_config(tmp_path, cfg)
        with patch.object(config_loader, "_find_config", return_value=tmp_path / "config.yaml"):
            with pytest.raises(ConfigError, match="knowledge_root"):
                load_config()

    def test_missing_reports_path_raises(self, tmp_path):
        cfg = dict(_MINIMAL_VALID_CONFIG)
        del cfg["reports_path"]
        _write_config(tmp_path, cfg)
        with patch.object(config_loader, "_find_config", return_value=tmp_path / "config.yaml"):
            with pytest.raises(ConfigError, match="reports_path"):
                load_config()

    def test_missing_config_file_raises(self, tmp_path):
        """Missing config.yaml raises ConfigError (not returns {})."""
        with patch.object(config_loader, "_find_config",
                          return_value=tmp_path / "nonexistent.yaml"):
            with pytest.raises(ConfigError, match="config.yaml not found"):
                load_config()
