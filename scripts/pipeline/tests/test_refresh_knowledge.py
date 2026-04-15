"""Tests for refresh_knowledge.py — subprocess sequencing and skip conditions.

Covers:
  - refresh() returns "no_clone" when clone cache is missing
  - refresh() returns "current" when model SHA matches HEAD
  - refresh() returns "stale" in check_only mode when SHA differs
  - refresh() calls scout → enrich → promote → index in correct order
  - refresh() with auto_clone=False does not attempt clone
  - refresh() auto-clears stale_since in model.yaml after successful refresh
  - refresh() does NOT clear stale_since when scout fails
"""
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import refresh_knowledge as _rk
from refresh_knowledge import refresh, _build_erc_member_set


# ---------------------------------------------------------------------------
# Helper stubs
# ---------------------------------------------------------------------------

def _patch_head(sha: str | None):
    """Return a context manager that patches _head_sha to return *sha*."""
    return patch.object(_rk, "_head_sha", return_value=sha)


def _patch_model(sha: str | None):
    """Return a context manager that patches _model_sha to return *sha*."""
    return patch.object(_rk, "_model_sha", return_value=sha)


def _patch_clone_dir(tmp_path: Path):
    """Return a context manager that patches _clone_dir to return a temp path."""
    return patch.object(_rk, "_clone_dir", return_value=tmp_path / "clone")


# ---------------------------------------------------------------------------
# no_clone path
# ---------------------------------------------------------------------------

class TestRefreshNoClone:
    def test_returns_no_clone_when_head_is_none(self, tmp_path):
        with _patch_clone_dir(tmp_path), _patch_head(None):
            result = refresh("cells", "python", auto_clone=False)
        assert result == "no_clone"

    def test_no_clone_with_auto_clone_false(self, tmp_path):
        """Even with HEAD=None, auto_clone=False prevents clone attempt."""
        with _patch_clone_dir(tmp_path), _patch_head(None), \
             patch.object(_rk, "_try_auto_clone") as mock_clone:
            result = refresh("cells", "python", auto_clone=False)
        mock_clone.assert_not_called()
        assert result == "no_clone"

    def test_auto_clone_attempted_when_head_none(self, tmp_path):
        """auto_clone=True (default) attempts clone when HEAD is missing."""
        with _patch_clone_dir(tmp_path), \
             patch.object(_rk, "_head_sha", side_effect=[None, None]), \
             patch.object(_rk, "_try_auto_clone", return_value=False) as mock_clone:
            result = refresh("cells", "python", auto_clone=True)
        mock_clone.assert_called_once()
        assert result == "no_clone"


# ---------------------------------------------------------------------------
# current path
# ---------------------------------------------------------------------------

class TestRefreshCurrent:
    def test_returns_current_when_sha_matches(self, tmp_path):
        sha = "abc123deadbeef"
        with _patch_clone_dir(tmp_path), _patch_head(sha), _patch_model(sha), \
             patch.object(_rk, "_update_clone", return_value=None):
            result = refresh("cells", "python")
        assert result == "current"

    def test_current_does_not_call_run(self, tmp_path):
        sha = "abc123deadbeef"
        with _patch_clone_dir(tmp_path), _patch_head(sha), _patch_model(sha), \
             patch.object(_rk, "_update_clone", return_value=None), \
             patch.object(_rk, "_run") as mock_run:
            refresh("cells", "python")
        mock_run.assert_not_called()


# ---------------------------------------------------------------------------
# check_only path (stale detection without running pipeline)
# ---------------------------------------------------------------------------

class TestRefreshCheckOnly:
    def test_returns_stale_when_sha_differs(self, tmp_path):
        with _patch_clone_dir(tmp_path), _patch_head("new_sha"), _patch_model("old_sha"):
            result = refresh("cells", "python", check_only=True)
        assert result == "stale"

    def test_check_only_does_not_call_run(self, tmp_path):
        with _patch_clone_dir(tmp_path), _patch_head("new_sha"), _patch_model("old_sha"), \
             patch.object(_rk, "_run") as mock_run:
            refresh("cells", "python", check_only=True)
        mock_run.assert_not_called()


