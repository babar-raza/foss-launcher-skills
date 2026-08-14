"""Tests for lib/bundle_manifest.py."""
from __future__ import annotations

import sys
from pathlib import Path

_PIPELINE_DIR = Path(__file__).resolve().parents[1]
if str(_PIPELINE_DIR) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_DIR))

from lib import bundle_manifest as bm


def _make_repo_with_generator_files(tmp_path: Path) -> Path:
    for rel in bm.GENERATOR_FINGERPRINT_PATHS:
        fpath = tmp_path / rel
        fpath.parent.mkdir(parents=True, exist_ok=True)
        fpath.write_text(f"# {rel}\nprint('hello')\n", encoding="utf-8")
    return tmp_path


class TestGeneratorFingerprint:
    def test_deterministic_for_same_content(self, tmp_path):
        repo1 = _make_repo_with_generator_files(tmp_path / "a")
        repo2 = _make_repo_with_generator_files(tmp_path / "b")
        assert bm.generator_fingerprint(repo1) == bm.generator_fingerprint(repo2)

    def test_changes_when_tracked_file_changes(self, tmp_path):
        repo = _make_repo_with_generator_files(tmp_path)
        before = bm.generator_fingerprint(repo)
        target = repo / bm.GENERATOR_FINGERPRINT_PATHS[0]
        target.write_text(target.read_text(encoding="utf-8") + "\n# changed\n", encoding="utf-8")
        after = bm.generator_fingerprint(repo)
        assert before != after

    def test_stable_when_untracked_file_changes(self, tmp_path):
        repo = _make_repo_with_generator_files(tmp_path)
        before = bm.generator_fingerprint(repo)
        unrelated = repo / "scripts" / "pipeline" / "commands" / "content" / "unrelated.py"
        unrelated.parent.mkdir(parents=True, exist_ok=True)
        unrelated.write_text("# not in the fingerprint list\n", encoding="utf-8")
        after = bm.generator_fingerprint(repo)
        assert before == after

    def test_missing_tracked_file_still_hashes_deterministically(self, tmp_path):
        repo = tmp_path  # none of the GENERATOR_FINGERPRINT_PATHS exist
        h1 = bm.generator_fingerprint(repo)
        h2 = bm.generator_fingerprint(repo)
        assert h1 == h2
        assert len(h1) == 64  # sha256 hex digest length

    def test_line_ending_normalization(self, tmp_path):
        repo_lf = _make_repo_with_generator_files(tmp_path / "lf")
        repo_crlf = tmp_path / "crlf"
        for rel in bm.GENERATOR_FINGERPRINT_PATHS:
            fpath = repo_crlf / rel
            fpath.parent.mkdir(parents=True, exist_ok=True)
            fpath.write_bytes(f"# {rel}\r\nprint('hello')\r\n".encode("utf-8"))
        assert bm.generator_fingerprint(repo_lf) == bm.generator_fingerprint(repo_crlf)


def _make_merged_dir(tmp_path: Path, *, with_snippets: bool = True) -> Path:
    merged = tmp_path / "knowledge" / "cells" / "net" / "merged"
    merged.mkdir(parents=True)
    (merged / "model.yaml").write_text("repo_sha: abc123\n", encoding="utf-8")
    (merged / "api_surface.json").write_text('{"classes": []}', encoding="utf-8")
    (merged / "formats.md").write_text("| Format | Support |\n", encoding="utf-8")
    (merged / "claims.json").write_text("[]", encoding="utf-8")
    # deliberately omit api_surface.md, formats.json, limitations.md, install.md,
    # merge_report.md to exercise the "not every product has every file" path
    if with_snippets:
        snip_dir = merged / "snippets"
        snip_dir.mkdir()
        (snip_dir / "snippet_001.cs").write_text("// example", encoding="utf-8")
    return merged


class TestComputeBundleManifest:
    def test_hashes_present_files_and_records_absent_as_none(self, tmp_path):
        merged = _make_merged_dir(tmp_path)
        manifest = bm.compute_bundle_manifest(
            merged, family="cells", platform="net", repo_sha="abc123",
            bundle_id="b1", generated_at="2026-08-14T00:00:00Z",
            generator_fingerprint_value="fp-fixed",
        )
        assert manifest["schema_version"] == bm.BUNDLE_SCHEMA_VERSION
        assert manifest["status"] == "COMPLETE"
        assert manifest["members"]["model.yaml"]["sha256"] is not None
        assert manifest["members"]["api_surface.md"]["sha256"] is None
        assert manifest["members"]["api_surface.md"]["bytes"] == 0
        assert "snippets/snippet_001.cs" in manifest["members"]
        assert manifest["members"]["snippets/snippet_001.cs"]["sha256"] is not None

    def test_no_snippets_dir_is_fine(self, tmp_path):
        merged = _make_merged_dir(tmp_path, with_snippets=False)
        manifest = bm.compute_bundle_manifest(
            merged, family="cells", platform="net", repo_sha="abc123",
            bundle_id="b1", generated_at="2026-08-14T00:00:00Z",
        )
        assert not any(k.startswith("snippets/") for k in manifest["members"])

    def test_computes_generator_fingerprint_when_repo_root_given(self, tmp_path):
        merged = _make_merged_dir(tmp_path)
        repo_root = tmp_path
        _make_repo_with_generator_files(repo_root)
        manifest = bm.compute_bundle_manifest(
            merged, family="cells", platform="net", repo_sha="abc123",
            bundle_id="b1", generated_at="2026-08-14T00:00:00Z",
            repo_root=repo_root,
        )
        assert manifest["generator_fingerprint"] == bm.generator_fingerprint(repo_root)


class TestVerifyBundleManifest:
    def test_no_mismatches_for_untouched_bundle(self, tmp_path):
        merged = _make_merged_dir(tmp_path)
        manifest = bm.compute_bundle_manifest(
            merged, family="cells", platform="net", repo_sha="abc123",
            bundle_id="b1", generated_at="2026-08-14T00:00:00Z",
        )
        assert bm.verify_bundle_manifest(merged, manifest) == []

    def test_detects_tampered_file(self, tmp_path):
        merged = _make_merged_dir(tmp_path)
        manifest = bm.compute_bundle_manifest(
            merged, family="cells", platform="net", repo_sha="abc123",
            bundle_id="b1", generated_at="2026-08-14T00:00:00Z",
        )
        (merged / "claims.json").write_text('[{"tampered": true}]', encoding="utf-8")
        mismatches = bm.verify_bundle_manifest(merged, manifest)
        assert len(mismatches) == 1
        assert "claims.json" in mismatches[0]

    def test_detects_deleted_file(self, tmp_path):
        merged = _make_merged_dir(tmp_path)
        manifest = bm.compute_bundle_manifest(
            merged, family="cells", platform="net", repo_sha="abc123",
            bundle_id="b1", generated_at="2026-08-14T00:00:00Z",
        )
        (merged / "claims.json").unlink()
        mismatches = bm.verify_bundle_manifest(merged, manifest)
        assert any("claims.json" in m and "missing" in m for m in mismatches)

    def test_detects_unexpectedly_present_file(self, tmp_path):
        merged = _make_merged_dir(tmp_path)
        manifest = bm.compute_bundle_manifest(
            merged, family="cells", platform="net", repo_sha="abc123",
            bundle_id="b1", generated_at="2026-08-14T00:00:00Z",
        )
        (merged / "api_surface.md").write_text("# surface\n", encoding="utf-8")
        mismatches = bm.verify_bundle_manifest(merged, manifest)
        assert any("api_surface.md" in m for m in mismatches)
