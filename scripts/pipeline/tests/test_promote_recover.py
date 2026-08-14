"""Tests for commands/ops/promote_recover.py — interrupted-swap state detection/recovery."""
from __future__ import annotations

import json
import sys
from pathlib import Path

_PIPELINE_DIR = Path(__file__).resolve().parents[1]
if str(_PIPELINE_DIR) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_DIR))

from commands.ops import promote_recover as pr


def _make_dir(path: Path, *, manifest_status: "str | None" = None) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    if manifest_status is not None:
        (path / "bundle_manifest.json").write_text(
            json.dumps({"status": manifest_status, "bundle_id": "b1"}), encoding="utf-8")
    return path


class TestDetectState:
    def test_cold_start_when_nothing_exists(self, tmp_path):
        info = pr.detect_state(tmp_path / "cells" / "net")
        assert info["state"] == "COLD_START"

    def test_healthy_when_only_merged_exists(self, tmp_path):
        product = tmp_path / "cells" / "net"
        _make_dir(product / "merged", manifest_status="COMPLETE")
        info = pr.detect_state(product)
        assert info["state"] == "HEALTHY"

    def test_state_a_merged_plus_staging_no_bak(self, tmp_path):
        product = tmp_path / "cells" / "net"
        _make_dir(product / "merged", manifest_status="COMPLETE")
        _make_dir(product / "merged.staging.abc123")
        info = pr.detect_state(product)
        assert info["state"] == "STATE_A"
        assert len(info["staging_dirs"]) == 1

    def test_state_b_bak_only_no_merged(self, tmp_path):
        product = tmp_path / "cells" / "net"
        _make_dir(product / "merged.atomic-bak", manifest_status="COMPLETE")
        info = pr.detect_state(product)
        assert info["state"] == "STATE_B"

    def test_state_c_merged_plus_bak_no_staging(self, tmp_path):
        product = tmp_path / "cells" / "net"
        _make_dir(product / "merged", manifest_status="COMPLETE")
        _make_dir(product / "merged.atomic-bak", manifest_status="COMPLETE")
        info = pr.detect_state(product)
        assert info["state"] == "STATE_C"

    def test_ambiguous_when_all_three_present(self, tmp_path):
        product = tmp_path / "cells" / "net"
        _make_dir(product / "merged", manifest_status="COMPLETE")
        _make_dir(product / "merged.atomic-bak", manifest_status="COMPLETE")
        _make_dir(product / "merged.staging.abc123")
        info = pr.detect_state(product)
        assert info["state"] == "AMBIGUOUS"


