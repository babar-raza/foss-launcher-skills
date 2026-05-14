import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from config_loader import ConfigError
from content_repo_adapter import (  # noqa: E402
    ASPOSE_CONTENT_ROOT,
    assert_write_allowed,
    build_context,
    metrics_mode,
    resolve_clone_cache,
    resolve_content_root,
    resolve_output_root,
)


def test_resolve_content_root_prefers_env(tmp_path):
    env_root = tmp_path / "content-env"
    cfg_root = tmp_path / "content-config"
    env_root.mkdir()
    cfg_root.mkdir()
    result = resolve_content_root({"content_root": str(cfg_root)}, {"CONTENT_REPO_PATH": str(env_root)})
    assert result == env_root.resolve()


def test_resolve_content_root_supports_content_root_config(tmp_path):
    root = tmp_path / "content"
    root.mkdir()
    result = resolve_content_root({"content_root": str(root)}, {})
    assert result == root.resolve()


def test_resolve_content_root_supports_legacy_content_repo_config(tmp_path):
    root = tmp_path / "legacy-content"
    root.mkdir()
    result = resolve_content_root({"content_repo": str(root)}, {})
    assert result == root.resolve()


def test_resolve_content_root_fails_closed_when_missing():
    with pytest.raises(ConfigError, match="Content root not configured"):
        resolve_content_root({}, {})


def test_resolve_content_root_requires_existing_directory_by_default(tmp_path):
    missing = tmp_path / "missing"
    with pytest.raises(ConfigError, match="does not exist"):
        resolve_content_root({"content_root": str(missing)}, {})


def test_resolve_output_root_prefers_explicit_arg(tmp_path):
    explicit = tmp_path / "explicit"
    config_root = tmp_path / "config"
    assert resolve_output_root(explicit, {"output_root": str(config_root)}) == explicit.resolve()


def test_resolve_output_root_uses_config_then_default(tmp_path):
    config_root = tmp_path / "config"
    assert resolve_output_root(None, {"output_root": str(config_root)}) == config_root.resolve()
    assert resolve_output_root(None, {}, default=tmp_path / "default") == (tmp_path / "default").resolve()


def test_resolve_clone_cache_rejects_obsolete_foss_launcher_path():
    with pytest.raises(ConfigError, match="obsolete clone-cache"):
        resolve_clone_cache({}, {"ASPOSE_CLONE_CACHE": "x/foss-launcher/runs/.clone_cache/y"})


def test_resolve_clone_cache_prefers_env(tmp_path):
    env_cache = tmp_path / "env-cache"
    cfg_cache = tmp_path / "cfg-cache"
    result = resolve_clone_cache({"clone_cache": str(cfg_cache)}, {"ASPOSE_CLONE_CACHE": str(env_cache)})
    assert result == env_cache.resolve()


def test_metrics_mode_defaults_to_dry_run():
    assert metrics_mode({}) == "dry-run"


def test_metrics_mode_submit_requires_endpoint_and_token():
    assert metrics_mode({}, submit=True) == "disabled"
    env = {"AGENT_METRICS_ENDPOINT": "https://metrics.example", "AGENT_METRICS_TOKEN": "secret"}
    assert metrics_mode(env, submit=True) == "submit"


def test_assert_write_allowed_allows_non_aspose_target(tmp_path):
    target = tmp_path / "content" / "page.md"
    assert assert_write_allowed(target) == target.resolve()


def test_assert_write_allowed_blocks_live_aspose_content():
    target = ASPOSE_CONTENT_ROOT / "docs.aspose.org" / "en" / "x.md"
    with pytest.raises(ConfigError, match="Refusing write"):
        assert_write_allowed(target)


def test_assert_write_allowed_dry_run_allows_reporting_forbidden_target():
    target = ASPOSE_CONTENT_ROOT / "docs.aspose.org" / "en" / "x.md"
    assert assert_write_allowed(target, dry_run=True) == target.resolve()


def test_build_context_resolves_all_fields(tmp_path):
    content = tmp_path / "content"
    content.mkdir()
    output = tmp_path / "out"
    cache = tmp_path / "cache"
    context = build_context(
        {"content_root": str(content), "output_root": str(output), "clone_cache": str(cache)},
        {},
        dry_run=True,
    )
    assert context.content_root == content.resolve()
    assert context.output_root == output.resolve()
    assert context.clone_cache == cache.resolve()
    assert context.metrics_mode == "dry-run"
    assert context.dry_run is True
