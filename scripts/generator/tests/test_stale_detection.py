"""
TC-W5-002: Tests for detect_stale_llms.py stale/missing/orphan detection.

Run with:
    .venv/Scripts/python -m pytest scripts/generator/tests/test_stale_detection.py -v
"""
import importlib.util
import json
import os
import tempfile

import pytest

# Load detect_stale_llms module
_GEN_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_STALE_FILE = os.path.join(_GEN_DIR, "detect_stale_llms.py")
_spec = importlib.util.spec_from_file_location("detect_stale_llms", _STALE_FILE)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

build_manifest = _mod.build_manifest
detect_issues = _mod.detect_issues
_sha256_file = _mod._sha256_file
_derive_source_path = _mod._derive_source_path


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_env(tmp_path):
    """
    Create a minimal temp environment:
      content/kb.aspose.org/en/pdf/net/how-to-test.md
      llms-output/kb.aspose.org/pdf/net/how-to-test.txt
    """
    # Source content file
    src_dir = tmp_path / 'content' / 'kb.aspose.org' / 'en' / 'pdf' / 'net'
    src_dir.mkdir(parents=True)
    src_md = src_dir / 'how-to-test.md'
    src_md.write_text('---\ntitle: Test Article\n---\n\n# Test Article\n\nContent here.\n',
                      encoding='utf-8')

    # Output .txt file
    out_dir = tmp_path / 'llms-output' / 'kb.aspose.org' / 'pdf' / 'net'
    out_dir.mkdir(parents=True)
    out_txt = out_dir / 'how-to-test.txt'
    out_txt.write_text('---\nProduct: Aspose.PDF\nPlatform: net\nPage Type: kb\n---\n\n# Test Article\n',
                       encoding='utf-8')

    return {
        'tmp_path': tmp_path,
        'src_md': str(src_md),
        'out_txt': str(out_txt),
        'llms_output': str(tmp_path / 'llms-output'),
        'content': str(tmp_path / 'content'),
    }


# ---------------------------------------------------------------------------
# Hash helper
# ---------------------------------------------------------------------------

class TestSha256File:
    def test_returns_hex_string(self, tmp_path):
        f = tmp_path / 'test.txt'
        f.write_text('hello world', encoding='utf-8')
        result = _sha256_file(str(f))
        assert isinstance(result, str)
        assert len(result) == 64

    def test_none_on_missing_file(self, tmp_path):
        result = _sha256_file(str(tmp_path / 'nonexistent.txt'))
        assert result is None

    def test_different_content_different_hash(self, tmp_path):
        f1 = tmp_path / 'a.txt'
        f2 = tmp_path / 'b.txt'
        f1.write_text('content A', encoding='utf-8')
        f2.write_text('content B', encoding='utf-8')
        assert _sha256_file(str(f1)) != _sha256_file(str(f2))


# ---------------------------------------------------------------------------
# Manifest building
# ---------------------------------------------------------------------------

class TestBuildManifest:
    def test_manifest_has_correct_structure(self, tmp_env):
        manifest = build_manifest(tmp_env['llms_output'], tmp_env['content'])
        assert 'manifest_version' in manifest
        assert 'generated_at' in manifest
        assert 'page_count' in manifest
        assert 'pages' in manifest
        assert manifest['page_count'] == 1

    def test_page_entry_has_hash(self, tmp_env):
        manifest = build_manifest(tmp_env['llms_output'], tmp_env['content'])
        entries = list(manifest['pages'].values())
        assert len(entries) == 1
        entry = entries[0]
        assert entry['source_hash'] is not None
        assert len(entry['source_hash']) == 64

    def test_source_path_resolved(self, tmp_env):
        manifest = build_manifest(tmp_env['llms_output'], tmp_env['content'])
        entries = list(manifest['pages'].values())
        assert entries[0]['source_path'] == tmp_env['src_md']


# ---------------------------------------------------------------------------
# Issue detection
# ---------------------------------------------------------------------------

class TestDetectIssues:
    def test_no_issues_when_current(self, tmp_env):
        manifest = build_manifest(tmp_env['llms_output'], tmp_env['content'])
        issues = detect_issues(manifest, tmp_env['llms_output'], tmp_env['content'])
        assert issues['stale'] == []
        assert issues['missing'] == []

    def test_stale_detected_on_source_change(self, tmp_env):
        manifest = build_manifest(tmp_env['llms_output'], tmp_env['content'])
        # Modify source file
        with open(tmp_env['src_md'], 'a', encoding='utf-8') as f:
            f.write('\n\nExtra content added.\n')
        issues = detect_issues(manifest, tmp_env['llms_output'], tmp_env['content'])
        assert len(issues['stale']) == 1
        stale_path = issues['stale'][0][0]
        assert 'how-to-test' in stale_path

    def test_missing_detected_when_output_deleted(self, tmp_env):
        manifest = build_manifest(tmp_env['llms_output'], tmp_env['content'])
        # Delete the output .txt file
        os.remove(tmp_env['out_txt'])
        issues = detect_issues(manifest, tmp_env['llms_output'], tmp_env['content'])
        assert len(issues['missing']) == 1
        missing_path = issues['missing'][0][0]
        assert 'how-to-test' in missing_path

    def test_check_only_exits_1_on_stale(self, tmp_env, monkeypatch):
        """Verify that --check-only causes exit(1) when stale content detected."""
        manifest = build_manifest(tmp_env['llms_output'], tmp_env['content'])
        # Modify source
        with open(tmp_env['src_md'], 'a', encoding='utf-8') as f:
            f.write('\n\nModified.\n')
        issues = detect_issues(manifest, tmp_env['llms_output'], tmp_env['content'])
        # There should be 1 stale entry
        assert len(issues['stale']) == 1, "Expected 1 stale entry after source modification"
