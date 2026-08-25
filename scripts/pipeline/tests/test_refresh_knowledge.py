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
# Path isolation (autouse)
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _isolate_paths(tmp_path):
    _rk.configure(repo_root=tmp_path)
    yield
    _rk.configure()


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
             patch.object(_rk, "_run_completeness_check"):
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
             patch.object(_rk, "_run", side_effect=fail_scout):
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
             patch.object(_rk, "_run_completeness_check"):
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

        _rk._set_stale_since("test", "net")

        # Delta should still exist (not renamed) because stale_since was already set
        assert delta_json.exists()
        prev_json = merged / "knowledge_delta.prev.json"
        assert not prev_json.exists()

    def test_second_cycle_rotation_overwrites_existing_prev(self, tmp_path):
        """G13 (mission-plan-the-end-to-end-vast-hejlsberg.md Task 20): a second
        (or later) stale-detection cycle must correctly rotate the CURRENT
        knowledge_delta.json over an already-existing .prev.json from an
        earlier cycle, not raise or silently leave .prev.json frozen at its
        old content. Path.rename() raises FileExistsError on Windows in
        exactly this situation -- the real, confirmed bug this test guards
        against; Path.replace() (the fix) is an atomic, cross-platform
        overwrite."""
        merged = tmp_path / "knowledge" / "test" / "net" / "merged"
        merged.mkdir(parents=True)
        model_yaml = merged / "model.yaml"
        delta_json = merged / "knowledge_delta.json"
        prev_json = merged / "knowledge_delta.prev.json"

        # Simulate: a first stale-detection cycle already rotated an older
        # delta into .prev.json (still present, stale_since still set from
        # that first cycle) -- then a fresh refresh cleared stale_since and
        # wrote a NEW knowledge_delta.json, and staleness was freshly
        # re-detected a second time (stale_since reset to null in between,
        # as _clear_stale_since + a new refresh cycle would do).
        prev_json.write_text('{"removed_apis": ["OldClassFromCycle1"]}', encoding="utf-8")
        delta_json.write_text('{"removed_apis": ["NewClassFromCycle2"]}', encoding="utf-8")
        model_yaml.write_text("stale_since: null\nrepo_sha: def456\n", encoding="utf-8")

        _rk._set_stale_since("test", "net")

        assert not delta_json.exists(), "current-cycle delta should have been rotated"
        assert prev_json.exists()
        # The stale (cycle-1) content must be replaced by the current (cycle-2)
        # content, not left frozen at whatever the first cycle wrote.
        assert "NewClassFromCycle2" in prev_json.read_text(encoding="utf-8")
        assert "OldClassFromCycle1" not in prev_json.read_text(encoding="utf-8")


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


# ---------------------------------------------------------------------------
# Task 15 (§9.10, closes G9): deprecated_apis delta classification
# ---------------------------------------------------------------------------

