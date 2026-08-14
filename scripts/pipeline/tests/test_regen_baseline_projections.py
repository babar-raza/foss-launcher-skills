"""Tests for commands/ops/regen_baseline_projections.py."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_PIPELINE_DIR = Path(__file__).resolve().parents[1]
if str(_PIPELINE_DIR) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_DIR))

from commands.ops import regen_baseline_projections as rbp


@pytest.fixture(autouse=True)
def _configure(tmp_path):
    rbp.configure(repo_root=tmp_path)
    yield
    rbp.configure(repo_root=None)


def _write_model(tmp_path: Path, family: str, platform: str, repo_sha: str, promoted_at: str = "2026-08-14T00:00:00+00:00") -> None:
    merged = tmp_path / "knowledge" / family / platform / "merged"
    merged.mkdir(parents=True, exist_ok=True)
    (merged / "model.yaml").write_text(
        f"family: {family}\nplatform: {platform}\nrepo_sha: {repo_sha}\npromoted_at: '{promoted_at}'\n",
        encoding="utf-8",
    )


class TestRebuildOne:
    def test_writes_both_projections(self, tmp_path):
        model = {"repo_sha": "abc123", "promoted_at": "2026-08-14T00:00:00+00:00"}
        ok = rbp.rebuild_one("cells", "net", model, run_id="test-run")
        assert ok is True

        baselines = json.loads((tmp_path / "data" / "upstream_baselines.json").read_text(encoding="utf-8"))
        assert baselines["cells/net"] == "abc123"

        state = json.loads((tmp_path / "data" / "knowledge_state.json").read_text(encoding="utf-8"))
        assert state["cells/net"]["accepted_baseline"]["repo_sha"] == "abc123"
        assert state["cells/net"]["accepted_baseline"]["sha_source"] == "model.yaml"

    def test_missing_repo_sha_is_a_noop(self, tmp_path):
        ok = rbp.rebuild_one("cells", "net", {})
        assert ok is False
        assert not (tmp_path / "data" / "upstream_baselines.json").exists()

    def test_preserves_other_state_sections(self, tmp_path):
        # a prior truth_audit record for this product must survive a baseline rebuild
        from lib.knowledge_state import record_truth_audit
        record_truth_audit("cells", "net", fail_count=0, warn_count=2,
                            report_path="reports/audit/cells-net.md", recorded_at="2026-08-01T00:00:00Z")
        rbp.rebuild_one("cells", "net", {"repo_sha": "xyz789"})
        state = json.loads((tmp_path / "data" / "knowledge_state.json").read_text(encoding="utf-8"))
        assert state["cells/net"]["truth_audit"]["fail_count"] == 0
        assert state["cells/net"]["accepted_baseline"]["repo_sha"] == "xyz789"


class TestRebuildAll:
    def test_rebuilds_every_tracked_product(self, tmp_path):
        _write_model(tmp_path, "cells", "net", "sha-net")
        _write_model(tmp_path, "cells", "go", "sha-go")
        result = rbp.rebuild_all()
        assert set(result["rebuilt"]) == {"cells/net", "cells/go"}
        assert result["errors"] == []

        baselines = json.loads((tmp_path / "data" / "upstream_baselines.json").read_text(encoding="utf-8"))
        assert baselines == {"cells/net": "sha-net", "cells/go": "sha-go"}

    def test_skips_products_with_no_repo_sha(self, tmp_path):
        merged = tmp_path / "knowledge" / "cells" / "broken" / "merged"
        merged.mkdir(parents=True)
        (merged / "model.yaml").write_text("family: cells\nplatform: broken\n", encoding="utf-8")
        result = rbp.rebuild_all()
        assert result["skipped"] == ["cells/broken"]
        assert result["rebuilt"] == []

    def test_ignores_underscore_prefixed_top_level_dirs(self, tmp_path):
        # knowledge/_vectors/, knowledge/_overrides/ must never be walked as products
        (tmp_path / "knowledge" / "_vectors" / "cells" / "merged").mkdir(parents=True)
        (tmp_path / "knowledge" / "_vectors" / "cells" / "merged" / "model.yaml").write_text(
            "repo_sha: should-not-be-picked-up\n", encoding="utf-8")
        _write_model(tmp_path, "cells", "net", "sha-net")
        result = rbp.rebuild_all()
        assert result["rebuilt"] == ["cells/net"]

    def test_no_knowledge_dir_is_a_clean_empty_result(self, tmp_path):
        result = rbp.rebuild_all()
        assert result == {"rebuilt": [], "skipped": [], "errors": []}


class TestCheckStaleness:
    def test_no_mismatches_after_rebuild(self, tmp_path):
        _write_model(tmp_path, "cells", "net", "sha-net")
        rbp.rebuild_all()
        assert rbp.check_staleness() == []

    def test_detects_projection_behind_source(self, tmp_path):
        _write_model(tmp_path, "cells", "net", "old-sha")
        rbp.rebuild_all()
        # source model.yaml advances (e.g. a real refresh happened) but nobody
        # re-ran rebuild_all/rebuild_one yet
        _write_model(tmp_path, "cells", "net", "new-sha")
        mismatches = rbp.check_staleness()
        assert len(mismatches) == 1
        assert mismatches[0] == {
            "family": "cells", "platform": "net",
            "projection_sha": "old-sha", "source_sha": "new-sha",
        }

    def test_missing_projection_entry_is_a_mismatch(self, tmp_path):
        _write_model(tmp_path, "cells", "net", "sha-net")
        # projections file never written
        mismatches = rbp.check_staleness()
        assert mismatches == [{
            "family": "cells", "platform": "net",
            "projection_sha": None, "source_sha": "sha-net",
        }]


class TestCLI:
    def test_check_staleness_exit_code(self, tmp_path):
        _write_model(tmp_path, "cells", "net", "sha-net")
        assert rbp.main(["check-staleness"]) == 1  # projection not built yet
        rbp.rebuild_all()
        assert rbp.main(["check-staleness"]) == 0

    def test_rebuild_all_exit_code(self, tmp_path):
        _write_model(tmp_path, "cells", "net", "sha-net")
        assert rbp.main(["rebuild-all"]) == 0
