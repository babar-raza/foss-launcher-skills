"""
Tests for scripts/pipeline/commands/content/locale_refresh_handoff.py (S-107).

Min required: 6 tests. This file has 8.
"""

import pytest
import yaml
from pathlib import Path

import commands.content.locale_refresh_handoff as lrh


# ── Fixtures ──────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def reset_config():
    yield
    lrh.configure(reports_root="reports/refresh_review", content_root="content")


def _make_receipt(receipts_dir: Path, page_path: str, sections: list, verdict: str = "BODY_UPDATED") -> Path:
    """Create a receipt YAML file in receipts_dir."""
    receipts_dir.mkdir(parents=True, exist_ok=True)
    slug = page_path.replace("/", "_").replace("\\", "_").replace(":", "")
    f = receipts_dir / f"{slug}.yaml"
    data = {
        "content_refresh_receipt": {
            "page_path": page_path,
            "new_hash": "sha256:abc123",
            "body_sections_changed": sections,
            "verdict": verdict,
        }
    }
    f.write_text(yaml.dump(data), encoding="utf-8")
    return f


# ── Tests ─────────────────────────────────────────────────────────────────


def test_locale_equivalents_discovered(tmp_path, monkeypatch):
    """Existing locale files are returned for a known en page path."""
    # Create fake locale files under tmp_path
    for locale in ["ar", "de", "fr"]:
        locale_file = tmp_path / "content" / "docs.aspose.org" / locale / "pdf" / "net" / "getting-started" / "index.md"
        locale_file.parent.mkdir(parents=True, exist_ok=True)
        locale_file.write_text("# Test", encoding="utf-8")

    # CWD → tmp_path so relative paths resolve against the temp fixtures
    monkeypatch.chdir(tmp_path)

    en_path = "content/docs.aspose.org/en/pdf/net/getting-started/index.md"
    results = lrh._find_locale_equivalents(en_path, "pdf", "net")
    found_locales = [r[0] for r in results]
    assert "ar" in found_locales
    assert "de" in found_locales
    assert "fr" in found_locales
    assert len(results) == 3


def test_small_change_queued_for_s75(tmp_path):
    """1 section changed → classified as 'small' → S-75 translate_skill."""
    receipt = {
        "page_path": "content/docs.aspose.org/en/pdf/net/index.md",
        "new_hash": "sha256:abc",
        "body_sections_changed": ["installation"],  # 1 section → 2 sentences < 3 → small
        "verdict": "BODY_UPDATED",
    }
    size = lrh._classify_change_size(receipt)
    assert size == "small"

    # Build a handoff entry with no locale files (just check skill assignment)
    entry = lrh._build_handoff_entry(receipt, [("ar", "content/.../ar/...")])
    assert entry["locales_requiring_update"][0]["translate_skill"] == lrh.SKILL_SMALL
    assert entry["locales_requiring_update"][0]["change_size"] == "small"


def test_large_change_queued_for_s56(tmp_path):
    """2+ sections changed → classified as 'large' → S-56 translate_skill."""
    receipt = {
        "page_path": "content/docs.aspose.org/en/pdf/net/index.md",
        "new_hash": "sha256:def",
        "body_sections_changed": ["installation", "usage"],  # 2 sections → 4 sentences >= 3 → large
        "verdict": "BODY_UPDATED",
    }
    size = lrh._classify_change_size(receipt)
    assert size == "large"

    entry = lrh._build_handoff_entry(receipt, [("de", "content/.../de/...")])
    assert entry["locales_requiring_update"][0]["translate_skill"] == lrh.SKILL_LARGE
    assert entry["locales_requiring_update"][0]["change_size"] == "large"


def test_no_locale_pages_produces_empty_handoff(tmp_path):
    """Receipt with no matching locale files produces no handoff entries."""
    receipts_dir = tmp_path / "receipts"
    page_path = "content/docs.aspose.org/en/pdf/net/orphan/index.md"
    _make_receipt(receipts_dir, page_path, ["overview"])

    lrh.configure(reports_root=str(tmp_path / "reports"), content_root=str(tmp_path / "content"))

    # No locale files exist → no entries
    entries = lrh.run("pdf", "net", receipts_dir=str(receipts_dir))
    assert entries == []