class TestDeprecatedApisDelta:
    def test_class_newly_deprecated_is_reported(self, tmp_path):
        import json

        merged = tmp_path / "merged"
        merged.mkdir()
        bak = tmp_path / "bak"
        bak.mkdir()

        (bak / "api_surface.json").write_text(json.dumps([
            {"name": "ClassA", "methods": [], "properties": []},
        ]), encoding="utf-8")
        (bak / "claims.json").write_text("[]", encoding="utf-8")
        (merged / "api_surface.json").write_text(json.dumps([
            {"name": "ClassA", "methods": [], "properties": [], "deprecated": True},
        ]), encoding="utf-8")
        (merged / "claims.json").write_text("[]", encoding="utf-8")

        _rk._write_knowledge_delta("test", "net", bak, merged, "sha_new", "sha_old")

        delta = json.loads((merged / "knowledge_delta.json").read_text(encoding="utf-8"))
        assert delta["deprecated_apis"] == ["ClassA"]

    def test_method_newly_deprecated_reports_owning_class(self, tmp_path):
        import json

        merged = tmp_path / "merged"
        merged.mkdir()
        bak = tmp_path / "bak"
        bak.mkdir()

        (bak / "api_surface.json").write_text(json.dumps([
            {"name": "ClassA", "methods": [{"name": "oldMethod", "deprecated": False}], "properties": []},
        ]), encoding="utf-8")
        (bak / "claims.json").write_text("[]", encoding="utf-8")
        (merged / "api_surface.json").write_text(json.dumps([
            {"name": "ClassA", "methods": [{"name": "oldMethod", "deprecated": True}], "properties": []},
        ]), encoding="utf-8")
        (merged / "claims.json").write_text("[]", encoding="utf-8")

        _rk._write_knowledge_delta("test", "net", bak, merged, "sha_new", "sha_old")

        delta = json.loads((merged / "knowledge_delta.json").read_text(encoding="utf-8"))
        assert delta["deprecated_apis"] == ["ClassA"]

    def test_already_deprecated_member_not_re_reported(self, tmp_path):
        """A member deprecated in BOTH old and new snapshots is not a new
        transition -- must not appear every cycle."""
        import json

        merged = tmp_path / "merged"
        merged.mkdir()
        bak = tmp_path / "bak"
        bak.mkdir()

        (bak / "api_surface.json").write_text(json.dumps([
            {"name": "ClassA", "methods": [{"name": "oldMethod", "deprecated": True}], "properties": []},
        ]), encoding="utf-8")
        (bak / "claims.json").write_text("[]", encoding="utf-8")
        (merged / "api_surface.json").write_text(json.dumps([
            {"name": "ClassA", "methods": [{"name": "oldMethod", "deprecated": True}], "properties": []},
        ]), encoding="utf-8")
        (merged / "claims.json").write_text("[]", encoding="utf-8")

        _rk._write_knowledge_delta("test", "net", bak, merged, "sha_new", "sha_old")

        delta = json.loads((merged / "knowledge_delta.json").read_text(encoding="utf-8"))
        assert delta["deprecated_apis"] == []

    def test_property_newly_deprecated_reports_owning_class(self, tmp_path):
        import json

        merged = tmp_path / "merged"
        merged.mkdir()
        bak = tmp_path / "bak"
        bak.mkdir()

        (bak / "api_surface.json").write_text(json.dumps([
            {"name": "ClassA", "methods": [], "properties": [{"name": "X", "deprecated": False}]},
        ]), encoding="utf-8")
        (bak / "claims.json").write_text("[]", encoding="utf-8")
        (merged / "api_surface.json").write_text(json.dumps([
            {"name": "ClassA", "methods": [], "properties": [{"name": "X", "deprecated": True}]},
        ]), encoding="utf-8")
        (merged / "claims.json").write_text("[]", encoding="utf-8")

        _rk._write_knowledge_delta("test", "net", bak, merged, "sha_new", "sha_old")

        delta = json.loads((merged / "knowledge_delta.json").read_text(encoding="utf-8"))
        assert delta["deprecated_apis"] == ["ClassA"]

    def test_no_deprecation_signal_yields_empty_list(self, tmp_path):
        import json

        merged = tmp_path / "merged"
        merged.mkdir()
        bak = tmp_path / "bak"
        bak.mkdir()

        (bak / "api_surface.json").write_text(json.dumps([
            {"name": "ClassA", "methods": [{"name": "m"}], "properties": []},
        ]), encoding="utf-8")
        (bak / "claims.json").write_text("[]", encoding="utf-8")
        (merged / "api_surface.json").write_text(json.dumps([
            {"name": "ClassA", "methods": [{"name": "m"}], "properties": []},
        ]), encoding="utf-8")
        (merged / "claims.json").write_text("[]", encoding="utf-8")

        _rk._write_knowledge_delta("test", "net", bak, merged, "sha_new", "sha_old")

        delta = json.loads((merged / "knowledge_delta.json").read_text(encoding="utf-8"))
        assert delta["deprecated_apis"] == []

    def test_pre_task15_knowledge_missing_field_defaults_safely(self, tmp_path):
        """Old, pre-Task-15 knowledge models have no "deprecated" key at all
        anywhere -- must not crash and must not fabricate a deprecation."""
        import json

        merged = tmp_path / "merged"
        merged.mkdir()
        bak = tmp_path / "bak"
        bak.mkdir()

        (bak / "api_surface.json").write_text(json.dumps([
            {"name": "ClassA", "methods": [{"name": "m"}], "properties": []},
        ]), encoding="utf-8")
        (bak / "claims.json").write_text("[]", encoding="utf-8")
        (merged / "api_surface.json").write_text(json.dumps([
            {"name": "ClassA", "methods": [{"name": "m"}, {"name": "n"}], "properties": []},
        ]), encoding="utf-8")
        (merged / "claims.json").write_text("[]", encoding="utf-8")

        _rk._write_knowledge_delta("test", "net", bak, merged, "sha_new", "sha_old")

        delta = json.loads((merged / "knowledge_delta.json").read_text(encoding="utf-8"))
        assert delta["deprecated_apis"] == []
        assert delta["modified_apis"] == ["ClassA"]  # method name-set change still caught normally


