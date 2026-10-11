"""Tests for check_no_raw_stale_since_gating.py — H3 (2026-09-11) regression
guard closing out the FRESH-001 migration
(reports/skill-gaps/2026-09-11-imaging-net-pipeline-hardening-prerequisites.md).
"""
from __future__ import annotations

import sys
from pathlib import Path

_CI_ROOT = Path(__file__).resolve().parent.parent / "checks"
if str(_CI_ROOT) not in sys.path:
    sys.path.insert(0, str(_CI_ROOT))

import pytest
import check_no_raw_stale_since_gating as guard  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_guard():
    yield
    guard.configure()


def _write_pipeline_file(pipeline_dir: Path, rel_path: str, body: str) -> Path:
    path = pipeline_dir / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


class TestFindViolations:
    def test_detects_is_not_none_pattern(self, tmp_path):
        guard.configure(repo_root=tmp_path)
        pipeline_dir = tmp_path / "scripts" / "pipeline"
        _write_pipeline_file(
            pipeline_dir, "commands/launch/example_gate.py",
            "if kn.stale_since is not None:\n    sys.exit(1)\n",
        )
        violations = guard.find_violations(pipeline_dir)
        assert "scripts/pipeline/commands/launch/example_gate.py" in violations
        assert violations["scripts/pipeline/commands/launch/example_gate.py"] == [1]

    def test_detects_is_none_pattern(self, tmp_path):
        guard.configure(repo_root=tmp_path)
        pipeline_dir = tmp_path / "scripts" / "pipeline"
        _write_pipeline_file(
            pipeline_dir, "commands/launch/example_gate.py",
            "if stale_since is None:\n    proceed()\n",
        )
        violations = guard.find_violations(pipeline_dir)
        assert violations == {"scripts/pipeline/commands/launch/example_gate.py": [1]}

    def test_freshness_guard_py_itself_is_exempt(self, tmp_path):
        guard.configure(repo_root=tmp_path)
        pipeline_dir = tmp_path / "scripts" / "pipeline"
        _write_pipeline_file(
            pipeline_dir, "lib/freshness_guard.py",
            "if stale_since is not None:\n    pass\n",
        )
        assert guard.find_violations(pipeline_dir) == {}

    def test_scan_stale_py_is_exempt(self, tmp_path):
        guard.configure(repo_root=tmp_path)
        pipeline_dir = tmp_path / "scripts" / "pipeline"
        _write_pipeline_file(
            pipeline_dir, "commands/knowledge/scan_stale.py",
            "if stale_since is not None and str(stale_since).strip():\n    pass\n",
        )
        assert guard.find_violations(pipeline_dir) == {}

    def test_test_files_are_exempt(self, tmp_path):
        guard.configure(repo_root=tmp_path)
        pipeline_dir = tmp_path / "scripts" / "pipeline"
        _write_pipeline_file(
            pipeline_dir, "tests/test_something.py",
            "assert 'stale_since is not None' in source_text\n",
        )
        assert guard.find_violations(pipeline_dir) == {}

    def test_clean_file_no_violations(self, tmp_path):
        guard.configure(repo_root=tmp_path)
        pipeline_dir = tmp_path / "scripts" / "pipeline"
        _write_pipeline_file(
            pipeline_dir, "commands/launch/site_planner.py",
            "allowed, result = is_generation_allowed(family, platform, mode='degraded')\n"
            "if not allowed:\n    sys.exit(1)\n",
        )
        assert guard.find_violations(pipeline_dir) == {}

    def test_this_repos_real_pipeline_tree_is_clean(self):
        """The real regression proof: as of the H3 fix, the actual
        scripts/pipeline/ tree has zero occurrences of the raw gating
        pattern outside the two allowed files (confirmed live: site_planner.py
        was the only offender, now migrated)."""
        assert guard.find_violations() == {}


class TestMain:
    def test_main_exits_0_when_clean(self, capsys):
        exit_code = guard.main([])
        assert exit_code == 0
        assert "OK:" in capsys.readouterr().out

    def test_main_exits_1_when_violation_found(self, tmp_path, capsys):
        guard.configure(repo_root=tmp_path)
        pipeline_dir = tmp_path / "scripts" / "pipeline"
        _write_pipeline_file(
            pipeline_dir, "commands/launch/example_gate.py",
            "if kn.stale_since is not None:\n    sys.exit(1)\n",
        )
        exit_code = guard.main([])
        assert exit_code == 1
        out = capsys.readouterr().out
        assert "BROKEN" in out
        assert "example_gate.py:1" in out