def test_only_body_updated_receipts_processed(tmp_path):
    """Only receipts with verdict=BODY_UPDATED are processed; others are ignored."""
    receipts_dir = tmp_path / "receipts"
    page_path = "content/docs.aspose.org/en/pdf/net/skip/index.md"
    _make_receipt(receipts_dir, page_path, ["overview"], verdict="BODY_SKIPPED")

    receipts = lrh._load_receipts(str(receipts_dir))
    assert receipts == [], "BODY_SKIPPED receipt should not be loaded"


def test_handoff_yaml_schema_valid(tmp_path, monkeypatch):
    """run() writes locale_handoff.yaml with correct top-level schema."""
    # CWD → tmp_path so relative paths resolve against temp fixtures
    monkeypatch.chdir(tmp_path)

    # Create a receipt using a relative en page path
    receipts_dir = tmp_path / "receipts"
    page_path = "content/docs.aspose.org/en/pdf/net/gs/index.md"
    _make_receipt(receipts_dir, page_path, ["overview"])

    # Create a matching locale equivalent (relative path resolution via CWD)
    locale_file = tmp_path / "content" / "docs.aspose.org" / "ar" / "pdf" / "net" / "gs" / "index.md"
    locale_file.parent.mkdir(parents=True, exist_ok=True)
    locale_file.write_text("# Arabic", encoding="utf-8")

    lrh.configure(reports_root=str(tmp_path / "reports"), content_root=str(tmp_path / "content"))

    lrh.run("pdf", "net", receipts_dir=str(receipts_dir))

    out_path = tmp_path / "reports" / "pdf" / "net" / "locale_handoff.yaml"
    assert out_path.exists(), "locale_handoff.yaml not written"

    with open(out_path, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    assert "locale_handoff" in data
    entries = data["locale_handoff"]
    assert isinstance(entries, list)
    assert len(entries) >= 1
    entry = entries[0]
    assert "source_page" in entry
    assert "changed_sections" in entry
    assert "locales_requiring_update" in entry
    locale_entry = entry["locales_requiring_update"][0]
    assert "locale" in locale_entry
    assert "path" in locale_entry
    assert "handoff_status" in locale_entry
    assert locale_entry["handoff_status"] == "QUEUED"
    assert "translate_skill" in locale_entry


def test_load_receipts_ignores_malformed_files(tmp_path):
    """Malformed YAML files in receipts dir are silently skipped."""
    receipts_dir = tmp_path / "receipts"
    receipts_dir.mkdir(parents=True)
    (receipts_dir / "bad.yaml").write_text("{{not: valid: yaml:", encoding="utf-8")
    (receipts_dir / "wrong_key.yaml").write_text("other_key: {}", encoding="utf-8")

    receipts = lrh._load_receipts(str(receipts_dir))
    assert receipts == []


def test_build_handoff_entry_schema(tmp_path):
    """_build_handoff_entry returns all required fields with correct types."""
    receipt = {
        "page_path": "content/docs.aspose.org/en/pdf/net/index.md",
        "new_hash": "sha256:xyz",
        "body_sections_changed": ["installation"],
        "verdict": "BODY_UPDATED",
    }
    locale_paths = [("ar", "content/docs.aspose.org/ar/pdf/net/index.md")]
    entry = lrh._build_handoff_entry(receipt, locale_paths)

    assert entry["source_page"] == receipt["page_path"]
    assert entry["source_revision"] == receipt["new_hash"]
    assert entry["changed_sections"] == ["installation"]
    assert len(entry["locales_requiring_update"]) == 1
    lu = entry["locales_requiring_update"][0]
    assert lu["locale"] == "ar"
    assert lu["handoff_status"] == "QUEUED"
    assert lu["translate_skill"] in (lrh.SKILL_SMALL, lrh.SKILL_LARGE)