# ---------------------------------------------------------------------------
# Full refresh — step sequencing
# ---------------------------------------------------------------------------

class TestRefreshSequencing:
    def test_scout_called_before_promote(self, tmp_path):
        """scout must run before promote; verify call ordering."""
        call_order: list[str] = []

        def fake_run(cmd: list[str], label: str) -> bool:
            call_order.append(label)
            return True

        with _patch_clone_dir(tmp_path), _patch_head("new"), _patch_model("old"), \
             patch.object(_rk, "_run", side_effect=fake_run):
            result = refresh("cells", "python")

        assert result == "refreshed"
        assert call_order.index("scout") < call_order.index("promote"), (
            "scout must be called before promote"
        )

    def test_enrich_called_after_scout(self, tmp_path):
        call_order: list[str] = []

        def fake_run(cmd: list[str], label: str) -> bool:
            call_order.append(label)
            return True

        with _patch_clone_dir(tmp_path), _patch_head("new"), _patch_model("old"), \
             patch.object(_rk, "_run", side_effect=fake_run):
            refresh("cells", "python")

        assert "enrich" in call_order
        assert call_order.index("scout") < call_order.index("enrich")

    def test_index_called_after_promote(self, tmp_path):
        call_order: list[str] = []

        def fake_run(cmd: list[str], label: str) -> bool:
            call_order.append(label)
            return True

        with _patch_clone_dir(tmp_path), _patch_head("new"), _patch_model("old"), \
             patch.object(_rk, "_run", side_effect=fake_run):
            refresh("cells", "python")

        assert "index" in call_order
        assert call_order.index("promote") < call_order.index("index")

    def test_returns_failed_when_scout_fails(self, tmp_path):
        def fake_run(cmd: list[str], label: str) -> bool:
            return False  # all steps fail

        with _patch_clone_dir(tmp_path), _patch_head("new"), _patch_model("old"), \
             patch.object(_rk, "_run", side_effect=fake_run):
            result = refresh("cells", "python")

        assert result == "failed"

    def test_returns_failed_when_promote_fails(self, tmp_path):
        def fake_run(cmd: list[str], label: str) -> bool:
            return label != "promote"

        with _patch_clone_dir(tmp_path), _patch_head("new"), _patch_model("old"), \
             patch.object(_rk, "_run", side_effect=fake_run):
            result = refresh("cells", "python")

        assert result == "failed"

    def test_enrich_failure_does_not_stop_pipeline(self, tmp_path):
        """enrich is best-effort: failure should not stop promote/index."""
        call_order: list[str] = []

        def fake_run(cmd: list[str], label: str) -> bool:
            call_order.append(label)
            return label != "enrich"  # enrich fails, rest succeed

        with _patch_clone_dir(tmp_path), _patch_head("new"), _patch_model("old"), \
             patch.object(_rk, "_run", side_effect=fake_run):
            result = refresh("cells", "python")

        assert result == "refreshed"
        assert "promote" in call_order
        assert "index" in call_order


# ---------------------------------------------------------------------------
# stale_since lifecycle (F-4 regression tests)
# ---------------------------------------------------------------------------

