"""Tests for scripts/pipeline/lib/vector_store.py (TC-VEC-03-A, RC2 staleness detection)."""

import hashlib
import json

# sys.path is set by tests/conftest.py — no manual insert needed here.
import vector_store as vs


def _write_api_surface(tmp_path, family, platform, content: bytes = b'[{"name": "Foo"}]'):
    merged = tmp_path / "knowledge" / family / platform / "merged"
    merged.mkdir(parents=True, exist_ok=True)
    api_path = merged / "api_surface.json"
    api_path.write_bytes(content)
    return api_path


def _write_profile(tmp_path, family, platform, *, source_hash: str, profile_id: str = "p1"):
    root = tmp_path / "knowledge" / "_vectors" / family / platform
    profile_dir = root / "profiles" / profile_id
    profile_dir.mkdir(parents=True, exist_ok=True)
    (root / "active.json").write_text(
        json.dumps({"version": "2.0.0", "profile_id": profile_id}), encoding="utf-8"
    )
    (profile_dir / "manifest.json").write_text(
        json.dumps({"profile_id": profile_id, "source_hash": source_hash}), encoding="utf-8"
    )


class TestVectorStatus:
    def setup_method(self):
        vs.configure()

    def teardown_method(self):
        vs.configure()

    def test_missing_when_no_api_surface(self, tmp_path):
        vs.configure(knowledge_root=tmp_path / "knowledge")
        assert vs.vector_status("widgets", "python") == vs.VectorStatus.MISSING

    def test_missing_when_no_active_profile(self, tmp_path):
        _write_api_surface(tmp_path, "widgets", "python")
        vs.configure(knowledge_root=tmp_path / "knowledge")
        assert vs.vector_status("widgets", "python") == vs.VectorStatus.MISSING

    def test_current_when_hash_matches(self, tmp_path):
        api_path = _write_api_surface(tmp_path, "widgets", "python")
        matching_hash = hashlib.sha256(api_path.read_bytes()).hexdigest()
        _write_profile(tmp_path, "widgets", "python", source_hash=matching_hash)
        vs.configure(knowledge_root=tmp_path / "knowledge")

        assert vs.vector_status("widgets", "python") == vs.VectorStatus.CURRENT
        assert vs.vectors_are_current("widgets", "python") is True

    def test_stale_when_hash_mismatches(self, tmp_path):
        _write_api_surface(tmp_path, "widgets", "python")
        _write_profile(tmp_path, "widgets", "python", source_hash="0" * 64)
        vs.configure(knowledge_root=tmp_path / "knowledge")

        assert vs.vector_status("widgets", "python") == vs.VectorStatus.STALE
        assert vs.vectors_are_current("widgets", "python") is False

    def test_stale_is_distinct_from_missing(self, tmp_path):
        """The exact requirement this module exists for: a reader must never
        conflate 'vectors exist but are out of date' with 'no vectors at all'."""
        _write_api_surface(tmp_path, "widgets", "python")
        _write_profile(tmp_path, "widgets", "python", source_hash="0" * 64)
        vs.configure(knowledge_root=tmp_path / "knowledge")
        stale_result = vs.vector_status("widgets", "python")

        vs.configure(knowledge_root=(tmp_path / "empty_knowledge"))
        missing_result = vs.vector_status("widgets", "python")

        assert stale_result != missing_result
        assert stale_result == vs.VectorStatus.STALE
        assert missing_result == vs.VectorStatus.MISSING

    def test_missing_profile_id_in_active_json(self, tmp_path):
        """A malformed/corrupt active.json must not raise — degrade to MISSING."""
        _write_api_surface(tmp_path, "widgets", "python")
        root = tmp_path / "knowledge" / "_vectors" / "widgets" / "python"
        root.mkdir(parents=True, exist_ok=True)
        (root / "active.json").write_text(json.dumps({"version": "2.0.0"}), encoding="utf-8")
        vs.configure(knowledge_root=tmp_path / "knowledge")

        assert vs.vector_status("widgets", "python") == vs.VectorStatus.MISSING