# ---------------------------------------------------------------------------
# Task 17 (§9.12, closes the other half of G10): claim_text_changes and
# api_signature_changes -- additive fields alongside the existing plain-
# string-list delta fields, carrying real text/signature data instead of
# just opaque IDs.
# ---------------------------------------------------------------------------

class TestClaimTextChangesDelta:
    def test_modified_claim_carries_old_and_new_text(self, tmp_path):
        import json
        merged = tmp_path / "merged"
        merged.mkdir()
        bak = tmp_path / "bak"
        bak.mkdir()

        (bak / "api_surface.json").write_text("[]", encoding="utf-8")
        (bak / "claims.json").write_text(json.dumps([
            {"claim_id": "CLM-1", "text": "old wording of the same fact."},
        ]), encoding="utf-8")
        (merged / "api_surface.json").write_text("[]", encoding="utf-8")
        (merged / "claims.json").write_text(json.dumps([
            {"claim_id": "CLM-1", "text": "new wording of the same fact."},
        ]), encoding="utf-8")

        _rk._write_knowledge_delta("test", "net", bak, merged, "sha_new", "sha_old")
        delta = json.loads((merged / "knowledge_delta.json").read_text(encoding="utf-8"))

        assert delta["modified_claims"] == ["CLM-1"]  # existing field unchanged in shape
        assert delta["claim_text_changes"]["CLM-1"] == {
            "old_text": "old wording of the same fact.",
            "new_text": "new wording of the same fact.",
        }

    def test_new_claim_has_old_text_none(self, tmp_path):
        import json
        merged = tmp_path / "merged"
        merged.mkdir()
        bak = tmp_path / "bak"
        bak.mkdir()
        (bak / "api_surface.json").write_text("[]", encoding="utf-8")
        (bak / "claims.json").write_text("[]", encoding="utf-8")
        (merged / "api_surface.json").write_text("[]", encoding="utf-8")
        (merged / "claims.json").write_text(json.dumps([
            {"claim_id": "CLM-new", "text": "a brand new fact."},
        ]), encoding="utf-8")

        _rk._write_knowledge_delta("test", "net", bak, merged, "sha_new", "sha_old")
        delta = json.loads((merged / "knowledge_delta.json").read_text(encoding="utf-8"))

        assert delta["claim_text_changes"]["CLM-new"] == {
            "old_text": None, "new_text": "a brand new fact.",
        }

    def test_removed_claim_has_new_text_none(self, tmp_path):
        import json
        merged = tmp_path / "merged"
        merged.mkdir()
        bak = tmp_path / "bak"
        bak.mkdir()
        (bak / "api_surface.json").write_text("[]", encoding="utf-8")
        (bak / "claims.json").write_text(json.dumps([
            {"claim_id": "CLM-gone", "text": "a fact that is now gone."},
        ]), encoding="utf-8")
        (merged / "api_surface.json").write_text("[]", encoding="utf-8")
        (merged / "claims.json").write_text("[]", encoding="utf-8")

        _rk._write_knowledge_delta("test", "net", bak, merged, "sha_new", "sha_old")
        delta = json.loads((merged / "knowledge_delta.json").read_text(encoding="utf-8"))

        assert delta["claim_text_changes"]["CLM-gone"] == {
            "old_text": "a fact that is now gone.", "new_text": None,
        }

    def test_unchanged_claim_has_no_text_changes_entry(self, tmp_path):
        import json
        merged = tmp_path / "merged"
        merged.mkdir()
        bak = tmp_path / "bak"
        bak.mkdir()
        stable = json.dumps([{"claim_id": "CLM-stable", "text": "unchanged fact."}])
        (bak / "api_surface.json").write_text("[]", encoding="utf-8")
        (bak / "claims.json").write_text(stable, encoding="utf-8")
        (merged / "api_surface.json").write_text("[]", encoding="utf-8")
        (merged / "claims.json").write_text(stable, encoding="utf-8")

        _rk._write_knowledge_delta("test", "net", bak, merged, "sha_new", "sha_old")
        delta = json.loads((merged / "knowledge_delta.json").read_text(encoding="utf-8"))

        assert delta["claim_text_changes"] == {}


