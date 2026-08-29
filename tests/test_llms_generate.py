"""Tests for the llms_generate/coverage/fidelity family (new 2026-08-29 sync).

Exercised against tests/fixtures/generic_hugo_repo/ -- a synthetic, non-Aspose
Hugo content tree (fictional "WidgetKit" product, example.org domains) built
specifically so these tests prove the generalized skills can reason about a
generic Hugo/content repo without any dependency on aspose.org or its
specific site layout. This IS the Phase-4 portability dry-run proof the
sync mission requires.
"""
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE_ROOT = REPO_ROOT / "tests" / "fixtures" / "generic_hugo_repo"
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import llms_common  # noqa: E402
import llms_coverage  # noqa: E402
import llms_fidelity  # noqa: E402
import llms_generate  # noqa: E402

_SITES = {
    "docs": {"content_path": "content/docs.example.org/en/{family}/{platform}/"},
    "blog": {"content_path": "content/blog.example.org/{family}/{platform}/"},
}


# --- llms_common ------------------------------------------------------------

def test_site_base_dir_strips_placeholders():
    assert llms_common.site_base_dir("content/docs.example.org/en/{family}/{platform}/") == \
        "content/docs.example.org/en"


def test_parse_frontmatter_extracts_fields():
    text = "---\ntitle: Hello\ndraft: true\n---\n\n# Body\n"
    fm, body = llms_common.parse_frontmatter(text)
    assert fm == {"title": "Hello", "draft": True}
    assert body.strip() == "# Body"


def test_parse_frontmatter_handles_missing_block():
    fm, body = llms_common.parse_frontmatter("# Just a body\n")
    assert fm == {}
    assert body == "# Just a body\n"


def test_is_eligible_page_excludes_drafts():
    assert llms_common.is_eligible_page({"draft": True}) is False
    assert llms_common.is_eligible_page({"draft": False}) is True
    assert llms_common.is_eligible_page({}) is True


def test_structural_counts_detects_shortcodes_and_evidence_leak():
    counts = llms_common.structural_counts("some text {{< shortcode >}} and claim_id: abc123")
    assert counts["has_shortcode"] is True
    assert counts["has_evidence_field"] is True


# --- llms_generate against the generic fixture -----------------------------

def test_generate_site_excludes_draft_pages(tmp_path):
    written = llms_generate.generate_site(
        FIXTURE_ROOT, tmp_path, "docs", _SITES["docs"]["content_path"]
    )
    rel_paths = {rel for rel, _ in written}
    assert not any("draft-page" in p for p in rel_paths)
    assert len(written) == 2  # getting-started + api-reference, draft excluded


def test_generate_site_writes_header_and_body(tmp_path):
    llms_generate.generate_site(FIXTURE_ROOT, tmp_path, "docs", _SITES["docs"]["content_path"])
    out_file = tmp_path / "docs" / "content" / "docs.example.org" / "en" / "widgetkit" / "python" / "getting-started.txt"
    assert out_file.is_file()
    text = out_file.read_text(encoding="utf-8")
    assert "Title: Getting Started with WidgetKit for Python" in text
    assert "## Installation" in text
    assert "| WGT" in text  # table content preserved


def test_generate_site_writes_index(tmp_path):
    llms_generate.generate_site(FIXTURE_ROOT, tmp_path, "docs", _SITES["docs"]["content_path"])
    index = (tmp_path / "docs" / "llms.txt").read_text(encoding="utf-8")
    assert "2 page(s)" in index
    assert "getting-started" in index


def test_generate_is_idempotent(tmp_path):
    llms_generate.generate_site(FIXTURE_ROOT, tmp_path / "run1", "docs", _SITES["docs"]["content_path"])
    llms_generate.generate_site(FIXTURE_ROOT, tmp_path / "run2", "docs", _SITES["docs"]["content_path"])
    file1 = (tmp_path / "run1" / "docs" / "content" / "docs.example.org" / "en" / "widgetkit" / "python" / "getting-started.txt").read_text()
    file2 = (tmp_path / "run2" / "docs" / "content" / "docs.example.org" / "en" / "widgetkit" / "python" / "getting-started.txt").read_text()
    assert file1 == file2


def test_generate_multiple_sites_no_cross_contamination(tmp_path):
    for site_type, cfg in _SITES.items():
        llms_generate.generate_site(FIXTURE_ROOT, tmp_path, site_type, cfg["content_path"])
    assert (tmp_path / "docs" / "llms.txt").is_file()
    assert (tmp_path / "blog" / "llms.txt").is_file()
    blog_index = (tmp_path / "blog" / "llms.txt").read_text(encoding="utf-8")
    assert "1 page(s)" in blog_index


