"""Integration tests for gap-eval page-level detection (TEST-03).

Exercises load_site_plan, expected_pages_from_plan, and stage7_missing_sections
from scripts/gap-eval/src/run.py using tmp_path fixtures only.
No real content/ or reports/plans/ paths are touched.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest
import yaml

# ---------------------------------------------------------------------------
# Module loader — avoids sys.path pollution and module-level side effects
# ---------------------------------------------------------------------------

def _load_run():
    spec = importlib.util.spec_from_file_location(
        "gap_eval_run",
        Path(__file__).parents[3] / "scripts" / "gap-eval" / "src" / "run.py",
    )
    m = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(m)
    except SystemExit:
        pass  # module-level sys.exit from missing env — ignore
    return m


ge = _load_run()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _minimal_plan(pages_by_section: dict) -> dict:
    """Build a minimal wrapped site_plan dict."""
    sections = {}
    for site_key, page_list in pages_by_section.items():
        sections[site_key] = {"page_count": len(page_list), "pages": page_list}
    return {"plan": {"family": "3d", "platform": "python", "sections": sections}}


def _flat_plan(pages_by_section: dict) -> dict:
    """Build a legacy flat (non-wrapped) site_plan dict."""
    sections = {}
    for site_key, page_list in pages_by_section.items():
        sections[site_key] = {"page_count": len(page_list), "pages": page_list}
    return {"family": "3d", "platform": "python", "sections": sections}


def _dummy_make_id(family, platform, finding_type, file, line, extra=""):
    return f"{family}-{platform}-{finding_type}-{abs(hash(file)) % 100000}"


# ---------------------------------------------------------------------------
# TEST-03-A: expected_pages_from_plan — wrapped format
# ---------------------------------------------------------------------------

def test_expected_pages_from_plan_structure():
    """Given a wrapped plan with 2 docs pages, function returns those 2 paths."""
    plan = _minimal_plan({
        "docs": [
            {"slug": "getting-started/installation", "path": "content/docs.aspose.org/en/3d/python/getting-started/installation.md", "mandatory": True},
            {"slug": "developer-guide/features",     "path": "content/docs.aspose.org/en/3d/python/developer-guide/features.md",     "mandatory": True},
        ]
    })
    result = ge.expected_pages_from_plan(plan)
    assert "docs" in result
    assert len(result["docs"]) == 2
    assert "content/docs.aspose.org/en/3d/python/getting-started/installation.md" in result["docs"]
    assert "content/docs.aspose.org/en/3d/python/developer-guide/features.md" in result["docs"]


# ---------------------------------------------------------------------------
# TEST-03-B: expected_pages_from_plan — legacy flat format (backward compat)
# ---------------------------------------------------------------------------

def test_expected_pages_from_plan_flat_format():
    """Backward-compat: flat (non-wrapped) plan is also handled correctly."""
    plan = _flat_plan({
        "kb": [
            {"slug": "faq", "path": "content/kb.aspose.org/en/3d/python/faq.md", "mandatory": True},
        ]
    })
    result = ge.expected_pages_from_plan(plan)
    assert "kb" in result
    assert "content/kb.aspose.org/en/3d/python/faq.md" in result["kb"]


# ---------------------------------------------------------------------------
# TEST-03-C: expected_pages_from_plan — empty section
# ---------------------------------------------------------------------------

def test_expected_pages_from_plan_empty():
    """A section with no pages returns no paths for that section."""
    plan = _minimal_plan({"docs": [], "kb": []})
    result = ge.expected_pages_from_plan(plan)
    # Empty page lists produce no keys in result
    assert "docs" not in result
    assert "kb" not in result


# ---------------------------------------------------------------------------
# TEST-03-D: stage7 — missing page produces finding
# ---------------------------------------------------------------------------

def test_missing_page_finding(tmp_path):
    """A page in the plan that doesn't exist on disk produces a missing-page finding."""
    # Write plan with 3 expected docs pages
    plan_dir = tmp_path / "reports" / "plans" / "3d" / "python"
    plan_dir.mkdir(parents=True)
    page_paths = [
        "content/docs.aspose.org/en/3d/python/getting-started/installation.md",
        "content/docs.aspose.org/en/3d/python/developer-guide/features.md",
        "content/docs.aspose.org/en/3d/python/developer-guide/scene-management.md",
    ]
    plan = _minimal_plan({
        "docs": [
            {"slug": p.split("/")[-1].replace(".md", ""), "path": p, "mandatory": True}
            for p in page_paths
        ]
    })
    (plan_dir / "site_plan.yaml").write_text(yaml.dump(plan), encoding="utf-8")

    # Create only 2 of the 3 pages on disk
    for p in page_paths[:2]:
        abs_p = tmp_path / p
        abs_p.parent.mkdir(parents=True, exist_ok=True)
        abs_p.write_text("---\ntitle: test\n---\n", encoding="utf-8")
    # page_paths[2] is intentionally absent

    findings = ge.stage7_missing_sections(
        "3d", "python",
        content_files={},
        profile={},
        make_id_fn=_dummy_make_id,
        repo_root=tmp_path,
    )

    missing_page_findings = [f for f in findings if f["type"] == "missing-page"]
    assert len(missing_page_findings) == 1, (
        f"Expected 1 missing-page finding, got {len(missing_page_findings)}: "
        f"{[f['file'] for f in missing_page_findings]}"
    )
    assert missing_page_findings[0]["file"] == page_paths[2]
    assert missing_page_findings[0]["wave"] == 3