class TestReidentifiedClaimsReconciliation:
    """A claim-ID reassignment (e.g. Task 16's anchor-stable IDs) must not be
    misreported as a real removal+addition when the claim's TEXT is
    unchanged -- found live 2026-08-25 as the root cause of a catastrophic
    content-deletion bug: an unreconciled re-ID storm makes semantic_diff.py
    classify every "removed" claim as FEATURE_REMOVED, which body_impact.py
    maps to UT_REMOVAL (delete the section), even though nothing about the
    claim's real content changed."""

    def test_pure_reid_excluded_from_removed_and_new_claims(self, tmp_path):
        import json
        merged = tmp_path / "merged"
        merged.mkdir()
        bak = tmp_path / "bak"
        bak.mkdir()
        (bak / "api_surface.json").write_text("[]", encoding="utf-8")
        (bak / "claims.json").write_text(json.dumps([
            {"claim_id": "CLM-old-1", "text": "Widget.paint() renders the control."},
        ]), encoding="utf-8")
        (merged / "api_surface.json").write_text("[]", encoding="utf-8")
        (merged / "claims.json").write_text(json.dumps([
            {"claim_id": "CLM-new-1", "text": "Widget.paint() renders the control."},
        ]), encoding="utf-8")

        _rk._write_knowledge_delta("test", "net", bak, merged, "sha_new", "sha_old")
        delta = json.loads((merged / "knowledge_delta.json").read_text(encoding="utf-8"))

        assert delta["removed_claims"] == []
        assert delta["new_claims"] == []
        assert delta["reidentified_claims"] == {"CLM-old-1": "CLM-new-1"}
        # A reidentified claim is not a text change either -- it never reaches
        # claim_text_changes, so no downstream consumer can mistake it for one.
        assert "CLM-old-1" not in delta["claim_text_changes"]
        assert "CLM-new-1" not in delta["claim_text_changes"]

    def test_genuine_removal_with_no_text_match_still_reported(self, tmp_path):
        import json
        merged = tmp_path / "merged"
        merged.mkdir()
        bak = tmp_path / "bak"
        bak.mkdir()
        (bak / "api_surface.json").write_text("[]", encoding="utf-8")
        (bak / "claims.json").write_text(json.dumps([
            {"claim_id": "CLM-gone", "text": "This capability no longer exists anywhere."},
        ]), encoding="utf-8")
        (merged / "api_surface.json").write_text("[]", encoding="utf-8")
        (merged / "claims.json").write_text("[]", encoding="utf-8")

        _rk._write_knowledge_delta("test", "net", bak, merged, "sha_new", "sha_old")
        delta = json.loads((merged / "knowledge_delta.json").read_text(encoding="utf-8"))

        assert delta["removed_claims"] == ["CLM-gone"]
        assert delta["reidentified_claims"] == {}

    def test_genuine_addition_with_no_prior_text_still_reported(self, tmp_path):
        import json
        merged = tmp_path / "merged"
        merged.mkdir()
        bak = tmp_path / "bak"
        bak.mkdir()
        (bak / "api_surface.json").write_text("[]", encoding="utf-8")
        (bak / "claims.json").write_text("[]", encoding="utf-8")
        (merged / "api_surface.json").write_text("[]", encoding="utf-8")
        (merged / "claims.json").write_text(json.dumps([
            {"claim_id": "CLM-brand-new", "text": "A genuinely new capability."},
        ]), encoding="utf-8")

        _rk._write_knowledge_delta("test", "net", bak, merged, "sha_new", "sha_old")
        delta = json.loads((merged / "knowledge_delta.json").read_text(encoding="utf-8"))

        assert delta["new_claims"] == ["CLM-brand-new"]
        assert delta["reidentified_claims"] == {}

    def test_duplicate_identical_text_pairs_one_to_one(self, tmp_path):
        """Two old claims and two new claims share identical text (e.g. two
        overloads with boilerplate doc text) -- both must reconcile, not just
        one, and neither should spill into removed_claims/new_claims."""
        import json
        merged = tmp_path / "merged"
        merged.mkdir()
        bak = tmp_path / "bak"
        bak.mkdir()
        text = "Registers a handler for this event."
        (bak / "api_surface.json").write_text("[]", encoding="utf-8")
        (bak / "claims.json").write_text(json.dumps([
            {"claim_id": "CLM-old-a", "text": text},
            {"claim_id": "CLM-old-b", "text": text},
        ]), encoding="utf-8")
        (merged / "api_surface.json").write_text("[]", encoding="utf-8")
        (merged / "claims.json").write_text(json.dumps([
            {"claim_id": "CLM-new-a", "text": text},
            {"claim_id": "CLM-new-b", "text": text},
        ]), encoding="utf-8")

        _rk._write_knowledge_delta("test", "net", bak, merged, "sha_new", "sha_old")
        delta = json.loads((merged / "knowledge_delta.json").read_text(encoding="utf-8"))

        assert delta["removed_claims"] == []
        assert delta["new_claims"] == []
        assert set(delta["reidentified_claims"].keys()) == {"CLM-old-a", "CLM-old-b"}
        assert set(delta["reidentified_claims"].values()) == {"CLM-new-a", "CLM-new-b"}

    def test_partial_overlap_of_duplicate_text_reconciles_only_the_surplus_pairs(self, tmp_path):
        """3 old claims share identical text; only 2 remain (2 new claims,
        same text). 2 must reconcile as re-IDs; 1 is a genuine removal."""
        import json
        merged = tmp_path / "merged"
        merged.mkdir()
        bak = tmp_path / "bak"
        bak.mkdir()
        text = "Shared boilerplate description."
        (bak / "api_surface.json").write_text("[]", encoding="utf-8")
        (bak / "claims.json").write_text(json.dumps([
            {"claim_id": "CLM-old-a", "text": text},
            {"claim_id": "CLM-old-b", "text": text},
            {"claim_id": "CLM-old-c", "text": text},
        ]), encoding="utf-8")
        (merged / "api_surface.json").write_text("[]", encoding="utf-8")
        (merged / "claims.json").write_text(json.dumps([
            {"claim_id": "CLM-new-a", "text": text},
            {"claim_id": "CLM-new-b", "text": text},
        ]), encoding="utf-8")

        _rk._write_knowledge_delta("test", "net", bak, merged, "sha_new", "sha_old")
        delta = json.loads((merged / "knowledge_delta.json").read_text(encoding="utf-8"))

        assert len(delta["reidentified_claims"]) == 2
        assert len(delta["removed_claims"]) == 1
        assert delta["new_claims"] == []

    def test_reidentified_claim_still_counted_in_summary_log(self, tmp_path, capsys):
        import json
        merged = tmp_path / "merged"
        merged.mkdir()
        bak = tmp_path / "bak"
        bak.mkdir()
        (bak / "api_surface.json").write_text("[]", encoding="utf-8")
        (bak / "claims.json").write_text(json.dumps([
            {"claim_id": "CLM-old-1", "text": "Unchanged fact, new id only."},
        ]), encoding="utf-8")
        (merged / "api_surface.json").write_text("[]", encoding="utf-8")
        (merged / "claims.json").write_text(json.dumps([
            {"claim_id": "CLM-new-1", "text": "Unchanged fact, new id only."},
        ]), encoding="utf-8")

        _rk._write_knowledge_delta("test", "net", bak, merged, "sha_new", "sha_old")
        out = capsys.readouterr().out
        assert "reidentified" in out

    def test_empty_text_claims_never_falsely_reconcile(self, tmp_path):
        """Two different claims that both happen to have empty/missing text
        must never be treated as the same re-identified claim."""
        import json
        merged = tmp_path / "merged"
        merged.mkdir()
        bak = tmp_path / "bak"
        bak.mkdir()
        (bak / "api_surface.json").write_text("[]", encoding="utf-8")
        (bak / "claims.json").write_text(json.dumps([
            {"claim_id": "CLM-old-empty", "text": ""},
        ]), encoding="utf-8")
        (merged / "api_surface.json").write_text("[]", encoding="utf-8")
        (merged / "claims.json").write_text(json.dumps([
            {"claim_id": "CLM-new-empty", "text": ""},
        ]), encoding="utf-8")

        _rk._write_knowledge_delta("test", "net", bak, merged, "sha_new", "sha_old")
        delta = json.loads((merged / "knowledge_delta.json").read_text(encoding="utf-8"))

        assert delta["removed_claims"] == ["CLM-old-empty"]
        assert delta["new_claims"] == ["CLM-new-empty"]
        assert delta["reidentified_claims"] == {}


