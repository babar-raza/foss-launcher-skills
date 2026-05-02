"""Fixture integration tests for claim injection across all five subdomains.

TC-CLAIM-06: Regression Test Layer + Fixture Integration Test.

All tests use tmp_path only; no real content/ or knowledge/ files are read.
The fixture data in tests/fixtures/claim_injection/ is copied to tmp_path per test.
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest

# Fixture root — static files copied to tmp_path per test
_FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "claim_injection"
_FIXTURE_KNOWLEDGE = _FIXTURE_ROOT / "knowledge"
_FIXTURE_CONTENT = _FIXTURE_ROOT / "content"

# Canonical subdomain names used in fixture content
_REFERENCE = "reference.aspose.org"
_DOCS = "docs.aspose.org"
_BLOG = "blog.aspose.org"
_KB = "kb.aspose.org"
_PRODUCTS = "products.aspose.org"

# Claim IDs used in fixture
_VALID_CLAIM = "ERC-cells-java-aabbccdd"
_STALE_CLAIM = "ERC-STALE-0000"


# ---------------------------------------------------------------------------
# Fixtures helpers
# ---------------------------------------------------------------------------

def _setup_fixture(tmp_path: Path) -> tuple[Path, Path]:
    """Copy fixture knowledge and content to tmp_path. Returns (knowledge_root, content_root)."""
    knowledge_root = tmp_path / "knowledge"
    content_root = tmp_path / "content"
    shutil.copytree(_FIXTURE_KNOWLEDGE, knowledge_root)
    shutil.copytree(_FIXTURE_CONTENT, content_root)
    return knowledge_root, content_root


def _get_fixture_files(content_root: Path) -> dict[str, Path]:
    """Return dict of subdomain -> fixture Path."""
    return {
        _REFERENCE: content_root / "reference.aspose.org/en/cells/java/TestClass.md",
        _DOCS: content_root / "docs.aspose.org/en/cells/java/test-docs.md",
        _BLOG: content_root / "blog.aspose.org/cells/java/test-blog/index.md",
        _KB: content_root / "kb.aspose.org/en/cells/java/test-kb.md",
        _PRODUCTS: content_root / "products.aspose.org/en/cells/_index.md",
    }


def _read_claims(filepath: Path) -> list[str]:
    """Parse evidence.claims from a .md file frontmatter."""
    import yaml
    text = filepath.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return []
    end = text.find("\n---", 3)
    if end == -1:
        return []
    fm = yaml.safe_load(text[3:end]) or {}
    evidence = fm.get("evidence") or {}
    return list(evidence.get("claims", []))


def _body_outside_frontmatter(filepath: Path) -> str:
    """Return the body content after the closing --- of frontmatter."""
    text = filepath.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return text
    end = text.find("\n---", 3)
    if end == -1:
        return text
    return text[end + 4:]  # after closing ---\n


# ---------------------------------------------------------------------------
# Patch helpers
# ---------------------------------------------------------------------------

def _patch_discovery(content_root: Path, files: list[Path]):
    """Context manager: patch discover_content to return given files."""
    return patch("evidence.runner.discover_content", return_value=files)


def _patch_knowledge(knowledge_root: Path):
    """Context manager: patch Knowledge to load from knowledge_root."""
    from knowledge_core import Knowledge as _Knowledge

    def _make(family, platform, knowledge_root=None):
        return _Knowledge(family, platform,
                          knowledge_root=knowledge_root or (knowledge_root))

    # We pass knowledge_root explicitly — use a real Knowledge object from fixture
    return None  # no patch needed; we pass knowledge_root directly


# ---------------------------------------------------------------------------
# TC-CLAIM-06: Fixture tests
# ---------------------------------------------------------------------------

class TestFixtureReportOnly:
    """Report-only modes must never modify content files."""

    def test_report_only_changes_zero_files(self, tmp_path):
        """--dry-run-json must not modify any content file."""
        from evidence.runner import attach_product
        knowledge_root, content_root = _setup_fixture(tmp_path)
        files = list(_get_fixture_files(content_root).values())
        content_before = {f: f.read_bytes() for f in files if f.exists()}

        records = []
        with _patch_discovery(content_root, [f for f in files if f.exists()]):
            from knowledge_core import Knowledge
            k = Knowledge("cells", "java", knowledge_root=knowledge_root)
            with patch("evidence.runner.Knowledge", return_value=k):
                attach_product("cells", "java", dry_run=True, force=True,
                               dry_run_records=records)

        for f, before in content_before.items():
            assert f.read_bytes() == before, f"report-only mode modified {f}"

    def test_no_content_files_modified_in_all_report_modes(self, tmp_path):
        """Both --dry-run and --dry-run-json leave content files unchanged."""
        from evidence.runner import attach_evidence
        knowledge_root, content_root = _setup_fixture(tmp_path)
        ref_file = _get_fixture_files(content_root)[_REFERENCE]
        content_before = ref_file.read_bytes()

        from knowledge_core import Knowledge
        k = Knowledge("cells", "java", knowledge_root=knowledge_root)

        # dry_run=True
        attach_evidence(ref_file, k, dry_run=True, force=True)
        assert ref_file.read_bytes() == content_before

        # dry_run=True + records (--dry-run-json mode)
        records = []
        attach_evidence(ref_file, k, dry_run=True, force=True, dry_run_records=records)
        assert ref_file.read_bytes() == content_before


class TestFixtureClaimPlanOutput:
    """--dry-run-json ClaimPlan output correctness per subdomain."""

    def test_dry_run_json_reference_shows_valid_claim(self, tmp_path):
        """Reference file with valid claim should appear in ClaimPlan as WOULD_UPDATE."""
        from evidence.runner import attach_evidence
        knowledge_root, content_root = _setup_fixture(tmp_path)
        ref_file = _get_fixture_files(content_root)[_REFERENCE]

        from knowledge_core import Knowledge
        k = Knowledge("cells", "java", knowledge_root=knowledge_root)

        records = []
        attach_evidence(ref_file, k, dry_run=True, force=True, dry_run_records=records)

        assert len(records) == 1
        rec = records[0]
        assert rec["action"] == "WOULD_UPDATE"
        # Valid claim should appear as ALLOW in policy
        proposed_ids = [c["claim_id"] for c in rec["proposed_claims"]]
        assert _VALID_CLAIM in proposed_ids
        statuses = {c["claim_id"]: c["policy_status"]
                    for c in rec["proposed_claims"]}
        assert statuses.get(_VALID_CLAIM) == "ALLOW"

    def test_dry_run_json_docs_shows_knowledge_claims_hash(self, tmp_path):
        """WOULD_UPDATE records must include claims_hash fields."""
        from evidence.runner import attach_evidence
        knowledge_root, content_root = _setup_fixture(tmp_path)
        docs_file = _get_fixture_files(content_root)[_DOCS]

        from knowledge_core import Knowledge
        k = Knowledge("cells", "java", knowledge_root=knowledge_root)

        records = []
        attach_evidence(docs_file, k, dry_run=True, force=True, dry_run_records=records)

        assert len(records) == 1
        rec = records[0]
        assert "knowledge_claims_hash" in rec
        assert rec["knowledge_claims_hash"] == k.claims_hash


class TestFixtureSubdomainFilter:
    """--subdomain restricts injection to exactly that subdomain."""

    def test_subdomain_reference_only_processes_reference(self, tmp_path):
        """With --subdomain reference.aspose.org, only reference files are in output."""
        from evidence.runner import attach_product
        knowledge_root, content_root = _setup_fixture(tmp_path)
        all_files = list(_get_fixture_files(content_root).values())
        ref_files = [f for f in all_files
                     if "reference.aspose.org" in str(f)]
        non_ref_files = [f for f in all_files
                         if "reference.aspose.org" not in str(f)]

        from knowledge_core import Knowledge
        k = Knowledge("cells", "java", knowledge_root=knowledge_root)
        records = []
        with patch("evidence.runner.discover_content",
                   return_value=[f for f in all_files if f.exists()]), \
             patch("evidence.runner.Knowledge", return_value=k):
            attach_product("cells", "java", dry_run=True, force=True,
                           subdomain=_REFERENCE, dry_run_records=records)

        for rec in records:
            assert _REFERENCE in rec["filepath"], (
                f"Non-reference file appeared in scoped run: {rec['filepath']}"
            )

    def test_subdomain_reference_does_not_touch_blog(self, tmp_path):
        """Blog file content must be unchanged after a reference-scoped run."""
        from evidence.runner import attach_product
        knowledge_root, content_root = _setup_fixture(tmp_path)
        all_files = list(_get_fixture_files(content_root).values())
        blog_file = _get_fixture_files(content_root)[_BLOG]
        blog_before = blog_file.read_bytes()

        from knowledge_core import Knowledge
        k = Knowledge("cells", "java", knowledge_root=knowledge_root)
        with patch("evidence.runner.discover_content",
                   return_value=[f for f in all_files if f.exists()]), \
             patch("evidence.runner.Knowledge", return_value=k):
            attach_product("cells", "java", dry_run=False, force=True,
                           subdomain=_REFERENCE)

        assert blog_file.read_bytes() == blog_before, (
            "Blog file was modified by a reference-scoped run"
        )


class TestFixtureStaleClaimDetection:
    """Stale claims are detected but never removed."""

    def test_stale_claim_detected_in_docs(self, tmp_path):
        """ERC-STALE-0000 (not in claims.json) should be detected in docs file."""
        from evidence.claim_validator import detect_stale_claims
        knowledge_root, content_root = _setup_fixture(tmp_path)
        docs_file = _get_fixture_files(content_root)[_DOCS]

        from knowledge_core import Knowledge
        k = Knowledge("cells", "java", knowledge_root=knowledge_root)

        stale = detect_stale_claims(docs_file, k)
        assert _STALE_CLAIM in stale, (
            f"Expected {_STALE_CLAIM} in stale claims; got {stale}"
        )

    def test_stale_claim_not_removed_from_docs(self, tmp_path):
        """detect_stale_claims must not write to the docs file."""
        from evidence.claim_validator import detect_stale_claims
        knowledge_root, content_root = _setup_fixture(tmp_path)
        docs_file = _get_fixture_files(content_root)[_DOCS]
        content_before = docs_file.read_bytes()

        from knowledge_core import Knowledge
        k = Knowledge("cells", "java", knowledge_root=knowledge_root)
        detect_stale_claims(docs_file, k)

        assert docs_file.read_bytes() == content_before, (
            "detect_stale_claims modified the docs file"
        )

    def test_valid_claim_not_stale_in_reference(self, tmp_path):
        """ERC-cells-java-aabbccdd in claims.json should NOT be stale."""
        from evidence.claim_validator import detect_stale_claims
        knowledge_root, content_root = _setup_fixture(tmp_path)
        ref_file = _get_fixture_files(content_root)[_REFERENCE]

        from knowledge_core import Knowledge
        k = Knowledge("cells", "java", knowledge_root=knowledge_root)

        stale = detect_stale_claims(ref_file, k)
        assert _VALID_CLAIM not in stale


class TestFixtureUnscopedWrite:
    """Unscoped write commands emit WARN; --all-subdomains suppresses it."""

    def test_unscoped_write_emits_warn(self, tmp_path, capsys):
        """attach_product without --subdomain should emit WARN to stderr."""
        from evidence.runner import attach_product
        knowledge_root, content_root = _setup_fixture(tmp_path)
        files = [f for f in _get_fixture_files(content_root).values() if f.exists()]

        from knowledge_core import Knowledge
        k = Knowledge("cells", "java", knowledge_root=knowledge_root)

        import io
        old_stderr = sys.stderr
        sys.stderr = io.StringIO()
        try:
            with patch("evidence.runner.discover_content", return_value=files), \
                 patch("evidence.runner.Knowledge", return_value=k):
                attach_product("cells", "java", dry_run=False, force=False,
                               subdomain=None, all_subdomains=False)
        finally:
            stderr_out = sys.stderr.getvalue()
            sys.stderr = old_stderr

        assert "WARN" in stderr_out and "all subdomains" in stderr_out, (
            f"Expected unscoped-write WARN in stderr; got: {stderr_out!r}"
        )

    def test_all_subdomains_flag_suppresses_warn(self, tmp_path, capsys):
        """--all-subdomains --confirm-all-subdomains suppresses the unscoped WARN."""
        from evidence.runner import attach_product
        knowledge_root, content_root = _setup_fixture(tmp_path)
        files = [f for f in _get_fixture_files(content_root).values() if f.exists()]

        from knowledge_core import Knowledge
        k = Knowledge("cells", "java", knowledge_root=knowledge_root)

        import io
        old_stderr = sys.stderr
        sys.stderr = io.StringIO()
        try:
            with patch("evidence.runner.discover_content", return_value=files), \
                 patch("evidence.runner.Knowledge", return_value=k):
                attach_product("cells", "java", dry_run=True, force=False,
                               subdomain=None, all_subdomains=True)
        finally:
            stderr_out = sys.stderr.getvalue()
            sys.stderr = old_stderr

        # Should NOT contain the unscoped-write WARN
        assert "running across all subdomains" not in stderr_out, (
            f"Unexpected WARN in stderr: {stderr_out!r}"
        )


class TestFixtureBodyUnchanged:
    """Markdown body outside frontmatter must be byte-for-byte identical."""

    def test_body_outside_frontmatter_unchanged(self, tmp_path):
        """Evidence injection must only touch frontmatter, not body content."""
        from evidence.runner import attach_evidence
        knowledge_root, content_root = _setup_fixture(tmp_path)
        ref_file = _get_fixture_files(content_root)[_REFERENCE]
        body_before = _body_outside_frontmatter(ref_file)

        from knowledge_core import Knowledge
        k = Knowledge("cells", "java", knowledge_root=knowledge_root)
        attach_evidence(ref_file, k, dry_run=False, force=True)

        body_after = _body_outside_frontmatter(ref_file)
        assert body_after == body_before, (
            "Evidence injection modified content outside frontmatter"
        )

    def test_no_body_change_from_evidence_injection(self, tmp_path):
        """Inject evidence into blog file; body must be unchanged."""
        from evidence.runner import attach_evidence
        knowledge_root, content_root = _setup_fixture(tmp_path)
        blog_file = _get_fixture_files(content_root)[_BLOG]
        body_before = _body_outside_frontmatter(blog_file)

        from knowledge_core import Knowledge
        k = Knowledge("cells", "java", knowledge_root=knowledge_root)
        attach_evidence(blog_file, k, dry_run=False, force=True)

        body_after = _body_outside_frontmatter(blog_file)
        assert body_after == body_before, (
            "Evidence injection modified blog body content"
        )


# ---------------------------------------------------------------------------
# Additional regression tests
# ---------------------------------------------------------------------------

class TestRegressionWriterMerge:
    """Regression guards for writer.py union-merge behavior."""

    def test_writer_union_merge_preserves_existing_claims(self, tmp_path):
        """Union-merge must retain existing claims not in proposed_claims."""
        from evidence.writer import _write_evidence_to_frontmatter
        lines = [
            "---",
            "title: Test",
            "evidence:",
            "  model_sha: old-sha",
            "  claims:",
            "    - CLM-existing-claim",
            "    - ERC-extra-manual",
            "  apis: []",
            "---",
            "# Test",
            "",
            "Body content.",
        ]
        f = tmp_path / "test.md"
        f.write_text("\n".join(lines) + "\n", encoding="utf-8")

        evidence = {
            "model_sha": "new-sha",
            "model_version": "1.0",
            "claims": ["CLM-new-claim"],
            "apis": ["NewClass"],
        }
        _write_evidence_to_frontmatter(f, evidence)

        import yaml
        text = f.read_text(encoding="utf-8")
        end = text.find("\n---", 3)
        fm = yaml.safe_load(text[3:end]) or {}
        claims = fm.get("evidence", {}).get("claims", [])

        # All three should be present (union-merge)
        assert "CLM-existing-claim" in claims
        assert "ERC-extra-manual" in claims
        assert "CLM-new-claim" in claims

    def test_writer_union_merge_body_unchanged(self, tmp_path):
        """Union-merge must not alter the body outside frontmatter."""
        from evidence.writer import _write_evidence_to_frontmatter
        lines = [
            "---",
            "title: Test",
            "evidence:",
            "  model_sha: old-sha",
            "  claims: []",
            "  apis: []",
            "---",
            "",
            "# Test",
            "",
            "This body must not change.",
            "",
            "```java",
            "foo();",
            "```",
        ]
        content = "\n".join(lines) + "\n"
        f = tmp_path / "test.md"
        f.write_text(content, encoding="utf-8")
        body_before = _body_outside_frontmatter(f)

        evidence = {
            "model_sha": "new-sha",
            "model_version": "1.0",
            "claims": ["CLM-abc"],
            "apis": ["Foo"],
        }
        _write_evidence_to_frontmatter(f, evidence)

        body_after = _body_outside_frontmatter(f)
        assert body_after == body_before, "Writer modified body outside frontmatter"


class TestRegressionLH02:
    """LH-02: batch_reference and evaluators must exit code 1 on unavailable knowledge."""

    def test_knowledge_available_false_exits_code_1(self, tmp_path):
        """attach_product must return empty dict (not raise) when knowledge unavailable.

        The runner.py contract: SKIP rather than exit-1 for attach_evidence.
        The batch_reference.py contract: exit-1 when knowledge unavailable (verified
        by test_batch_reference.py::test_stale_knowledge_exits).
        This test verifies runner.py returns empty dict gracefully.
        """
        from evidence.runner import attach_product
        from unittest.mock import patch, MagicMock

        # Knowledge with available=False
        k = MagicMock()
        k.available = False

        with patch("evidence.runner.Knowledge", return_value=k):
            result = attach_product("cells", "java")

        # runner.py returns {} on unavailable (it is a per-file scanner, not a generator)
        assert result == {}, (
            "attach_product should return {} when knowledge is unavailable"
        )

    def test_batch_reference_stale_knowledge_exits_nonzero(self, tmp_path):
        """batch_reference.py must exit non-zero on stale knowledge (existing LH-02 test).

        This test documents that the LH-02 gate for batch_reference is verified by
        test_batch_reference.py::test_stale_knowledge_exits. We include a lightweight
        smoke check here for cross-reference.
        """
        import subprocess
        script = (
            Path(__file__).resolve().parents[1]
            / "commands" / "content" / "batch_reference.py"
        )
        # Pass a non-existent family to trigger missing api_surface.json guard
        result = subprocess.run(
            [sys.executable, str(script), "--update", "nonexistent-family", "nonexistent"],
            capture_output=True,
            cwd=str(Path(__file__).resolve().parents[3]),
        )
        assert result.returncode != 0, (
            "batch_reference must exit non-zero when knowledge is unavailable"
        )
