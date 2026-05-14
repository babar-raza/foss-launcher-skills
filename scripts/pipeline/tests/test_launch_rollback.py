"""Compatibility test surface for launch rollback parity.

The project pytest configuration runs tests from ``tests/``. This file exists
because the reference skill contract names ``scripts/pipeline/tests`` as the
historical verification location.
"""

from pathlib import Path

from scripts.pipeline.commands.launch import launch_rollback


def test_launch_rollback_rejects_non_content_paths(tmp_path: Path) -> None:
    launch_rollback.configure(repo_root=tmp_path)
    classified = launch_rollback.classify_files(["scripts/pipeline/bad.py"])
    assert classified["protected"] == ["scripts/pipeline/bad.py"]