class TestApiSignatureChangesDelta:
    def test_modified_api_carries_added_and_removed_members(self, tmp_path):
        import json
        merged = tmp_path / "merged"
        merged.mkdir()
        bak = tmp_path / "bak"
        bak.mkdir()

        (bak / "api_surface.json").write_text(json.dumps([
            {"name": "ClassA",
             "methods": [{"name": "oldMethod"}],
             "properties": [{"name": "OldProp"}]},
        ]), encoding="utf-8")
        (bak / "claims.json").write_text("[]", encoding="utf-8")
        (merged / "api_surface.json").write_text(json.dumps([
            {"name": "ClassA",
             "methods": [{"name": "newMethod"}],
             "properties": [{"name": "OldProp"}, {"name": "NewProp"}]},
        ]), encoding="utf-8")
        (merged / "claims.json").write_text("[]", encoding="utf-8")

        _rk._write_knowledge_delta("test", "net", bak, merged, "sha_new", "sha_old")
        delta = json.loads((merged / "knowledge_delta.json").read_text(encoding="utf-8"))

        assert delta["modified_apis"] == ["ClassA"]  # existing field unchanged in shape
        assert delta["api_signature_changes"]["ClassA"] == {
            "added_methods": ["newMethod"],
            "removed_methods": ["oldMethod"],
            "added_properties": ["NewProp"],
            "removed_properties": [],
        }

    def test_erc_only_modified_class_has_no_signature_change_entry(self, tmp_path):
        """A class whose modified_apis membership comes only from ERC member-
        doc coverage changes (no real method/property name-set change) must
        not get a fabricated, empty signature_changes entry."""
        import json
        merged = tmp_path / "merged"
        merged.mkdir()
        bak = tmp_path / "bak"
        bak.mkdir()
        api_surface = json.dumps([
            {"name": "ClassB", "methods": [{"name": "m"}], "properties": []},
        ])
        (bak / "api_surface.json").write_text(api_surface, encoding="utf-8")
        (bak / "claims.json").write_text("[]", encoding="utf-8")
        (merged / "api_surface.json").write_text(api_surface, encoding="utf-8")
        (merged / "claims.json").write_text(json.dumps([
            {"claim_id": "ERC-test-net-1", "kind": "api", "text": "ClassB.m does something."},
        ]), encoding="utf-8")

        _rk._write_knowledge_delta("test", "net", bak, merged, "sha_new", "sha_old")
        delta = json.loads((merged / "knowledge_delta.json").read_text(encoding="utf-8"))

        assert delta["modified_apis"] == ["ClassB"]  # ERC-coverage-only membership
        assert delta["api_signature_changes"] == {}


