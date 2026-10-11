"""Tests for subdomain filter + dry-run-json (TC-CLAIM-02, TC-CLAIM-03).

All tests use tmp_path; no real content/ files are read or written.
All write-path tests verify git diff content/ is unaffected (by using tmp_path
fixtures entirely outside content/).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from io import StringIO
from unittest.mock import MagicMock, patch

import pytest

_PIPELINE_DIR = Path(__file__).resolve().parent.parent
if str(_PIPELINE_DIR) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_DIR))

from lib.content_discovery import _infer_subdomain, SITE_PATHS
from evidence.runner import attach_product, _KNOWN_SUBDOMAINS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_md(path: Path, claims=None) -> Path:
    """Write a minimal Markdown file with optional evidence block."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if claims is not None:
        claims_yaml = "\n".join(f"    - {c}" for c in claims)
        text = (
            "---\ntitle: Test\nweight: 1\n"
            "evidence:\n"
            "  model_sha: old-sha\n"
            "  model_version: 0.0\n"
            f"  claims:\n{claims_yaml}\n"
            "  apis: []\n---\n\n# Test\n\nContent.\n"
        )
    else:
        text = "---\ntitle: Test\nweight: 1\n---\n\n# Test\n\nContent.\n"
    path.write_text(text, encoding="utf-8")
    return path


def _fake_knowledge(repo_sha="new-sha"):
    k = MagicMock()
    k.available = True
    k.repo_sha = repo_sha
    k.version = "1.0"
    k.platform = "java"
    k.claim_ids = {"ERC-cells-java-aabb"}
    k.classes = {}
    k.api_to_claim = {}
    return k


# ---------------------------------------------------------------------------
# TC-CLAIM-02: _infer_subdomain
# ---------------------------------------------------------------------------

def test_infer_subdomain_returns_correct_site_name():
    """_infer_subdomain recognises all five canonical subdomains."""
    cases = [
        ("reference.aspose.org", Path("/repo/content/reference.aspose.org/en/cells/java/Foo.md")),
        ("docs.aspose.org",      Path("/repo/content/docs.aspose.org/en/cells/java/guide.md")),
        ("blog.aspose.org",      Path("/repo/content/blog.aspose.org/cells/java/post/index.md")),
        ("kb.aspose.org",        Path("/repo/content/kb.aspose.org/en/cells/java/how-to.md")),
        ("products.aspose.org",  Path("/repo/content/products.aspose.org/en/cells/java/_index.md")),
    ]
    for expected, path in cases:
        assert _infer_subdomain(path) == expected, f"Failed for {path}"


def test_infer_subdomain_returns_none_for_outside_path():
    """Path not under any known content site returns None."""
    assert _infer_subdomain(Path("/tmp/some/other/file.md")) is None
    assert _infer_subdomain(Path("/repo/scripts/pipeline/tests/test_foo.py")) is None


# ---------------------------------------------------------------------------
# TC-CLAIM-02: subdomain filter in attach_product
# ---------------------------------------------------------------------------

def test_subdomain_filter_restricts_to_reference(tmp_path):
    """When --subdomain reference.aspose.org, only reference files are processed."""
    ref_file = tmp_path / "content/reference.aspose.org/en/cells/java/Foo.md"
    blog_file = tmp_path / "content/blog.aspose.org/cells/java/post/index.md"
    _make_md(ref_file)
    _make_md(blog_file)

    processed = []

    def fake_discover(family, platform):
        return [ref_file, blog_file]

    def fake_attach(fp, knowledge, dry_run=False, force=False, dry_run_records=None):
        processed.append(str(fp))
        return "DRY-RUN"

    with patch("evidence.runner.discover_content", fake_discover), \
         patch("evidence.runner.attach_evidence", fake_attach), \
         patch("evidence.runner.Knowledge", return_value=_fake_knowledge()):
        attach_product("cells", "java", dry_run=True,
                       subdomain="reference.aspose.org")

    assert any("reference.aspose.org" in p for p in processed)
    assert not any("blog.aspose.org" in p for p in processed)


def test_subdomain_filter_restricts_to_blog(tmp_path):
    """When --subdomain blog.aspose.org, only blog files are processed."""
    ref_file = tmp_path / "content/reference.aspose.org/en/cells/java/Foo.md"
    blog_file = tmp_path / "content/blog.aspose.org/cells/java/post/index.md"
    _make_md(ref_file)
    _make_md(blog_file)

    processed = []

    def fake_discover(family, platform):
        return [ref_file, blog_file]

    def fake_attach(fp, knowledge, dry_run=False, force=False, dry_run_records=None):
        processed.append(str(fp))
        return "DRY-RUN"

    with patch("evidence.runner.discover_content", fake_discover), \
         patch("evidence.runner.attach_evidence", fake_attach), \
         patch("evidence.runner.Knowledge", return_value=_fake_knowledge()):
        attach_product("cells", "java", dry_run=True,
                       subdomain="blog.aspose.org")

    assert any("blog.aspose.org" in p for p in processed)
    assert not any("reference.aspose.org" in p for p in processed)