# ---------------------------------------------------------------------------
# TEST-03-E: stage7 — all pages present → no missing-page findings
# ---------------------------------------------------------------------------

def test_present_page_no_finding(tmp_path):
    """When all planned pages exist on disk, no missing-page findings are produced."""
    plan_dir = tmp_path / "reports" / "plans" / "3d" / "python"
    plan_dir.mkdir(parents=True)
    page_paths = [
        "content/docs.aspose.org/en/3d/python/getting-started/installation.md",
        "content/docs.aspose.org/en/3d/python/developer-guide/features.md",
    ]
    plan = _minimal_plan({
        "docs": [
            {"slug": p.split("/")[-1].replace(".md", ""), "path": p, "mandatory": True}
            for p in page_paths
        ]
    })
    (plan_dir / "site_plan.yaml").write_text(yaml.dump(plan), encoding="utf-8")

    # Create ALL pages
    for p in page_paths:
        abs_p = tmp_path / p
        abs_p.parent.mkdir(parents=True, exist_ok=True)
        abs_p.write_text("---\ntitle: test\n---\n", encoding="utf-8")

    findings = ge.stage7_missing_sections(
        "3d", "python",
        content_files={},
        profile={},
        make_id_fn=_dummy_make_id,
        repo_root=tmp_path,
    )

    missing_page_findings = [f for f in findings if f["type"] == "missing-page"]
    assert len(missing_page_findings) == 0, (
        f"No missing-page findings expected; got: {[f['file'] for f in missing_page_findings]}"
    )


# ---------------------------------------------------------------------------
# TEST-03-F: stage7 — no site_plan.yaml → falls through without crashing
# ---------------------------------------------------------------------------

def test_fallback_without_plan(tmp_path):
    """When no site_plan.yaml exists, stage7 falls through without crashing."""
    # No plan file written; no profile set up → should return empty or section-level findings
    findings = ge.stage7_missing_sections(
        "3d", "python",
        content_files={},
        profile={"expected_sections": []},  # empty profile — no mandatory sections
        make_id_fn=_dummy_make_id,
        repo_root=tmp_path,
    )
    # Should not raise; result is a list (possibly empty)
    assert isinstance(findings, list)
    # Must not contain missing-page findings (no plan was present)
    assert not any(f.get("type") == "missing-page" for f in findings)


# ---------------------------------------------------------------------------
# TEST-03-G: finding schema — required fields present
# ---------------------------------------------------------------------------

def test_missing_page_finding_schema(tmp_path):
    """Each missing-page finding must carry the required schema fields."""
    plan_dir = tmp_path / "reports" / "plans" / "3d" / "python"
    plan_dir.mkdir(parents=True)
    page_path = "content/docs.aspose.org/en/3d/python/getting-started/installation.md"
    plan = _minimal_plan({
        "docs": [{"slug": "installation", "path": page_path, "mandatory": True}]
    })
    (plan_dir / "site_plan.yaml").write_text(yaml.dump(plan), encoding="utf-8")
    # Do NOT create the page — it should be flagged as missing

    findings = ge.stage7_missing_sections(
        "3d", "python",
        content_files={},
        profile={},
        make_id_fn=_dummy_make_id,
        repo_root=tmp_path,
    )

    missing = [f for f in findings if f["type"] == "missing-page"]
    assert missing, "Expected at least one missing-page finding"

    required_fields = {"id", "type", "severity", "file", "wave", "mandatory"}
    for field in required_fields:
        assert field in missing[0], f"Finding missing required field: {field!r}"

    assert missing[0]["type"] == "missing-page"
    assert missing[0]["wave"] == 3
    assert missing[0]["severity"] in ("low", "medium", "high")