# ---------------------------------------------------------------------------
# SR-04 (TC-4): _write_model_field round-trip
# ---------------------------------------------------------------------------

class TestWriteModelField:
    """TC-4: _write_model_field atomically updates a single field in merged/model.yaml."""

    def test_writes_new_field_to_existing_model_yaml(self, tmp_path):
        """_write_model_field adds a new key and preserves existing keys."""
        import yaml
        merged = tmp_path / "family" / "net" / "merged"
        merged.mkdir(parents=True)
        model_path = merged / "model.yaml"
        model_path.write_text(
            yaml.safe_dump({"repo_sha": "abc123", "version": "1.0"}),
            encoding="utf-8",
        )
        _rk.configure(knowledge_root=tmp_path)
        _rk._write_model_field("family", "net", "enrichment_status", "full")
        data = yaml.safe_load(model_path.read_text(encoding="utf-8"))
        assert data["enrichment_status"] == "full"
        assert data["repo_sha"] == "abc123", "Existing fields must be preserved"

    def test_writes_scout_only_status(self, tmp_path):
        """enrichment_status='scout-only' is written and readable."""
        import yaml
        merged = tmp_path / "family" / "net" / "merged"
        merged.mkdir(parents=True)
        model_path = merged / "model.yaml"
        model_path.write_text(yaml.safe_dump({"repo_sha": "def456"}), encoding="utf-8")
        _rk.configure(knowledge_root=tmp_path)
        _rk._write_model_field("family", "net", "enrichment_status", "scout-only")
        data = yaml.safe_load(model_path.read_text(encoding="utf-8"))
        assert data["enrichment_status"] == "scout-only"

    def test_silent_when_model_yaml_absent(self, tmp_path):
        """_write_model_field must not raise when model.yaml doesn't exist."""
        _rk.configure(knowledge_root=tmp_path)
        _rk._write_model_field("no_family", "no_platform", "enrichment_status", "full")
        # No exception raised = pass

    def test_overwrites_existing_field(self, tmp_path):
        """A second _write_model_field call overwrites the previous value."""
        import yaml
        merged = tmp_path / "family" / "net" / "merged"
        merged.mkdir(parents=True)
        model_path = merged / "model.yaml"
        model_path.write_text(
            yaml.safe_dump({"enrichment_status": "scout-only"}), encoding="utf-8"
        )
        _rk.configure(knowledge_root=tmp_path)
        _rk._write_model_field("family", "net", "enrichment_status", "full")
        data = yaml.safe_load(model_path.read_text(encoding="utf-8"))
        assert data["enrichment_status"] == "full"