# --- llms_coverage against the generic fixture ------------------------------

def test_coverage_full_after_generation(tmp_path):
    llms_generate.generate_site(FIXTURE_ROOT, tmp_path, "docs", _SITES["docs"]["content_path"])
    result = llms_coverage.coverage_for_site(FIXTURE_ROOT, tmp_path, "docs", _SITES["docs"]["content_path"])
    assert result["eligible_pages"] == 2
    assert result["covered_pages"] == 2
    assert result["coverage_pct"] == 100.0
    assert result["missing_pages"] == []


def test_coverage_reports_gap_before_generation(tmp_path):
    result = llms_coverage.coverage_for_site(FIXTURE_ROOT, tmp_path, "docs", _SITES["docs"]["content_path"])
    assert result["coverage_pct"] == 0.0
    assert len(result["missing_pages"]) == 2


# --- llms_fidelity against the generic fixture ------------------------------

def test_fidelity_scores_generated_pages_well(tmp_path):
    llms_generate.generate_site(FIXTURE_ROOT, tmp_path, "docs", _SITES["docs"]["content_path"])
    result = llms_fidelity.fidelity_for_site(FIXTURE_ROOT, tmp_path, "docs", _SITES["docs"]["content_path"])
    assert result["status"] == "scored"
    assert result["domain_score"] >= 80.0
    assert result["failing_pages"] == 0


def test_fidelity_negative_control_detects_dropped_section(tmp_path):
    """The auditor must correctly REJECT a false-complete output (mirrors
    source's own 'Negative Control' manual-verification note)."""
    llms_generate.generate_site(FIXTURE_ROOT, tmp_path, "docs", _SITES["docs"]["content_path"])
    out_file = tmp_path / "docs" / "content" / "docs.example.org" / "en" / "widgetkit" / "python" / "getting-started.txt"
    # Truncate the output to drop the ## Installation / ## Quick Example / ## Supported Formats sections.
    out_file.write_text("Site: docs\nTitle: Getting Started with WidgetKit for Python\n\n# Getting Started\n", encoding="utf-8")

    result = llms_fidelity.fidelity_for_site(FIXTURE_ROOT, tmp_path, "docs", _SITES["docs"]["content_path"])
    truncated_page = next(p for p in result["pages"] if "getting-started" in p["page"])
    assert truncated_page["score"] < 80.0
    assert truncated_page["checks"]["h2_count_ok"] is False
    assert truncated_page["checks"]["table_row_count_ok"] is False


def test_fidelity_reports_no_pages_when_nothing_generated(tmp_path):
    result = llms_fidelity.fidelity_for_site(FIXTURE_ROOT, tmp_path, "docs", _SITES["docs"]["content_path"])
    assert result["status"] == "no_pages"


# --- CLI-level end-to-end dry-run proof -------------------------------------

def test_cli_main_generates_against_generic_fixture_repo(tmp_path, monkeypatch):
    """The actual Phase-4 portability proof: invoke llms_generate.main() the
    same way an operator would, pointed ONLY at config.yaml + CONTENT_REPO_PATH
    -- no aspose.org path, no source-repo write access, nothing beyond what
    ships in this fixture. If this passes, the skill can reason about a
    generic Hugo/content repo end to end."""
    import config_loader

    monkeypatch.setenv("CONTENT_REPO_PATH", str(FIXTURE_ROOT))
    monkeypatch.setattr(config_loader, "_find_config", lambda: FIXTURE_ROOT / "config.yaml")

    output_dir = tmp_path / "llms-output"
    exit_code = llms_generate.main(["--output", str(output_dir)])
    assert exit_code == 0
    assert (output_dir / "docs" / "llms.txt").is_file()
    assert (output_dir / "blog" / "llms.txt").is_file()

    exit_code = llms_coverage.main(["--output", str(output_dir), "--gate", "95"])
    assert exit_code == 0

    exit_code = llms_fidelity.main(["--output", str(output_dir), "--gate", "80"])
    assert exit_code == 0


def test_cli_main_fails_closed_without_content_repo_configured(monkeypatch, tmp_path):
    import config_loader

    monkeypatch.delenv("CONTENT_REPO_PATH", raising=False)
    monkeypatch.setattr(config_loader, "_find_config", lambda: tmp_path / "does-not-exist.yaml")
    exit_code = llms_generate.main(["--output", str(tmp_path / "out")])
    assert exit_code == 2
