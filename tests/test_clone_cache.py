import os
import subprocess
import sys

import pytest

from scripts.pipeline.core.clone_cache import cache_root, clone_exists, clone_path

REPO_ROOT = os.path.dirname(os.path.dirname(__file__))


def test_cache_root_default(monkeypatch):
    monkeypatch.delenv("ASPOSE_CLONE_CACHE", raising=False)

    root = cache_root()

    assert root.name == ".clone_cache"
    assert root.parent.name == "runs"
    assert "aspose.org" not in str(root).lower()


def test_cache_root_env_override(tmp_path, monkeypatch):
    monkeypatch.setenv("ASPOSE_CLONE_CACHE", str(tmp_path / "custom_cache"))

    assert cache_root() == (tmp_path / "custom_cache").resolve()


def test_cache_root_rejects_obsolete_foss_launcher_variants(monkeypatch):
    for value in (
        "/some/path/foss-launcher/runs/.clone_cache",
        r"C:\foss-launcher\runs\.clone_cache",
        "/some/path/foss_launcher/runs/.clone_cache",
    ):
        monkeypatch.setenv("ASPOSE_CLONE_CACHE", value)
        with pytest.raises(ValueError, match="obsolete foss-launcher"):
            cache_root()


def test_clone_path_uses_flat_aspose_prefix(tmp_path, monkeypatch):
    monkeypatch.setenv("ASPOSE_CLONE_CACHE", str(tmp_path))

    path = clone_path("3d", "net")

    assert path == tmp_path.resolve() / "aspose_3d_net"


def test_clone_exists_requires_git_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("ASPOSE_CLONE_CACHE", str(tmp_path))
    clone_dir = tmp_path / "aspose_3d_net"
    clone_dir.mkdir()

    assert clone_exists("3d", "net") is False

    (clone_dir / ".git").mkdir()
    assert clone_exists("3d", "net") is True


def test_cli_resolve_existing_clone_no_network(tmp_path):
    clone_dir = tmp_path / "aspose_3d_net"
    clone_dir.mkdir()
    (clone_dir / ".git").mkdir()

    result = subprocess.run(
        [
            sys.executable,
            str(os.path.join(REPO_ROOT, "scripts", "pipeline", "core", "clone_cache.py")),
            "resolve",
            "3d",
            "net",
        ],
        capture_output=True,
        text=True,
        env={**os.environ, "ASPOSE_CLONE_CACHE": str(tmp_path)},
    )

    assert result.returncode == 0, result.stderr
    assert "aspose_3d_net" in result.stdout


def test_cli_errors_without_registry_or_existing_clone(tmp_path):
    result = subprocess.run(
        [
            sys.executable,
            str(os.path.join(REPO_ROOT, "scripts", "pipeline", "core", "clone_cache.py")),
            "resolve",
            "missing",
            "fake",
        ],
        capture_output=True,
        text=True,
        env={**os.environ, "ASPOSE_CLONE_CACHE": str(tmp_path)},
    )

    assert result.returncode == 1
    assert "error:" in result.stderr


def test_cli_usage_errors():
    result = subprocess.run(
        [sys.executable, os.path.join(REPO_ROOT, "scripts", "pipeline", "core", "clone_cache.py")],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "Usage" in result.stderr