# ---------------------------------------------------------------------------
# TC-2: _set_stale_since failure propagates from refresh() (Phase 1 contract test)
# ---------------------------------------------------------------------------

class TestSetStaleSinceExceptionPropagation:
    """TC-2 contract: _set_stale_since failure must NOT be swallowed by refresh().

    When _set_stale_since raises, it means the pipeline cannot record that a
    destructive refresh is starting.  This is a hard failure — the exception
    must propagate out of refresh() so the CLI exits non-zero and the operator
    is notified.  This is distinct from _clear_stale_since (both call sites
    are wrapped in try/except with a WARN, per SR-01).
    """

    def test_set_stale_since_failure_propagates_from_refresh(self, tmp_path):
        """_set_stale_since raising must escape refresh() unhandled."""
        boom = RuntimeError("disk full — cannot write model.yaml")

        with _patch_clone_dir(tmp_path), _patch_head("new_sha"), _patch_model("old_sha"), \
             patch.object(_rk, "_set_stale_since", side_effect=boom):
            with pytest.raises(RuntimeError, match="disk full"):
                refresh("cells", "python")


# ---------------------------------------------------------------------------
# TC-DAG-001: Extractor hash detection
# ---------------------------------------------------------------------------

class TestExtractorHashDetection:
    """TC-DAG-001: Re-extraction is triggered when extractor source files change."""

    def test_compute_extractor_hash_returns_string(self):
        """_compute_extractor_hash returns a 16-char hex string."""
        h = _rk._compute_extractor_hash()
        assert isinstance(h, str)
        assert len(h) == 16
        # Must be hex
        int(h, 16)

    def test_compute_extractor_hash_is_deterministic(self):
        """Same extractor files produce same hash across calls."""
        h1 = _rk._compute_extractor_hash()
        h2 = _rk._compute_extractor_hash()
        assert h1 == h2

    def test_extractor_changed_triggers_refresh(self, tmp_path):
        """When repo SHA matches but extractor hash differs, refresh proceeds (not 'current')."""
        with _patch_clone_dir(tmp_path), _patch_head("same_sha"), _patch_model("same_sha"), \
             patch.object(_rk, "_update_clone", return_value=None), \
             patch.object(_rk, "_stored_extractor_hash", return_value="old_hash_12345678"), \
             patch.object(_rk, "_compute_extractor_hash", return_value="new_hash_87654321"), \
             patch.object(_rk, "_set_stale_since"), \
             patch.object(_rk, "_run", return_value=True), \
             patch.object(_rk, "_clear_stale_since"), \
             patch.object(_rk, "_save_extractor_hash"), \
             patch.object(_rk, "_run_completeness_check"):
            result = refresh("cells", "net")
            # Should NOT return "current" — extractor changed
            assert result != "current"

    def test_extractor_unchanged_returns_current(self, tmp_path):
        """When repo SHA matches AND extractor hash matches, return 'current'."""
        with _patch_clone_dir(tmp_path), _patch_head("same_sha"), _patch_model("same_sha"), \
             patch.object(_rk, "_update_clone", return_value=None), \
             patch.object(_rk, "_stored_extractor_hash", return_value="same_hash_12345"), \
             patch.object(_rk, "_compute_extractor_hash", return_value="same_hash_12345"), \
             patch.object(_rk, "_has_pending_delta", return_value=False), \
             patch.object(_rk, "_clear_stale_since"):
            result = refresh("cells", "net")
            assert result == "current"

    def test_no_stored_hash_returns_current(self, tmp_path):
        """When no extractor_hash in model.yaml (first run), skip check — return 'current'."""
        with _patch_clone_dir(tmp_path), _patch_head("same_sha"), _patch_model("same_sha"), \
             patch.object(_rk, "_update_clone", return_value=None), \
             patch.object(_rk, "_stored_extractor_hash", return_value=None), \
             patch.object(_rk, "_compute_extractor_hash", return_value="any_hash"), \
             patch.object(_rk, "_has_pending_delta", return_value=False), \
             patch.object(_rk, "_clear_stale_since"):
            result = refresh("cells", "net")
            assert result == "current"
