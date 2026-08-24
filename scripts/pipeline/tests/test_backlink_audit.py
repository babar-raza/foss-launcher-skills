"""test_backlink_audit.py — Unit tests for backlink_audit.py.

New test file (2026-08-21, TC14): backlink_audit.py had zero test coverage
before this. Added specifically to prove audit_file()/run_audit() actually
surface the 3 violation classes classify_compliance() already supports
(WRONG_ANCHOR_TEXT, DUPLICATE_LINK, DUPLICATE_SUBDOMAIN) -- confirmed live
before this fix that audit_file() never passed the existing_links/
expected_anchor_text kwargs needed for WRONG_ANCHOR_TEXT, so it could never
fire even though the detection logic existed; DUPLICATE_LINK/
DUPLICATE_SUBDOMAIN needed no new inputs but were never tallied into
AuditTotals/build_report()'s counters.

Run:
    python -m pytest scripts/pipeline/tests/test_backlink_audit.py -v
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from commands.ops.backlink_audit import (
    audit_file, run_audit, build_report,
    STATUS_COMPLIANT, STATUS_WRONG_ANCHOR_TEXT, STATUS_DUPLICATE_LINK,
    STATUS_DUPLICATE_SUBDOMAIN, STATUS_MISSING, STATUS_WRONG_TARGET,
)

FAMILIES_MAP = {"pdf": "Aspose.PDF", "slides": "Aspose.Slides"}
PLATFORMS_MAP = {"cpp": "C++", "python": "Python"}


def _target_map() -> dict:
    return {
        "targets": {
            "kb.aspose.com": {
                "families": {
                    "pdf": {"url": "https://kb.aspose.com/pdf/", "http_status": 200},
                },
                "platforms": {
                    "pdf/cpp": {"url": "https://kb.aspose.com/pdf/cpp/", "http_status": 200},
                },
            },
        },
        "all_urls": {},
    }


def _write_kb_page(tmp_path: Path, rel_path: str, body: str) -> Path:
    fp = tmp_path / rel_path
    fp.parent.mkdir(parents=True, exist_ok=True)
    fp.write_text(f"---\ntitle: Test\n---\n\n{body}\n", encoding="utf-8")
    return fp


class TestAuditFileWrongAnchorText:
    def test_correct_url_wrong_anchor_detected(self, tmp_path):
        fp = _write_kb_page(
            tmp_path, "content/kb.aspose.org/en/pdf/cpp/faq.md",
            "## See Also\n\n- [Some wrong wording here](https://kb.aspose.com/pdf/cpp/)\n",
        )
        rec = audit_file(
            fp, tmp_path, _target_map(),
            families_map=FAMILIES_MAP, platforms_map=PLATFORMS_MAP,
        )
        assert rec.status == STATUS_WRONG_ANCHOR_TEXT

    def test_correct_url_correct_anchor_is_compliant(self, tmp_path):
        fp = _write_kb_page(
            tmp_path, "content/kb.aspose.org/en/pdf/cpp/faq.md",
            "## See Also\n\n- [Aspose.PDF for C++ — Enterprise Knowledge Base](https://kb.aspose.com/pdf/cpp/)\n",
        )
        rec = audit_file(
            fp, tmp_path, _target_map(),
            families_map=FAMILIES_MAP, platforms_map=PLATFORMS_MAP,
        )
        assert rec.status == STATUS_COMPLIANT

    def test_omitting_display_maps_disables_anchor_check_backward_compatible(self, tmp_path):
        """Negative control: the pre-TC14 call shape (no families_map/
        platforms_map) must not crash and must not attempt WRONG_ANCHOR_TEXT
        detection -- a wrong-wording page falls back to plain COMPLIANT,
        exactly as it did before this fix."""
        fp = _write_kb_page(
            tmp_path, "content/kb.aspose.org/en/pdf/cpp/faq.md",
            "## See Also\n\n- [Some wrong wording here](https://kb.aspose.com/pdf/cpp/)\n",
        )
        rec = audit_file(fp, tmp_path, _target_map())
        assert rec.status == STATUS_COMPLIANT


class TestAuditFileDuplicates:
    def test_duplicate_link_detected(self, tmp_path):
        """Reproduces the confirmed-live kb.aspose.org/pdf/cpp defect class
        (64 pages, TC4's original finding) -- audit_file() must now surface
        it as DUPLICATE_LINK instead of silently passing as COMPLIANT."""
        fp = _write_kb_page(
            tmp_path, "content/kb.aspose.org/en/pdf/cpp/faq.md",
            "## See Also\n\n"
            "- [Aspose.PDF — Enterprise Knowledge Base](https://kb.aspose.com/pdf/)\n"
            "- [Aspose.PDF for C++ — Enterprise Knowledge Base](https://kb.aspose.com/pdf/cpp/)\n",
        )
        rec = audit_file(fp, tmp_path, _target_map())
        assert rec.status == STATUS_DUPLICATE_LINK

    def test_duplicate_subdomain_detected(self, tmp_path):
        fp = _write_kb_page(
            tmp_path, "content/kb.aspose.org/en/pdf/cpp/faq.md",
            "## See Also\n\n"
            "- [Aspose.PDF for C++ — Enterprise Knowledge Base](https://kb.aspose.com/pdf/cpp/)\n"
            "- [Some unrelated page](https://kb.aspose.com/slides/)\n",
        )
        rec = audit_file(fp, tmp_path, _target_map())
        assert rec.status == STATUS_DUPLICATE_SUBDOMAIN

    def test_real_live_kb_pdf_cpp_duplicate_case(self):
        """End-to-end against the REAL repo content and target map. This page
        was TC4's original live DUPLICATE_LINK example (a family bullet never
        removed when a platform bullet was appended); TC15 Stage 2's
        kb.aspose.org backfill (commit 0385b0e781, 2026-08-24) healed it to a
        single correct link, so it now must audit COMPLIANT. Kept as a live
        regression guard against the fix reverting -- test_duplicate_link_detected
        above is the constructed-fixture coverage for the detection logic
        itself and stays independent of live content state."""
        from lib.backlink_targets import load_target_map
        repo_root = Path(__file__).resolve().parents[3]
        target_map = load_target_map(repo_root)
        fp = repo_root / "content/kb.aspose.org/en/pdf/cpp/_index.md"
        if not fp.is_file():
            import pytest
            pytest.skip("live fixture page not present in this checkout")
        rec = audit_file(fp, repo_root, target_map)
        assert rec.status == STATUS_COMPLIANT


class TestAuditFileDeepAuthorityWiring:
    """BL-AUDIT-DEEP-WIRE (2026-08-24): the CLI's --deep/--authority flags
    were parsed but never threaded into audit_file()'s resolve_backlink()
    call, so any reference.aspose.org page correctly deep-linked to its
    exact class URL (via backlink_backfill.py --deep, or pre-existing) was
    misclassified WRONG_TARGET -- confirmed live: 471 of 497 WRONG_TARGET
    results on a post-backfill reference.aspose.org audit were pages just
    written with a correct, deliberate deep link."""

    def _authority(self, source_file: str, target_path: str) -> dict:
        return {
            "authority": {
                source_file: {
                    "allowed_for_generation": True,
                    "target_subdomain": "reference",
                    "target_path": target_path,
                },
            },
        }

    def test_deep_link_wrong_target_without_wiring_baseline(self, tmp_path):
        """Baseline reproducing the bug: omitting exact_deep_match_enabled/
        authority (the pre-fix call shape) resolves only the shallow family
        target, so a page correctly holding the deep class URL and nothing
        else audits WRONG_TARGET."""
        fp = _write_kb_page(
            tmp_path, "content/reference.aspose.org/en/3d/java/EntityRendererFeatures.md",
            "## See Also\n\n"
            "- [Aspose.3D for Java — Enterprise API Reference]"
            "(https://reference.aspose.com/3d/java/com.aspose.threed/entityrendererfeatures/)\n",
        )
        target_map = {
            "targets": {
                "reference.aspose.com": {
                    "families": {"3d": {"url": "https://reference.aspose.com/3d/", "http_status": 200}},
                    "platforms": {"3d/java": {"url": "https://reference.aspose.com/3d/java/", "http_status": 200}},
                },
            },
            "all_urls": {},
        }
        rec = audit_file(fp, tmp_path, target_map)
        assert rec.status == STATUS_WRONG_TARGET

    def test_deep_link_compliant_when_wired(self, tmp_path):
        """With exact_deep_match_enabled=True and a matching authority
        record, the same page must audit COMPLIANT -- proving the CLI's
        --deep flag now actually reaches resolve_backlink()."""
        rel = "content/reference.aspose.org/en/3d/java/EntityRendererFeatures.md"
        fp = _write_kb_page(
            tmp_path, rel,
            "## See Also\n\n"
            "- [Aspose.3D for Java — Enterprise API Reference]"
            "(https://reference.aspose.com/3d/java/com.aspose.threed/entityrendererfeatures/)\n",
        )
        target_map = {"targets": {}, "all_urls": {}}
        authority = self._authority(
            rel, "3d/java/com.aspose.threed/entityrendererfeatures",
        )
        rec = audit_file(
            fp, tmp_path, target_map,
            exact_deep_match_enabled=True, authority=authority,
        )
        assert rec.status == STATUS_COMPLIANT

    def test_omitting_deep_params_preserves_prior_behavior(self, tmp_path):
        """Negative control: omitting exact_deep_match_enabled/authority
        (the default call shape used by every other existing caller) must
        behave exactly as before this fix -- shallow resolution only, even
        when an authority record exists that COULD have matched."""
        rel = "content/reference.aspose.org/en/3d/java/EntityRendererFeatures.md"
        fp = _write_kb_page(
            tmp_path, rel,
            "## See Also\n\n"
            "- [Aspose.3D for Java — Enterprise API Reference]"
            "(https://reference.aspose.com/3d/java/com.aspose.threed/entityrendererfeatures/)\n",
        )
        target_map = {
            "targets": {
                "reference.aspose.com": {
                    "families": {"3d": {"url": "https://reference.aspose.com/3d/", "http_status": 200}},
                    "platforms": {"3d/java": {"url": "https://reference.aspose.com/3d/java/", "http_status": 200}},
                },
            },
            "all_urls": {},
        }
        rec = audit_file(fp, tmp_path, target_map)
        assert rec.status == STATUS_WRONG_TARGET


class TestRunAuditTallying:
    def test_totals_include_new_statuses(self, tmp_path):
        _write_kb_page(
            tmp_path, "content/kb.aspose.org/en/pdf/cpp/dup.md",
            "## See Also\n\n"
            "- [Aspose.PDF — Enterprise Knowledge Base](https://kb.aspose.com/pdf/)\n"
            "- [Aspose.PDF for C++ — Enterprise Knowledge Base](https://kb.aspose.com/pdf/cpp/)\n",
        )
        _write_kb_page(
            tmp_path, "content/kb.aspose.org/en/pdf/cpp/wrong-anchor.md",
            "## See Also\n\n- [wrong wording](https://kb.aspose.com/pdf/cpp/)\n",
        )
        records, totals = run_audit(tmp_path, _target_map(), subdomains=["kb.aspose.org"])
        assert totals.duplicate_link == 1
        assert totals.wrong_anchor_text == 1

    def test_build_report_counters_include_new_fields(self, tmp_path):
        _write_kb_page(
            tmp_path, "content/kb.aspose.org/en/pdf/cpp/dup.md",
            "## See Also\n\n"
            "- [Aspose.PDF — Enterprise Knowledge Base](https://kb.aspose.com/pdf/)\n"
            "- [Aspose.PDF for C++ — Enterprise Knowledge Base](https://kb.aspose.com/pdf/cpp/)\n",
        )
        records, totals = run_audit(tmp_path, _target_map(), subdomains=["kb.aspose.org"])
        report = build_report(records, totals, "test-hash")
        assert report["totals"]["duplicate_link"] == 1
        assert report["by_subdomain"]["kb.aspose.org"]["duplicate_link"] == 1
        assert report["by_family"]["pdf"]["duplicate_link"] == 1
        assert len(report["duplicates"]) == 1
        assert report["duplicates"][0]["file"] == "content/kb.aspose.org/en/pdf/cpp/dup.md"

    def test_missing_still_works_unaffected(self, tmp_path):
        """Regression control: a page with zero qualifying links must still
        classify MISSING -- new detection logic must not interfere with
        existing statuses."""
        _write_kb_page(
            tmp_path, "content/kb.aspose.org/en/pdf/cpp/empty.md",
            "No links here at all.",
        )
        records, totals = run_audit(tmp_path, _target_map(), subdomains=["kb.aspose.org"])
        assert totals.missing == 1
        assert records[0].status == STATUS_MISSING