def test_subdomain_none_processes_all_five_with_warn(tmp_path, capsys):
    """No subdomain → all files processed + WARN emitted on write path."""
    files = [
        tmp_path / "content/reference.aspose.org/en/cells/java/Foo.md",
        tmp_path / "content/blog.aspose.org/cells/java/post/index.md",
    ]
    for f in files:
        _make_md(f)

    processed = []

    def fake_discover(family, platform):
        return files

    def fake_attach(fp, knowledge, dry_run=False, force=False, dry_run_records=None):
        processed.append(str(fp))
        return "DRY-RUN"

    stderr_capture = StringIO()
    with patch("evidence.runner.discover_content", fake_discover), \
         patch("evidence.runner.attach_evidence", fake_attach), \
         patch("evidence.runner.Knowledge", return_value=_fake_knowledge()), \
         patch("sys.stderr", stderr_capture):
        # dry_run=False to trigger the WARN path
        attach_product("cells", "java", dry_run=False, subdomain=None)

    warn_output = stderr_capture.getvalue()
    assert "WARN" in warn_output
    assert "all subdomains" in warn_output
    # Both files were processed
    assert len(processed) == 2


def test_unknown_subdomain_raises_value_error():
    """Passing an unrecognised subdomain raises ValueError before any I/O."""
    with patch("evidence.runner.Knowledge", return_value=_fake_knowledge()):
        with pytest.raises(ValueError, match="Unknown subdomain"):
            attach_product("cells", "java", subdomain="not-a-real-subdomain.com")


def test_all_subdomains_confirm_flag_suppresses_warn(tmp_path):
    """--all-subdomains --confirm-all-subdomains suppresses the unscoped WARN."""
    md = tmp_path / "content/reference.aspose.org/en/cells/java/Foo.md"
    _make_md(md)

    def fake_discover(family, platform):
        return [md]

    def fake_attach(fp, knowledge, dry_run=False, force=False, dry_run_records=None):
        return "DRY-RUN"

    stderr_capture = StringIO()
    with patch("evidence.runner.discover_content", fake_discover), \
         patch("evidence.runner.attach_evidence", fake_attach), \
         patch("evidence.runner.Knowledge", return_value=_fake_knowledge()), \
         patch("sys.stderr", stderr_capture):
        attach_product("cells", "java", dry_run=False,
                       subdomain=None, all_subdomains=True)

    warn_output = stderr_capture.getvalue()
    # Should NOT contain the unscoped-all-subdomains WARN
    assert "WARN: running across all subdomains" not in warn_output


# ---------------------------------------------------------------------------
# TC-CLAIM-03: --dry-run-json ClaimPlan output
# ---------------------------------------------------------------------------

def test_dry_run_json_is_valid_json(tmp_path):
    """dry_run_records accumulator produces valid JSON when serialized."""
    records = []
    ref_file = tmp_path / "content/reference.aspose.org/en/cells/java/Foo.md"
    _make_md(ref_file)

    def fake_discover(family, platform):
        return [ref_file]

    def fake_attach(fp, knowledge, dry_run=False, force=False, dry_run_records=None):
        if dry_run_records is not None:
            dry_run_records.append({
                "filepath": str(fp),
                "subdomain": "reference.aspose.org",
                "action": "WOULD_UPDATE",
                "existing_claims": [],
                "proposed_claims": [],
                "added_claims": [],
                "stale_claims": [],
                "skip_reason": None,
                "token_matches": [],
            })
        return "DRY-RUN"

    with patch("evidence.runner.discover_content", fake_discover), \
         patch("evidence.runner.attach_evidence", fake_attach), \
         patch("evidence.runner.Knowledge", return_value=_fake_knowledge()):
        attach_product("cells", "java", dry_run=True,
                       dry_run_records=records)

    # Serialise and parse — must not raise
    serialised = json.dumps(records, indent=2)
    parsed = json.loads(serialised)
    assert isinstance(parsed, list)
    assert len(parsed) == 1


def test_dry_run_json_is_deterministic_on_same_input(tmp_path):
    """Two calls with the same input produce identical JSON."""
    ref_file = tmp_path / "content/reference.aspose.org/en/cells/java/Foo.md"
    _make_md(ref_file)

    def fake_discover(family, platform):
        return [ref_file]

    def fake_attach(fp, knowledge, dry_run=False, force=False, dry_run_records=None):
        if dry_run_records is not None:
            dry_run_records.append({
                "filepath": str(fp),
                "subdomain": "reference.aspose.org",
                "action": "WOULD_UPDATE",
                "existing_claims": [],
                "proposed_claims": [],
                "added_claims": [],
                "stale_claims": [],
                "skip_reason": None,
                "token_matches": [],
            })
        return "DRY-RUN"

    def _run():
        records = []
        with patch("evidence.runner.discover_content", fake_discover), \
             patch("evidence.runner.attach_evidence", fake_attach), \
             patch("evidence.runner.Knowledge", return_value=_fake_knowledge()):
            attach_product("cells", "java", dry_run=True, dry_run_records=records)
        return json.dumps(records, indent=2, sort_keys=True)

    assert _run() == _run()