class TestStaleFlagLifecycle:
    """Verify refresh() auto-clears stale_since after a successful refresh.

    These tests were added in the Healing Sprint (S-AD-HOC-4) to prevent the
    recurrence of manual model.yaml edits after knowledge refreshes.
    """

    def _make_model_yaml(self, path: Path, stale_since: str | None = "2026-03-01") -> None:
        import yaml as _yaml
        data = {
            "family": "cells",
            "platform": "python",
            "repo_sha": "old_sha",
            "stale_since": stale_since,
            "last_refreshed": "2026-03-01",
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")

    def test_stale_flag_cleared_after_refresh(self, tmp_path):
        """After a successful refresh, stale_since must be null in merged/model.yaml."""
        import yaml as _yaml
        merged_dir = tmp_path / "knowledge" / "cells" / "python" / "merged"
        merged_dir.mkdir(parents=True)
        model_path = merged_dir / "model.yaml"
        self._make_model_yaml(model_path, stale_since="2026-03-01")

        with _patch_clone_dir(tmp_path), _patch_head("new_sha"), _patch_model("old_sha"), \
             patch.object(_rk, "_run", return_value=True), \
             patch.object(_rk, "_run_completeness_check"), \
             patch.object(_rk, "KNOWLEDGE_ROOT", tmp_path / "knowledge"):
            result = refresh("cells", "python")

        assert result == "refreshed"
        data = _yaml.safe_load(model_path.read_text(encoding="utf-8"))
        assert data["stale_since"] is None, (
            "stale_since must be cleared automatically after a successful refresh"
        )

    def test_stale_flag_not_cleared_on_scout_failure(self, tmp_path):
        """When scout fails, stale_since must remain unchanged."""
        import yaml as _yaml
        merged_dir = tmp_path / "knowledge" / "cells" / "python" / "merged"
        merged_dir.mkdir(parents=True)
        model_path = merged_dir / "model.yaml"
        self._make_model_yaml(model_path, stale_since="2026-03-01")

        def fail_scout(cmd: list[str], label: str) -> bool:
            return False  # scout fails → refresh returns "failed" immediately

        with _patch_clone_dir(tmp_path), _patch_head("new_sha"), _patch_model("old_sha"), \
             patch.object(_rk, "_run", side_effect=fail_scout), \
             patch.object(_rk, "KNOWLEDGE_ROOT", tmp_path / "knowledge"):
            result = refresh("cells", "python")

        assert result == "failed"
        data = _yaml.safe_load(model_path.read_text(encoding="utf-8"))
        assert data["stale_since"] == "2026-03-01", (
            "stale_since must not be cleared when the refresh pipeline fails"
        )

    def test_stale_already_null_no_side_effect(self, tmp_path):
        """If stale_since is already null, refresh succeeds without error."""
        import yaml as _yaml
        merged_dir = tmp_path / "knowledge" / "cells" / "python" / "merged"
        merged_dir.mkdir(parents=True)
        model_path = merged_dir / "model.yaml"
        self._make_model_yaml(model_path, stale_since=None)

        with _patch_clone_dir(tmp_path), _patch_head("new_sha"), _patch_model("old_sha"), \
             patch.object(_rk, "_run", return_value=True), \
             patch.object(_rk, "_run_completeness_check"), \
             patch.object(_rk, "KNOWLEDGE_ROOT", tmp_path / "knowledge"):
            result = refresh("cells", "python")

        assert result == "refreshed"
        data = _yaml.safe_load(model_path.read_text(encoding="utf-8"))
        assert data["stale_since"] is None


# ---------------------------------------------------------------------------
# _build_erc_member_set — FIX-2 helper for ERC delta tracking
# ---------------------------------------------------------------------------

class TestBuildErcMemberSet:
    def _make_claim(self, text: str, kind: str = "api", claim_id: str = "ERC-cells-net-abc") -> dict:
        return {"claim_id": claim_id, "text": text, "kind": kind, "confidence": 0.8}

    def test_extracts_classname_membername(self):
        claims = [self._make_claim("Workbook.Save writes the workbook to disk.")]
        result = _build_erc_member_set(claims)
        assert "Workbook.Save" in result

    def test_backtick_prefix_stripped(self):
        claims = [self._make_claim("`Workbook.Load` reads a workbook from file.")]
        result = _build_erc_member_set(claims)
        assert "Workbook.Load" in result

    def test_non_api_kind_excluded(self):
        claims = [self._make_claim("Workbook.Save writes the workbook.", kind="feature")]
        result = _build_erc_member_set(claims)
        assert len(result) == 0

    def test_non_erc_claim_id_excluded(self):
        claims = [{"claim_id": "SC-001", "text": "Workbook.Save does X.", "kind": "api"}]
        result = _build_erc_member_set(claims)
        assert len(result) == 0

    def test_text_not_starting_classname_membername_excluded(self):
        claims = [self._make_claim("The workbook supports saving to multiple formats.")]
        result = _build_erc_member_set(claims)
        assert len(result) == 0

    def test_multiple_classes_extracted(self):
        claims = [
            self._make_claim("Workbook.Save writes to disk.", claim_id="ERC-cells-net-001"),
            self._make_claim("Cell.PutValue sets the value.", claim_id="ERC-cells-net-002"),
            self._make_claim("Style.ForegroundColor controls color.", claim_id="ERC-cells-net-003"),
        ]
        result = _build_erc_member_set(claims)
        assert "Workbook.Save" in result
        assert "Cell.PutValue" in result
        assert "Style.ForegroundColor" in result

    def test_empty_claims_returns_empty_set(self):
        assert _build_erc_member_set([]) == set()

    def test_symmetric_difference_detects_new_members(self):
        """Demonstrates FIX-2 intent: new ERC claims → classes appear in modified_apis."""
        old_claims = [self._make_claim("Workbook.Save writes to disk.", claim_id="ERC-cells-net-001")]
        new_claims = [
            self._make_claim("Workbook.Save writes to disk.", claim_id="ERC-cells-net-001"),
            self._make_claim("Cell.PutValue sets cell value.", claim_id="ERC-cells-net-002"),
        ]
        old_set = _build_erc_member_set(old_claims)
        new_set = _build_erc_member_set(new_claims)
        changed_classes = sorted({key.split(".")[0] for key in (new_set ^ old_set)})
        assert changed_classes == ["Cell"], (
            "Only Cell was added — Workbook unchanged — symmetric diff should contain Cell.PutValue only"
        )

    def test_no_change_produces_empty_symmetric_diff(self):
        """When old and new ERC claims are identical, no classes in modified_apis."""
        claims = [self._make_claim("Workbook.Save writes to disk.")]
        old_set = _build_erc_member_set(claims)
        new_set = _build_erc_member_set(claims)
        assert old_set ^ new_set == set()


# ---------------------------------------------------------------------------
# Fix A: Delta invalidation on re-staleness (healing sprint 2026-04-15)
# ---------------------------------------------------------------------------

class TestSetStaleSinceRenamesDelta:
    """Fix A: _set_stale_since renames existing knowledge_delta.json to .prev.json."""

    def test_renames_delta_to_prev(self, tmp_path):
        """When stale_since is None and delta exists, delta is renamed."""
        merged = tmp_path / "knowledge" / "test" / "net" / "merged"
        merged.mkdir(parents=True)
        model_yaml = merged / "model.yaml"
        delta_json = merged / "knowledge_delta.json"
        prev_json = merged / "knowledge_delta.prev.json"

        model_yaml.write_text("stale_since: null\nrepo_sha: abc123\n", encoding="utf-8")
        delta_json.write_text('{"modified_apis": []}', encoding="utf-8")

        with patch.object(_rk, "KNOWLEDGE_ROOT", tmp_path / "knowledge"):
            _rk._set_stale_since("test", "net")

        assert not delta_json.exists(), "delta.json should have been renamed"
        assert prev_json.exists(), "delta.prev.json should exist"
        assert prev_json.read_text(encoding="utf-8") == '{"modified_apis": []}'

    def test_no_rename_when_delta_absent(self, tmp_path):
        """When no delta.json exists, no error and no .prev.json created."""
        merged = tmp_path / "knowledge" / "test" / "net" / "merged"
        merged.mkdir(parents=True)
        model_yaml = merged / "model.yaml"
        model_yaml.write_text("stale_since: null\nrepo_sha: abc123\n", encoding="utf-8")

        with patch.object(_rk, "KNOWLEDGE_ROOT", tmp_path / "knowledge"):
            _rk._set_stale_since("test", "net")

        prev_json = merged / "knowledge_delta.prev.json"
        assert not prev_json.exists()

    def test_no_rename_when_already_stale(self, tmp_path):
        """When stale_since is already set, neither model nor delta is modified."""
        merged = tmp_path / "knowledge" / "test" / "net" / "merged"
        merged.mkdir(parents=True)
        model_yaml = merged / "model.yaml"
        delta_json = merged / "knowledge_delta.json"

        model_yaml.write_text("stale_since: '2026-04-15'\nrepo_sha: abc123\n", encoding="utf-8")
        delta_json.write_text('{"modified_apis": []}', encoding="utf-8")

        with patch.object(_rk, "KNOWLEDGE_ROOT", tmp_path / "knowledge"):
            _rk._set_stale_since("test", "net")

        # Delta should still exist (not renamed) because stale_since was already set
        assert delta_json.exists()
        prev_json = merged / "knowledge_delta.prev.json"
        assert not prev_json.exists()


# ---------------------------------------------------------------------------
# Fix B: Resurrection detection in delta writer (healing sprint 2026-04-15)
# ---------------------------------------------------------------------------

class TestResurrectionDetection:
    """Fix B: _write_knowledge_delta detects resurrected APIs from prev.json."""

    def test_detects_resurrected_apis(self, tmp_path):
        """APIs in new_apis that appear in prev.json removed_apis are resurrected."""
        import json

        merged = tmp_path / "merged"
        merged.mkdir()
        bak = tmp_path / "bak"
        bak.mkdir()

        # Write prev delta showing ClassA and ClassB were removed
        prev_json = merged / "knowledge_delta.prev.json"
        prev_json.write_text(json.dumps({
            "removed_apis": ["ClassA", "ClassB", "ClassC"],
        }), encoding="utf-8")

        # Bak has old api_surface without ClassA/ClassB
        (bak / "api_surface.json").write_text("[]", encoding="utf-8")
        (bak / "claims.json").write_text("[]", encoding="utf-8")

        # New merged has ClassA and ClassB back (plus ClassD which is new)
        (merged / "api_surface.json").write_text(json.dumps([
            {"name": "ClassA", "methods": [], "properties": []},
            {"name": "ClassB", "methods": [], "properties": []},
            {"name": "ClassD", "methods": [], "properties": []},
        ]), encoding="utf-8")
        (merged / "claims.json").write_text("[]", encoding="utf-8")

        _rk._write_knowledge_delta("test", "net", bak, merged, "sha_new", "sha_old")

        delta = json.loads((merged / "knowledge_delta.json").read_text(encoding="utf-8"))
        assert "resurrected_apis" in delta
        assert sorted(delta["resurrected_apis"]) == ["ClassA", "ClassB"]
        # ClassC was removed in prev but NOT re-added → not resurrected
        assert "ClassC" not in delta["resurrected_apis"]
        # ClassD is new but was not in prev removed_apis → not resurrected
        assert "ClassD" not in delta["resurrected_apis"]

    def test_no_prev_delta_produces_empty_resurrected(self, tmp_path):
        """Without prev.json, resurrected_apis is an empty list."""
        import json

        merged = tmp_path / "merged"
        merged.mkdir()
        bak = tmp_path / "bak"
        bak.mkdir()

        (bak / "api_surface.json").write_text("[]", encoding="utf-8")
        (bak / "claims.json").write_text("[]", encoding="utf-8")
        (merged / "api_surface.json").write_text(json.dumps([
            {"name": "ClassA", "methods": [], "properties": []},
        ]), encoding="utf-8")
        (merged / "claims.json").write_text("[]", encoding="utf-8")

        _rk._write_knowledge_delta("test", "net", bak, merged, "sha_new", "sha_old")

        delta = json.loads((merged / "knowledge_delta.json").read_text(encoding="utf-8"))
        assert delta.get("resurrected_apis") == []
