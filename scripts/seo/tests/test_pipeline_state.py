"""Tests for scripts/seo/pipeline/pipeline_state.py (SEO-STATE-MANIFEST).

No production caller exists yet -- each dependent card
(SEO-RECOMMENDATION-MEMORY, SEO-HEALTH-SUMMARY, SEO-METADATA-OBSERVATION-LOOP)
wires its own record_stage_write() call as it is built, per the plan's own
stated integration order. These tests exercise the module directly against
an isolated tmp_path repo root, never the real reports/seo/ tree.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parents[2]
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from seo.pipeline import pipeline_state as ps  # noqa: E402


@pytest.fixture(autouse=True)
def _isolated_repo_root(tmp_path):
    ps.configure(repo_root=tmp_path)
    yield tmp_path
    ps.configure()


class TestStageRegistry:
    def test_every_registered_path_is_relative(self):
        for stage_key, relpath in ps.STAGE_REGISTRY.items():
            assert not Path(relpath).is_absolute(), stage_key

    def test_frontmatter_grounding_has_no_entry(self):
        # frontmatter_grounding.py is a read-only library with no write of
        # its own -- confirmed by inspection, not a stale omission.
        assert "frontmatter_grounding" not in ps.STAGE_REGISTRY

    def test_known_real_producer_paths_are_registered(self):
        assert ps.STAGE_REGISTRY["page_index"] == "reports/seo/page_index.json"
        assert ps.STAGE_REGISTRY["patch_manifest"] == "patches/seo/patch_manifest.json"
        assert ps.STAGE_REGISTRY["schema_a_migration_state"] == "data/seo_schema_a_migration_state.json"


class TestLoadPipelineState:
    def test_bootstraps_empty_when_no_manifest_exists(self, _isolated_repo_root):
        state = ps.load_pipeline_state()
        assert state == {"schema_version": 1, "stages": {}}

    def test_no_manifest_file_is_created_by_a_read_only_load(self, _isolated_repo_root):
        ps.load_pipeline_state()
        assert not (_isolated_repo_root / "reports" / "seo" / "pipeline_state.json").exists()

    def test_corrupt_manifest_is_treated_as_empty_not_raised(self, _isolated_repo_root):
        manifest = _isolated_repo_root / "reports" / "seo" / "pipeline_state.json"
        manifest.parent.mkdir(parents=True, exist_ok=True)
        manifest.write_text("{not valid json", encoding="utf-8")
        state = ps.load_pipeline_state()
        assert state == {"schema_version": 1, "stages": {}}


class TestRecordStageWrite:
    def test_records_a_real_registered_stage(self, _isolated_repo_root):
        target = _isolated_repo_root / "reports" / "seo" / "page_index.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text('{"pages": []}', encoding="utf-8")

        ok = ps.record_stage_write("page_index")

        assert ok is True
        state = ps.load_pipeline_state()
        assert state["schema_version"] == 1
        entry = state["stages"]["page_index"]
        assert entry["path"] == "reports/seo/page_index.json"
        assert entry["size_bytes"] == len(b'{"pages": []}')
        assert entry["sha256"] == __import__("hashlib").sha256(b'{"pages": []}').hexdigest()
        assert "recorded_at" in entry

    def test_records_when_target_file_does_not_exist_yet(self, _isolated_repo_root):
        ok = ps.record_stage_write("opportunities")
        assert ok is True
        entry = ps.load_pipeline_state()["stages"]["opportunities"]
        assert entry["sha256"] is None
        assert entry["size_bytes"] is None

    def test_unknown_stage_key_with_no_path_is_non_fatal_no_op(self, _isolated_repo_root):
        ok = ps.record_stage_write("totally_made_up_stage")
        assert ok is False
        assert ps.load_pipeline_state()["stages"] == {}

    def test_unknown_stage_key_with_explicit_path_is_recorded(self, _isolated_repo_root):
        ok = ps.record_stage_write("future_stage", path="reports/seo/future_stage.json")
        assert ok is True
        assert ps.load_pipeline_state()["stages"]["future_stage"]["path"] == "reports/seo/future_stage.json"

    def test_writes_are_purely_additive_across_stages(self, _isolated_repo_root):
        ps.record_stage_write("page_index")
        ps.record_stage_write("opportunities")
        state = ps.load_pipeline_state()
        assert set(state["stages"]) == {"page_index", "opportunities"}

    def test_a_second_write_to_the_same_stage_overwrites_only_that_entry(self, _isolated_repo_root):
        ps.record_stage_write("page_index")
        first = ps.load_pipeline_state()["stages"]["page_index"]["recorded_at"]
        ps.record_stage_write("opportunities")

        target = _isolated_repo_root / "reports" / "seo" / "page_index.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text('{"pages": [1]}', encoding="utf-8")
        ps.record_stage_write("page_index")

        state = ps.load_pipeline_state()
        assert set(state["stages"]) == {"page_index", "opportunities"}
        assert state["stages"]["page_index"]["size_bytes"] == len(b'{"pages": [1]}')
        assert first is not None

    def test_extra_metadata_is_carried_when_provided(self, _isolated_repo_root):
        ps.record_stage_write("safety_summary", extra={"run_id": "it-0049"})
        entry = ps.load_pipeline_state()["stages"]["safety_summary"]
        assert entry["extra"] == {"run_id": "it-0049"}

    def test_never_raises_on_internal_failure(self, _isolated_repo_root, monkeypatch):
        def _boom(*args, **kwargs):
            raise OSError("simulated disk failure")

        monkeypatch.setattr(ps, "_save_atomic", _boom)
        ok = ps.record_stage_write("page_index")
        assert ok is False

    def test_atomic_write_leaves_no_temp_file_behind(self, _isolated_repo_root):
        ps.record_stage_write("page_index")
        seo_dir = _isolated_repo_root / "reports" / "seo"
        leftovers = [p for p in seo_dir.iterdir() if p.name.startswith(".seo_pipeline_state_")]
        assert leftovers == []

    def test_manifest_is_valid_json_with_schema_version(self, _isolated_repo_root):
        ps.record_stage_write("page_index")
        manifest = _isolated_repo_root / "reports" / "seo" / "pipeline_state.json"
        data = json.loads(manifest.read_text(encoding="utf-8"))
        assert data["schema_version"] == 1