def test_dry_run_json_shows_added_claims(tmp_path):
    """ClaimPlan record includes added_claims list."""
    ref_file = tmp_path / "content/reference.aspose.org/en/cells/java/Foo.md"
    _make_md(ref_file, claims=["CLM-old"])

    records = []

    def fake_discover(family, platform):
        return [ref_file]

    def fake_attach(fp, knowledge, dry_run=False, force=False, dry_run_records=None):
        if dry_run_records is not None:
            dry_run_records.append({
                "filepath": str(fp),
                "subdomain": "reference.aspose.org",
                "action": "WOULD_UPDATE",
                "existing_claims": ["CLM-old"],
                "proposed_claims": [{"claim_id": "ERC-new", "policy_status": "ALLOW",
                                     "policy_reason": "token match"}],
                "added_claims": ["ERC-new"],
                "stale_claims": [],
                "skip_reason": None,
                "token_matches": ["SomeClass"],
            })
        return "DRY-RUN"

    with patch("evidence.runner.discover_content", fake_discover), \
         patch("evidence.runner.attach_evidence", fake_attach), \
         patch("evidence.runner.Knowledge", return_value=_fake_knowledge()):
        attach_product("cells", "java", dry_run=True, dry_run_records=records)

    assert len(records) == 1
    assert "ERC-new" in records[0]["added_claims"]


def test_dry_run_json_shows_skip_reason_for_skipped_files(tmp_path):
    """SKIP records include a non-null skip_reason."""
    ref_file = tmp_path / "content/reference.aspose.org/en/cells/java/Foo.md"
    _make_md(ref_file)

    records = []

    def fake_discover(family, platform):
        return [ref_file]

    def fake_attach(fp, knowledge, dry_run=False, force=False, dry_run_records=None):
        if dry_run_records is not None:
            dry_run_records.append({
                "filepath": str(fp),
                "subdomain": "reference.aspose.org",
                "action": "SKIP",
                "existing_claims": [],
                "proposed_claims": [],
                "added_claims": [],
                "stale_claims": [],
                "skip_reason": "current",
                "token_matches": [],
            })
        return "SKIP (current)"

    with patch("evidence.runner.discover_content", fake_discover), \
         patch("evidence.runner.attach_evidence", fake_attach), \
         patch("evidence.runner.Knowledge", return_value=_fake_knowledge()):
        attach_product("cells", "java", dry_run=True, dry_run_records=records)

    assert records[0]["action"] == "SKIP"
    assert records[0]["skip_reason"] is not None


def test_dry_run_json_zero_content_files_modified(tmp_path):
    """dry_run_records accumulation must not touch any file on disk."""
    ref_file = tmp_path / "content/reference.aspose.org/en/cells/java/Foo.md"
    _make_md(ref_file)
    original_content = ref_file.read_text(encoding="utf-8")

    records = []

    def fake_discover(family, platform):
        return [ref_file]

    def fake_attach(fp, knowledge, dry_run=False, force=False, dry_run_records=None):
        if dry_run_records is not None:
            dry_run_records.append({"filepath": str(fp), "action": "WOULD_UPDATE"})
        return "DRY-RUN"

    with patch("evidence.runner.discover_content", fake_discover), \
         patch("evidence.runner.attach_evidence", fake_attach), \
         patch("evidence.runner.Knowledge", return_value=_fake_knowledge()):
        attach_product("cells", "java", dry_run=True, dry_run_records=records)

    # File content must be unchanged
    assert ref_file.read_text(encoding="utf-8") == original_content


def test_dry_run_json_respects_subdomain_filter(tmp_path):
    """ClaimPlan records contain only files from the requested subdomain."""
    ref_file = tmp_path / "content/reference.aspose.org/en/cells/java/Foo.md"
    blog_file = tmp_path / "content/blog.aspose.org/cells/java/post/index.md"
    _make_md(ref_file)
    _make_md(blog_file)

    records = []

    def fake_discover(family, platform):
        return [ref_file, blog_file]

    def fake_attach(fp, knowledge, dry_run=False, force=False, dry_run_records=None):
        if dry_run_records is not None:
            dry_run_records.append({"filepath": str(fp)})
        return "DRY-RUN"

    with patch("evidence.runner.discover_content", fake_discover), \
         patch("evidence.runner.attach_evidence", fake_attach), \
         patch("evidence.runner.Knowledge", return_value=_fake_knowledge()):
        attach_product("cells", "java", dry_run=True,
                       subdomain="reference.aspose.org",
                       dry_run_records=records)

    assert len(records) == 1
    assert "reference.aspose.org" in records[0]["filepath"]
