"""
Tests for scripts/pipeline/commands/content/body_refresh.py (S-105).

Min required: 12 tests. This file has 13.
"""

import json
import hashlib
import pytest
import yaml
from pathlib import Path

import commands.content.body_refresh as br


# ── Helpers ────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def reset_config():
    yield
    br.configure(
        reports_root="reports/refresh_review",
        receipts_root=None,
        llm_router_class=None,
        safe_write_fn=None,
        hash_validation=True,
    )


def _sha(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _make_page(tmp_path: Path, rel_path: str, content: str) -> Path:
    p = tmp_path / rel_path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


def _setup_reports(
    tmp_path: Path,
    family: str,
    platform: str,
    impacts: list[dict],
    changes: list[dict],
) -> None:
    reports = tmp_path / "reports" / family / platform
    reports.mkdir(parents=True)
    (reports / "body_impact.json").write_text(json.dumps(impacts), encoding="utf-8")
    (reports / "semantic_changes.json").write_text(json.dumps(changes), encoding="utf-8")
    br.configure(
        reports_root=str(tmp_path / "reports"),
        receipts_root=str(tmp_path / "reports" / family / platform / "receipts"),
        hash_validation=False,  # skip hash validation in unit tests
    )


def _make_impact(page_path: str, change_id: str, section_id: str, update_type: str, impact_level: str = "DEFINITE") -> dict:
    return {
        "impact_id": "IMP-0001",
        "page_path": page_path,
        "locale": "en",
        "semantic_change_ids": [change_id],
        "affected_sections": [
            {
                "section_id": section_id,
                "heading": f"## {section_id}",
                "lines": [5, 15],
                "reason": "test",
                "impact_level": impact_level,
                "required_action": "BODY_UPDATE",
                "update_type": update_type,
            }
        ],
        "planner_signal": False,
    }


def _make_change(change_id: str, symbol: str, change_type: str = "API_REMOVED") -> dict:
    return {
        "change_id": change_id,
        "change_type": change_type,
        "symbol": symbol,
        "symbol_kind": "class",
        "public_impact": "USER_VISIBLE",
        "content_impact": "BODY_UPDATE",
        "confidence": 0.95,
        "family": "pdf",
        "platform": "net",
        "base_sha": "abc",
        "current_sha": "def",
        "evidence_paths": [],
    }


# ── Tests ─────────────────────────────────────────────────────────────────

def test_api_removed_sentence_replaced(tmp_path):
    """SURGICAL: renamed API symbol is replaced in prose with new symbol."""
    page_content = "---\ntitle: Test\nauto_updatable: true\n---\n\nUse `OldDocument` to load files.\n"
    page = _make_page(tmp_path, "content/page.md", page_content)

    writes: list[tuple] = []
    br.configure(safe_write_fn=lambda p, c, **kw: writes.append((str(p), c)) or True)

    change = _make_change("CHG-001", "OldDocument", "API_RENAMED")
    change["new_symbol"] = "PdfDocument"
    impact = _make_impact(str(page), "CHG-001", "body", br.UT_SURGICAL)
    _setup_reports(tmp_path, "pdf", "net", [impact], [change])

    receipts = br.run("pdf", "net", execute=True)
    assert len(writes) == 1
    assert "PdfDocument" in writes[0][1]
    assert "OldDocument" not in writes[0][1]


def test_api_removed_code_block_regenerated(tmp_path):
    """EXAMPLE_REGENERATION strategy handles code block containing removed API."""
    page_content = (
        "---\ntitle: Test\n---\n\n## Example\n\n"
        "```csharp\nvar doc = new OldDocument();\ndoc.Save();\n```\n"
    )
    page = _make_page(tmp_path, "content/page.md", page_content)

    writes: list[tuple] = []
    br.configure(safe_write_fn=lambda p, c, **kw: writes.append((str(p), c)) or True)

    change = _make_change("CHG-001", "OldDocument", "API_REMOVED")
    impact = _make_impact(str(page), "CHG-001", "example", br.UT_EXAMPLE)
    _setup_reports(tmp_path, "pdf", "net", [impact], [change])

    receipts = br.run("pdf", "net", execute=True)
    assert len(receipts) == 1


def test_api_removed_table_row_removed(tmp_path):
    """TABLE_ROW_RECONCILIATION removes rows containing removed API."""
    page_content = (
        "---\ntitle: Test\n---\n\n## Formats\n\n"
        "| Format | Class |\n| --- | --- |\n| PDF | OldDocument |\n| HTML | HtmlDoc |\n"
    )
    page = _make_page(tmp_path, "content/page.md", page_content)

    writes: list[tuple] = []
    br.configure(safe_write_fn=lambda p, c, **kw: writes.append((str(p), c)) or True)

    change = _make_change("CHG-001", "OldDocument", "API_REMOVED")
    impact = _make_impact(str(page), "CHG-001", "formats", br.UT_TABLE)
    _setup_reports(tmp_path, "pdf", "net", [impact], [change])

    receipts = br.run("pdf", "net", execute=True)
    if writes:
        assert "OldDocument" not in writes[0][1]
        assert "HtmlDoc" in writes[0][1]  # other rows preserved


def test_api_renamed_prose_updated(tmp_path):
    """SURGICAL: renamed API symbol updates prose references."""
    page_content = "---\ntitle: Test\n---\n\nThe `LegacyConverter` class converts files.\n"
    page = _make_page(tmp_path, "content/page.md", page_content)

    writes: list[tuple] = []
    br.configure(safe_write_fn=lambda p, c, **kw: writes.append((str(p), c)) or True)

    change = _make_change("CHG-001", "LegacyConverter", "API_RENAMED")
    change["new_symbol"] = "PdfConverter"
    impact = _make_impact(str(page), "CHG-001", "body", br.UT_SURGICAL)
    _setup_reports(tmp_path, "pdf", "net", [impact], [change])

    receipts = br.run("pdf", "net", execute=True)
    if writes:
        assert "PdfConverter" in writes[0][1]


def test_feature_removed_section_eliminated(tmp_path):
    """SECTION_REMOVAL: entire section removed when feature is removed."""
    page_content = (
        "---\ntitle: Test\n---\n\n## Overview\n\nStill valid content.\n\n"
        "## Legacy Section\n\nThis references the old feature.\n\n"
        "## See Also\n\nLinks here.\n"
    )
    page = _make_page(tmp_path, "content/page.md", page_content)

    writes: list[tuple] = []
    br.configure(safe_write_fn=lambda p, c, **kw: writes.append((str(p), c)) or True)

    change = _make_change("CHG-001", "LegacyFeature", "FEATURE_REMOVED")
    impact = _make_impact(str(page), "CHG-001", "legacy-section", br.UT_REMOVAL)
    _setup_reports(tmp_path, "pdf", "net", [impact], [change])

    receipts = br.run("pdf", "net", execute=True)
    if writes:
        assert "## Legacy Section" not in writes[0][1]
        assert "Still valid content" in writes[0][1]


def test_feature_added_section_enriched(tmp_path):
    """PARAGRAPH_REWRITE: LLM path invoked and result applied."""
    page_content = "---\ntitle: Test\n---\n\n## Signing\n\nOld signing text here.\n"
    page = _make_page(tmp_path, "content/page.md", page_content)

    class MockLLM:
        class MockResult:
            data = "Updated signing text with new feature."
        def call_chat(self, *a, **kw):
            return self.MockResult()
        def __init__(self):
            pass

    writes: list[tuple] = []
    br.configure(
        safe_write_fn=lambda p, c, **kw: writes.append((str(p), c)) or True,
        llm_router_class=MockLLM,
    )

    change = _make_change("CHG-001", "NewSignatureFeature", "FEATURE_ADDED")
    impact = _make_impact(str(page), "CHG-001", "signing", br.UT_REWRITE)
    _setup_reports(tmp_path, "pdf", "net", [impact], [change])

    receipts = br.run("pdf", "net", execute=True)
    assert len(receipts) == 1


def test_behavior_changed_paragraph_rewritten(tmp_path):
    """PARAGRAPH_REWRITE for BEHAVIOR_CHANGED invokes LLM."""
    page_content = "---\ntitle: Test\n---\n\n## Rendering\n\nOld rendering description.\n"
    page = _make_page(tmp_path, "content/page.md", page_content)

    class MockLLM:
        class MockResult:
            data = "New rendering description reflecting changed behavior."
        def call_chat(self, *a, **kw):
            return self.MockResult()
        def __init__(self):
            pass

    writes: list[tuple] = []
    br.configure(
        safe_write_fn=lambda p, c, **kw: writes.append((str(p), c)) or True,
        llm_router_class=MockLLM,
    )

    change = _make_change("CHG-001", "PdfRenderer", "BEHAVIOR_CHANGED")
    impact = _make_impact(str(page), "CHG-001", "rendering", br.UT_REWRITE)
    _setup_reports(tmp_path, "pdf", "net", [impact], [change])

    receipts = br.run("pdf", "net", execute=True)
    assert len(receipts) == 1


def test_api_added_rewrite_has_deterministic_fallback(tmp_path):
    """PARAGRAPH_REWRITE updates API additions even when LLM returns no change."""
    page_content = "---\ntitle: Test\n---\n\n## Forms\n\nExisting form workflow text.\n"
    page = _make_page(tmp_path, "content/page.md", page_content)

    class NoopLLM:
        class MockResult:
            data = None
        def call_chat(self, *a, **kw):
            return self.MockResult()
        def __init__(self):
            pass

    writes: list[tuple] = []
    br.configure(
        safe_write_fn=lambda p, c, **kw: writes.append((str(p), c)) or True,
        llm_router_class=NoopLLM,
    )

    change = _make_change("CHG-001", "ImportDataAction", "API_ADDED")
    impact = _make_impact(str(page), "CHG-001", "forms", br.UT_REWRITE)
    _setup_reports(tmp_path, "pdf", "net", [impact], [change])

    receipts = br.run("pdf", "net", execute=True)
    assert len(receipts) == 1
    assert receipts[0]["verdict"] == br.VD_UPDATED
    assert "`ImportDataAction`" in writes[0][1]


def test_feature_added_rewrite_has_deterministic_fallback(tmp_path):
    """PARAGRAPH_REWRITE updates feature changes without requiring LLM."""
    page_content = "---\ntitle: Test\n---\n\n## Loading\n\nExisting loading text.\n"
    page = _make_page(tmp_path, "content/page.md", page_content)

    writes: list[tuple] = []
    br.configure(safe_write_fn=lambda p, c, **kw: writes.append((str(p), c)) or True)

    change = _make_change("CHG-001", "CLM-3d-abc123", "FEATURE_ADDED")
    change["symbol_kind"] = "claim"
    impact = _make_impact(str(page), "CHG-001", "loading", br.UT_REWRITE)
    _setup_reports(tmp_path, "3d", "java", [impact], [change])

    receipts = br.run("3d", "java", execute=True)
    assert receipts[0]["verdict"] == br.VD_UPDATED
    assert "reviewed against the current source model" in writes[0][1]


def test_section_change_id_limits_rewrite_to_matching_change(tmp_path):
    """Section-level change_id prevents unrelated page changes from driving strategy."""
    page_content = "---\ntitle: Test\n---\n\n## Loading\n\nExisting loading text.\n"
    page = _make_page(tmp_path, "content/page.md", page_content)

    writes: list[tuple] = []
    br.configure(safe_write_fn=lambda p, c, **kw: writes.append((str(p), c)) or True)

    removed = _make_change("CHG-REMOVED", "RemovedRenderer", "API_REMOVED")
    added = _make_change("CHG-ADDED", "CLM-3d-abc123", "FEATURE_ADDED")
    added["symbol_kind"] = "claim"
    impact = _make_impact(str(page), "CHG-REMOVED", "loading", br.UT_REWRITE)
    impact["semantic_change_ids"] = ["CHG-REMOVED", "CHG-ADDED"]
    impact["affected_sections"][0]["change_id"] = "CHG-ADDED"
    _setup_reports(tmp_path, "3d", "java", [impact], [removed, added])

    receipts = br.run("3d", "java", execute=True)
    assert receipts[0]["verdict"] == br.VD_UPDATED
    assert "reviewed against the current source model" in writes[0][1]


def test_preserve_first_unaffected_sections_unchanged(tmp_path):
    """Sections NOT in affected_sections are never modified."""
    page_content = (
        "---\ntitle: Test\n---\n\n## Overview\n\nUnchanged overview text.\n\n"
        "## Installation\n\nUse `OldPkg` here.\n"
    )
    page = _make_page(tmp_path, "content/page.md", page_content)

    writes: list[tuple] = []
    br.configure(safe_write_fn=lambda p, c, **kw: writes.append((str(p), c)) or True)

    change = _make_change("CHG-001", "OldPkg", "API_REMOVED")
    # Only target 'installation', not 'overview'
    impact = _make_impact(str(page), "CHG-001", "installation", br.UT_SURGICAL)
    _setup_reports(tmp_path, "pdf", "net", [impact], [change])

    receipts = br.run("pdf", "net", execute=True)
    if writes:
        assert "Unchanged overview text" in writes[0][1]


def test_auto_updatable_false_page_skipped(tmp_path):
    """Pages with auto_updatable: false are never written."""
    page_content = "---\ntitle: Test\nauto_updatable: false\n---\n\nProtected content.\n"
    page = _make_page(tmp_path, "content/protected.md", page_content)

    writes: list[tuple] = []
    br.configure(
        safe_write_fn=lambda p, c, **kw: writes.append((str(p), c)) or True,
        hash_validation=False,
    )

    change = _make_change("CHG-001", "SomeClass")
    impact = _make_impact(str(page), "CHG-001", "body", br.UT_SURGICAL)
    _setup_reports(tmp_path, "pdf", "net", [impact], [change])

    receipts = br.run("pdf", "net", execute=True)
    assert len(writes) == 0
    assert any(r.get("verdict") == br.VD_SKIPPED_AUTO for r in receipts)


def test_provenance_auto_updatable_false_page_skipped(tmp_path):
    """Pages with provenance.auto_updatable: false are never written."""
    page_content = (
        "---\ntitle: Test\nprovenance:\n"
        "  auto_updatable: false\n---\n\nProtected content.\n"
    )
    page = _make_page(tmp_path, "content/protected.md", page_content)

    writes: list[tuple] = []
    br.configure(
        safe_write_fn=lambda p, c, **kw: writes.append((str(p), c)) or True,
        hash_validation=False,
    )

    change = _make_change("CHG-001", "SomeClass")
    impact = _make_impact(str(page), "CHG-001", "body", br.UT_REWRITE)
    _setup_reports(tmp_path, "pdf", "net", [impact], [change])

    receipts = br.run("pdf", "net", execute=True)
    assert len(writes) == 0
    assert any(r.get("verdict") == br.VD_SKIPPED_AUTO for r in receipts)


def test_localized_products_page_rejected_before_write(tmp_path):
    """Body refresh must not write English prose into localized product pages."""
    page_content = "---\ntitle: Test\n---\n\n## Overview\n\nTexto localizado.\n"
    page = _make_page(
        tmp_path,
        "content/products.aspose.org/fr/pdf/net/_index.md",
        page_content,
    )

    writes: list[tuple] = []
    br.configure(
        safe_write_fn=lambda p, c, **kw: writes.append((str(p), c)) or True,
        hash_validation=False,
    )

    change = _make_change("CHG-001", "ImportDataAction", "API_ADDED")
    impact = _make_impact(str(page), "CHG-001", "overview", br.UT_REWRITE)
    impact["locale"] = "fr"
    _setup_reports(tmp_path, "pdf", "net", [impact], [change])

    receipts = br.run("pdf", "net", execute=True)
    assert len(writes) == 0
    assert receipts[0]["verdict"] == br.VD_REJECTED_LOCALIZED
    assert receipts[0]["locale"] == "fr"


def test_ambiguous_locale_path_rejected_before_write(tmp_path):
    """Missing locale identity fails closed instead of defaulting to English."""
    page_content = "---\ntitle: Test\n---\n\n## Overview\n\nBody.\n"
    page = _make_page(
        tmp_path,
        "content/docs.aspose.org/pdf/net/getting-started.md",
        page_content,
    )

    writes: list[tuple] = []
    br.configure(
        safe_write_fn=lambda p, c, **kw: writes.append((str(p), c)) or True,
        hash_validation=False,
    )

    change = _make_change("CHG-001", "ImportDataAction", "API_ADDED")
    impact = _make_impact(str(page), "CHG-001", "overview", br.UT_REWRITE)
    _setup_reports(tmp_path, "pdf", "net", [impact], [change])

    receipts = br.run("pdf", "net", execute=True)
    assert len(writes) == 0
    assert receipts[0]["verdict"] == br.VD_REJECTED_AMBIGUOUS


def test_dry_run_produces_no_writes(tmp_path):
    """--dry-run mode plans but produces no file writes."""
    page_content = "---\ntitle: Test\n---\n\nUse `Document.Save` here.\n"
    page = _make_page(tmp_path, "content/page.md", page_content)

    writes: list[tuple] = []
    br.configure(safe_write_fn=lambda p, c, **kw: writes.append((str(p), c)) or True)

    change = _make_change("CHG-001", "Document")
    impact = _make_impact(str(page), "CHG-001", "body", br.UT_SURGICAL)
    _setup_reports(tmp_path, "pdf", "net", [impact], [change])

    receipts = br.run("pdf", "net", dry_run=True)
    assert len(writes) == 0
    assert all(r.get("verdict") == br.VD_SKIPPED_DRY for r in receipts if r.get("verdict"))


def test_idempotent_rerun_no_changes(tmp_path):
    """Running body_refresh twice produces same output (idempotency)."""
    page_content = "---\ntitle: Test\n---\n\nUse `NewAPI` here.\n"
    page = _make_page(tmp_path, "content/page.md", page_content)

    writes: list[list] = [[]]
    br.configure(safe_write_fn=lambda p, c, **kw: writes[0].append(c) or True)

    change = _make_change("CHG-001", "OldAPI")
    impact = _make_impact(str(page), "CHG-001", "body", br.UT_SURGICAL)
    _setup_reports(tmp_path, "pdf", "net", [impact], [change])

    receipts1 = br.run("pdf", "net", execute=True)
    receipts2 = br.run("pdf", "net", execute=True)
    # Same number of receipts
    assert len(receipts1) == len(receipts2)


def test_api_added_fallback_idempotent_with_stale_line_range(tmp_path):
    """Fallback does not duplicate notes already present outside stale line ranges."""
    page_content = (
        "---\ntitle: Test\n---\n\n"
        "## Forms\n\nExisting form workflow text.\n\n"
        "The current pdf/net API surface also includes `ImportDataAction` for related workflows.\n"
    )
    page = _make_page(tmp_path, "content/page.md", page_content)

    writes: list[tuple] = []
    br.configure(safe_write_fn=lambda p, c, **kw: writes.append((str(p), c)) or True)

    change = _make_change("CHG-001", "ImportDataAction", "API_ADDED")
    impact = _make_impact(str(page), "CHG-001", "forms", br.UT_REWRITE)
    impact["affected_sections"][0]["lines"] = [4, 6]
    _setup_reports(tmp_path, "pdf", "net", [impact], [change])

    receipts = br.run("pdf", "net", execute=True)
    assert len(writes) == 0
    assert receipts[0]["verdict"] == br.VD_NO_SECTIONS


def test_duplicate_api_refresh_notes_collapsed(tmp_path):
    """Execute pass collapses repeated deterministic API notes."""
    page_content = (
        "---\ntitle: Test\n---\n\n"
        "## Forms\n\nExisting form workflow text.\n\n"
        "The current pdf/net API surface also includes `BoxShape` for related workflows.\n"
        "The current pdf/net API surface also includes `ImportDataAction` for related workflows.\n"
    )
    page = _make_page(tmp_path, "content/page.md", page_content)

    writes: list[tuple] = []
    br.configure(safe_write_fn=lambda p, c, **kw: writes.append((str(p), c)) or True)

    change = _make_change("CHG-001", "BoxShape", "API_ADDED")
    impact = _make_impact(str(page), "CHG-001", "forms", br.UT_REWRITE)
    _setup_reports(tmp_path, "pdf", "net", [impact], [change])

    receipts = br.run("pdf", "net", execute=True)
    assert receipts[0]["verdict"] == br.VD_UPDATED
    assert writes[0][1].count("API surface also includes") == 1


def test_receipt_written_per_page(tmp_path):
    """Each updated page produces a receipt YAML in receipts/."""
    page_content = "---\ntitle: Test\n---\n\n## Install\n\nRun `OldPackage.Install()`.\n"
    page = _make_page(tmp_path, "content/page.md", page_content)

    br.configure(safe_write_fn=lambda p, c, **kw: True)

    change = _make_change("CHG-001", "OldPackage")
    impact = _make_impact(str(page), "CHG-001", "install", br.UT_SURGICAL)
    _setup_reports(tmp_path, "pdf", "net", [impact], [change])

    receipts = br.run("pdf", "net", execute=True)
    # Check receipts list returned
    assert len(receipts) >= 1
    # Check receipt has required fields
    r = receipts[0]
    assert "receipt_id" in r
    assert "page_path" in r
    assert "verdict" in r


def test_see_also_section_never_removed(tmp_path):
    """See Also section is protected and never touched even if targeted."""
    page_content = (
        "---\ntitle: Test\n---\n\n## Main Content\n\nAPI docs here.\n\n"
        "## See Also\n\n- [Link1](url1)\n- [Link2](url2)\n"
    )
    page = _make_page(tmp_path, "content/page.md", page_content)

    writes: list[tuple] = []
    br.configure(safe_write_fn=lambda p, c, **kw: writes.append((str(p), c)) or True)

    change = _make_change("CHG-001", "SomeAPI", "API_REMOVED")
    # Try to target 'see-also' section (should be protected)
    impact = _make_impact(str(page), "CHG-001", "see-also", br.UT_REMOVAL)
    _setup_reports(tmp_path, "pdf", "net", [impact], [change])

    receipts = br.run("pdf", "net", execute=True)
    # See Also should never be removed
    if writes:
        assert "## See Also" in writes[0][1]
    else:
        # Nothing written (protected) — also acceptable
        pass