class TestRecover:
    def test_healthy_is_a_noop(self, tmp_path):
        product = tmp_path / "cells" / "net"
        merged = _make_dir(product / "merged", manifest_status="COMPLETE")
        result = pr.recover(product)
        assert result == {"state": "HEALTHY", "action_taken": "none", "ok": True}
        assert merged.is_dir()

    def test_cold_start_is_a_noop(self, tmp_path):
        product = tmp_path / "cells" / "net"
        result = pr.recover(product)
        assert result == {"state": "COLD_START", "action_taken": "none", "ok": True}

    def test_state_a_removes_stale_staging_leaves_merged_untouched(self, tmp_path):
        product = tmp_path / "cells" / "net"
        merged = _make_dir(product / "merged", manifest_status="COMPLETE")
        (merged / "model.yaml").write_text("repo_sha: real-old-value\n", encoding="utf-8")
        staging = _make_dir(product / "merged.staging.abc123")
        (staging / "partial_file.json").write_text("{}", encoding="utf-8")

        result = pr.recover(product)

        assert result["state"] == "STATE_A"
        assert result["ok"] is True
        assert not staging.exists()
        assert merged.is_dir()
        assert (merged / "model.yaml").read_text(encoding="utf-8") == "repo_sha: real-old-value\n"

    def test_state_b_restores_bak_to_merged(self, tmp_path):
        product = tmp_path / "cells" / "net"
        bak = _make_dir(product / "merged.atomic-bak", manifest_status="COMPLETE")
        (bak / "model.yaml").write_text("repo_sha: last-known-good\n", encoding="utf-8")

        result = pr.recover(product)

        assert result["state"] == "STATE_B"
        assert result["ok"] is True
        merged = product / "merged"
        assert merged.is_dir()
        assert not bak.exists()
        assert (merged / "model.yaml").read_text(encoding="utf-8") == "repo_sha: last-known-good\n"

    def test_state_b_also_cleans_up_stale_staging(self, tmp_path):
        product = tmp_path / "cells" / "net"
        _make_dir(product / "merged.atomic-bak", manifest_status="COMPLETE")
        staging = _make_dir(product / "merged.staging.xyz")

        result = pr.recover(product)

        assert result["ok"] is True
        assert not staging.exists()

    def test_state_c_deletes_bak_when_merged_manifest_complete(self, tmp_path):
        product = tmp_path / "cells" / "net"
        merged = _make_dir(product / "merged", manifest_status="COMPLETE")
        bak = _make_dir(product / "merged.atomic-bak", manifest_status="COMPLETE")

        result = pr.recover(product)

        assert result["state"] == "STATE_C"
        assert result["ok"] is True
        assert merged.is_dir()
        assert not bak.exists()

    def test_state_c_refuses_when_merged_manifest_incomplete(self, tmp_path):
        product = tmp_path / "cells" / "net"
        merged = _make_dir(product / "merged", manifest_status="IN_PROGRESS")
        bak = _make_dir(product / "merged.atomic-bak", manifest_status="COMPLETE")

        result = pr.recover(product)

        assert result["state"] == "STATE_C"
        assert result["ok"] is False
        # bak preserved -- refuses to delete evidence when it can't verify merged/ is good
        assert bak.exists()

    def test_state_c_refuses_when_merged_manifest_missing(self, tmp_path):
        product = tmp_path / "cells" / "net"
        merged = _make_dir(product / "merged")  # no bundle_manifest.json at all
        bak = _make_dir(product / "merged.atomic-bak", manifest_status="COMPLETE")

        result = pr.recover(product)

        assert result["ok"] is False
        assert bak.exists()

    def test_ambiguous_refuses_to_guess(self, tmp_path):
        product = tmp_path / "cells" / "net"
        _make_dir(product / "merged", manifest_status="COMPLETE")
        _make_dir(product / "merged.atomic-bak", manifest_status="COMPLETE")
        _make_dir(product / "merged.staging.abc")

        result = pr.recover(product)

        assert result["state"] == "AMBIGUOUS"
        assert result["ok"] is False
        # nothing touched
        assert (product / "merged").is_dir()
        assert (product / "merged.atomic-bak").is_dir()
        assert (product / "merged.staging.abc").is_dir()


class TestCLI:
    def test_dry_run_never_mutates(self, tmp_path, capsys):
        product_root = tmp_path / "knowledge"
        product = product_root / "cells" / "net"
        _make_dir(product / "merged.atomic-bak", manifest_status="COMPLETE")
        rc = pr.main(["cells", "net", "--knowledge-root", str(product_root), "--dry-run"])
        assert rc == 0
        assert (product / "merged.atomic-bak").is_dir()
        assert not (product / "merged").exists()

    def test_recovers_state_b_via_cli(self, tmp_path):
        product_root = tmp_path / "knowledge"
        product = product_root / "cells" / "net"
        _make_dir(product / "merged.atomic-bak", manifest_status="COMPLETE")
        rc = pr.main(["cells", "net", "--knowledge-root", str(product_root)])
        assert rc == 0
        assert (product / "merged").is_dir()
        assert not (product / "merged.atomic-bak").exists()

    def test_exit_code_1_when_recovery_refuses(self, tmp_path):
        product_root = tmp_path / "knowledge"
        product = product_root / "cells" / "net"
        _make_dir(product / "merged", manifest_status="IN_PROGRESS")
        _make_dir(product / "merged.atomic-bak", manifest_status="COMPLETE")
        rc = pr.main(["cells", "net", "--knowledge-root", str(product_root)])
        assert rc == 1
