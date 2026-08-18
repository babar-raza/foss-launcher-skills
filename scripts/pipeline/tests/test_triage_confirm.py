"""Tests for triage_confirm.py — two-layer body-prose staleness scanner.

Covers TC-201..204 runtime contract:
  TC-201: Layer 2 body-prose detection (removed APIs, modified APIs, slug, removed claims)
  TC-202: Planner delta-awareness (already-reconciled deltas not re-fired as stale)
  TC-203: Reconciliation schema (automated/operator/manual sections, unresolved reporting)
  TC-204: read_error verdict (unreadable page yields read_error, not False)
"""
from __future__ import annotations

import sys
import json
import tempfile
from pathlib import Path

import pytest

_PIPELINE_DIR = Path(__file__).resolve().parent.parent
if str(_PIPELINE_DIR) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_DIR))

from triage_confirm import triage_confirm  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _page(tmp_path: Path, name: str, body: str) -> Path:
    p = tmp_path / name
    p.write_text(body, encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# TC-201: Layer 2 body-prose detection
# ---------------------------------------------------------------------------

class TestLayer2Detection:
    """TC-201: page body prose signals detected correctly."""

    def test_clean_page_not_stale(self, tmp_path):
        page = _page(tmp_path, "Workbook.md", "This page has no stale references.")
        knowledge = {"api_surface": [{"name": "Workbook"}], "delta": {}}
        result = triage_confirm(page, knowledge)
        assert result["stale"] is False
        assert result["reasons"] == []
        assert result["confidence"] == 0.0

    def test_removed_api_in_body_triggers_stale(self, tmp_path):
        page = _page(tmp_path, "Page.md", "Use the OldClass to open workbooks.")
        knowledge = {
            "api_surface": [],
            "delta": {"removed_apis": ["OldClass"]},
        }
        result = triage_confirm(page, knowledge)
        assert result["stale"] is True
        assert any("OldClass" in r for r in result["reasons"])
        assert result["confidence"] >= 0.9

    def test_removed_api_not_in_body_no_signal(self, tmp_path):
        page = _page(tmp_path, "Page.md", "Use the NewClass to open workbooks.")
        knowledge = {
            "api_surface": [],
            "delta": {"removed_apis": ["OldClass"]},
        }
        result = triage_confirm(page, knowledge)
        assert result["stale"] is False

    def test_modified_api_in_body_is_advisory_not_stale(self, tmp_path):
        page = _page(tmp_path, "page.md", "Call ChangedClass.method() to process data.")
        knowledge = {
            "api_surface": [{"name": "ChangedClass"}],
            "delta": {"modified_apis": ["ChangedClass"]},
        }
        result = triage_confirm(page, knowledge)
        assert result["stale"] is False
        assert result["reasons"] == []
        assert any("ChangedClass" in r for r in result["advisories"])
        assert result["confidence"] == 0.0

    def test_missing_member_on_modified_api_is_stale(self, tmp_path):
        page = _page(
            tmp_path,
            "page.md",
            "Call `ChangedClass.removedMethod()` to process data.",
        )
        knowledge = {
            "api_surface": [{
                "name": "ChangedClass",
                "methods": [{"name": "currentMethod"}],
                "properties": [],
            }],
            "delta": {"modified_apis": ["ChangedClass"]},
        }
        result = triage_confirm(page, knowledge)
        assert result["stale"] is True
        assert any("ChangedClass.removedMethod" in reason for reason in result["reasons"])
        assert result["confidence"] >= 0.9

    def test_changed_parameter_signature_on_modified_api_is_stale(self, tmp_path):
        page = _page(
            tmp_path,
            "page.md",
            "Use `ChangedClass.convert(String)` for conversion.",
        )
        knowledge = {
            "api_surface": [{
                "name": "ChangedClass",
                "methods": [{
                    "name": "convert",
                    "params": [{"name": "value", "type": "Stream"}],
                }],
            }],
            "delta": {"modified_apis": ["ChangedClass"]},
        }
        result = triage_confirm(page, knowledge)
        assert result["stale"] is True
        assert any("stale signature" in reason for reason in result["reasons"])

    def test_current_overload_signature_is_not_stale(self, tmp_path):
        page = _page(
            tmp_path,
            "page.md",
            "Use `ChangedClass.convert(Stream)` for conversion.",
        )
        knowledge = {
            "api_surface": [{
                "name": "ChangedClass",
                "methods": [{
                    "name": "convert",
                    "params": [{"name": "value", "type": "Stream"}],
                }],
            }],
            "delta": {"modified_apis": ["ChangedClass"]},
        }
        result = triage_confirm(page, knowledge)
        assert result["stale"] is False

    def test_chained_call_in_same_backtick_span_is_not_falsely_stale(self, tmp_path):
        """Regression test for a confirmed bug: [^`]* inside the captured
        parameter group is greedy across parens, so a CHAINED call in one
        backtick span -- `Document.Form().Field(name)` -- had Form()'s
        "()" swallow everything up to the LAST ")" before the backtick,
        misreading ").Field(name" as Form's claimed argument list. Since
        Form takes zero params, this produced a false "stale signature"
        finding on accurate prose (found live, MT014-2026-07-29-PDF-GO-REDO,
        content/kb.aspose.org/en/pdf/go/faq.md -- Document.Form() truly
        takes no arguments; .Field(name) is a separate, correctly-described
        chained call)."""
        page = _page(
            tmp_path,
            "page.md",
            "Use `Document.Form().Field(name)` and assert the concrete type.",
        )
        knowledge = {
            "api_surface": [{
                "name": "Document",
                "methods": [{"name": "Form", "params": []}],
            }],
            "delta": {"modified_apis": ["Document"]},
        }
        result = triage_confirm(page, knowledge)
        assert result["stale"] is False
        assert result["reasons"] == []

    def test_single_call_signature_still_detected_after_chained_call_fix(self, tmp_path):
        """Negative control: the fix above must not blind the checker to
        real, non-chained signature mismatches."""
        page = _page(
            tmp_path,
            "page.md",
            "Use `Document.Load(String)` to open with options.",
        )
        knowledge = {
            "api_surface": [{
                "name": "Document",
                "methods": [{
                    "name": "Load",
                    "params": [{"name": "value", "type": "Stream"}],
                }],
            }],
            "delta": {"modified_apis": ["Document"]},
        }
        result = triage_confirm(page, knowledge)
        assert result["stale"] is True
        assert any("stale signature" in reason for reason in result["reasons"])

    def test_real_enum_member_is_not_falsely_reported_missing(self, tmp_path):
        """RPR-ST088-01 regression: api_surface.json stores an enum class's
        own members under "enum_members", not "methods"/"properties" --
        the missing-member scan never included that key, so every real,
        current enum member (e.g. SaveFormat.XLSX) was reported as
        "missing" the instant its class was cited via a dotted backtick
        reference. Found live 2026-08-18, cells/python S-84 remediation."""
        page = _page(
            tmp_path,
            "page.md",
            "Save with `SaveFormat.XLSX` for the standard Excel format.",
        )
        knowledge = {
            "api_surface": [{
                "name": "SaveFormat",
                "methods": [],
                "properties": [],
                "enum_members": [
                    {"name": "XLSX", "value": "auto()"},
                    {"name": "CSV", "value": "auto()"},
                ],
            }],
            "delta": {"modified_apis": ["SaveFormat"]},
        }
        result = triage_confirm(page, knowledge)
        assert result["stale"] is False
        assert result["reasons"] == []

    def test_real_missing_enum_member_still_detected(self, tmp_path):
        """Negative control: the enum_members fix above must not blind the
        checker to a genuinely absent enum member."""
        page = _page(
            tmp_path,
            "page.md",
            "Save with `SaveFormat.PDF` for a portable document.",
        )
        knowledge = {
            "api_surface": [{
                "name": "SaveFormat",
                "methods": [],
                "properties": [],
                "enum_members": [
                    {"name": "XLSX", "value": "auto()"},
                    {"name": "CSV", "value": "auto()"},
                ],
            }],
            "delta": {"modified_apis": ["SaveFormat"]},
        }
        result = triage_confirm(page, knowledge)
        assert result["stale"] is True
        assert any("missing member 'SaveFormat.PDF'" in reason for reason in result["reasons"])

    def test_bare_empty_parens_naming_a_real_method_is_not_falsely_stale(self, tmp_path):
        """RPR-ST087-01 regression: `Workbook.save()` in running prose just
        NAMES the method -- it is not a claim that save() takes zero
        arguments. Found live 2026-08-18, cells/python S-84 remediation:
        the real Workbook.save() takes 5 real params, but citing it with
        bare empty parens (completely normal prose style) was flagged as a
        stale signature because the checker treated "()" as an explicit
        zero-arity assertion."""
        page = _page(
            tmp_path,
            "page.md",
            "Call `Workbook.save()` to persist your changes to disk.",
        )
        knowledge = {
            "api_surface": [{
                "name": "Workbook",
                "methods": [{
                    "name": "save",
                    "params": [
                        {"name": "file_path", "type": ""},
                        {"name": "save_format", "type": ""},
                    ],
                }],
            }],
            "delta": {"modified_apis": ["Workbook"]},
        }
        result = triage_confirm(page, knowledge)
        assert result["stale"] is False
        assert result["reasons"] == []

    def test_real_arity_mismatch_with_written_params_still_detected(self, tmp_path):
        """Negative control: the empty-parens fix above must not blind the
        checker to a real signature mismatch when prose DOES write out
        (wrong) params rather than leaving them bare."""
        page = _page(
            tmp_path,
            "page.md",
            "Call `Workbook.save(String)` to persist your changes to disk.",
        )
        knowledge = {
            "api_surface": [{
                "name": "Workbook",
                "methods": [{
                    "name": "save",
                    "params": [{"name": "value", "type": "Stream"}],
                }],
            }],
            "delta": {"modified_apis": ["Workbook"]},
        }
        result = triage_confirm(page, knowledge)
        assert result["stale"] is True
        assert any("stale signature" in reason for reason in result["reasons"])

    def test_duplicate_class_rows_union_members(self, tmp_path):
        page = _page(
            tmp_path,
            "page.md",
            "Use `ChangedClass.first()` and `ChangedClass.second()`.",
        )
        knowledge = {
            "api_surface": [
                {"name": "ChangedClass", "methods": [{"name": "first"}]},
                {"name": "ChangedClass", "methods": [{"name": "second"}]},
            ],
            "delta": {"modified_apis": ["ChangedClass"]},
        }
        result = triage_confirm(page, knowledge)
        assert result["stale"] is False

    def test_frontmatter_api_evidence_is_not_scanned_as_body_prose(self, tmp_path):
        page = _page(
            tmp_path,
            "page.md",
            "---\nevidence:\n  apis: [OldClass]\n---\nCurrent prose has no removed API.",
        )
        knowledge = {
            "api_surface": [{"name": "CurrentClass"}],
            "delta": {"removed_apis": ["OldClass"]},
        }
        result = triage_confirm(page, knowledge)
        assert result["stale"] is False
        assert result["reasons"] == []

    def test_removed_api_in_body_after_frontmatter_still_blocks(self, tmp_path):
        page = _page(
            tmp_path,
            "page.md",
            "---\nevidence:\n  apis: [CurrentClass]\n---\nUse OldClass to process data.",
        )
        knowledge = {
            "api_surface": [{"name": "CurrentClass"}],
            "delta": {"removed_apis": ["OldClass"]},
        }
        result = triage_confirm(page, knowledge)
        assert result["stale"] is True
        assert any("OldClass" in r for r in result["reasons"])

    def test_slug_not_in_api_surface_triggers_stale(self, tmp_path):
        page = _page(tmp_path, "DeletedClass.md", "This class was removed.")
        knowledge = {
            "api_surface": [{"name": "Workbook"}, {"name": "Worksheet"}],
            "delta": {},
        }
        result = triage_confirm(page, knowledge)
        assert result["stale"] is True
        assert any("DeletedClass" in r for r in result["reasons"])
        assert result["confidence"] >= 0.8

    def test_slug_in_api_surface_no_slug_signal(self, tmp_path):
        page = _page(tmp_path, "Workbook.md", "The Workbook class manages workbooks.")
        knowledge = {
            "api_surface": [{"name": "Workbook"}],
            "delta": {},
        }
        result = triage_confirm(page, knowledge)
        # No slug signal; may be stale for other reasons but not this one
        assert not any("slug" in r for r in result["reasons"])

    def test_removed_claim_id_in_body_triggers_stale(self, tmp_path):
        page = _page(tmp_path, "Page.md", "See CLM-cells-001 for details on this feature.")
        knowledge = {
            "api_surface": [],
            "delta": {"removed_claims": ["CLM-cells-001"]},
        }
        result = triage_confirm(page, knowledge)
        assert result["stale"] is True
        assert any("CLM-cells-001" in r for r in result["reasons"])
        assert result["confidence"] >= 0.7

    def test_empty_api_surface_no_slug_check(self, tmp_path):
        """Slug check skipped when api_surface is empty (no false positives)."""
        page = _page(tmp_path, "Workbook.md", "Some content.")
        knowledge = {"api_surface": [], "delta": {}}
        result = triage_confirm(page, knowledge)
        assert not any("slug" in r for r in result["reasons"])

    def test_lowercase_slug_no_slug_check(self, tmp_path):
        """Slug check skipped for lowercase filenames (not class pages)."""
        page = _page(tmp_path, "installation.md", "Install the package.")
        knowledge = {"api_surface": [{"name": "Workbook"}], "delta": {}}
        result = triage_confirm(page, knowledge)
        assert not any("slug" in r for r in result["reasons"])

    def test_multiple_signals_accumulate(self, tmp_path):
        page = _page(tmp_path, "Page.md", "Use OldClass and also CLM-cells-001.")
        knowledge = {
            "api_surface": [],
            "delta": {
                "removed_apis": ["OldClass"],
                "removed_claims": ["CLM-cells-001"],
            },
        }
        result = triage_confirm(page, knowledge)
        assert result["stale"] is True
        assert len(result["reasons"]) >= 2
        assert result["confidence"] >= 0.9  # max of signals

    def test_no_delta_key_no_error(self, tmp_path):
        """Missing delta key handled gracefully (no KeyError)."""
        page = _page(tmp_path, "Page.md", "Content without any stale references.")
        knowledge = {"api_surface": [{"name": "Workbook"}]}
        result = triage_confirm(page, knowledge)
        assert "stale" in result
        assert "reasons" in result
        assert "confidence" in result


# ---------------------------------------------------------------------------
# TC-202: Delta-aware (no re-dispatch of already-reconciled deltas)
# ---------------------------------------------------------------------------

class TestDeltaAwareness:
    """TC-202: empty or absent delta yields no false positives."""

    def test_empty_delta_no_false_positive(self, tmp_path):
        page = _page(tmp_path, "Workbook.md", "The Workbook class manages files.")
        knowledge = {
            "api_surface": [{"name": "Workbook"}],
            "delta": {"removed_apis": [], "modified_apis": [], "removed_claims": []},
        }
        result = triage_confirm(page, knowledge)
        assert result["stale"] is False

    def test_none_delta_no_error(self, tmp_path):
        """None delta coerced to empty dict without error."""
        page = _page(tmp_path, "Workbook.md", "Content.")
        knowledge = {"api_surface": [{"name": "Workbook"}], "delta": None}
        result = triage_confirm(page, knowledge)
        assert "stale" in result

    def test_word_boundary_match_prevents_false_positive(self, tmp_path):
        """'Workbook' in body should not trigger on removed API 'Work'."""
        page = _page(tmp_path, "Page.md", "The Workbook class is stable.")
        knowledge = {
            "api_surface": [{"name": "Workbook"}],
            "delta": {"removed_apis": ["Work"]},
        }
        result = triage_confirm(page, knowledge)
        # "Work" should not match "Workbook" due to word-boundary regex
        removed_hits = [r for r in result["reasons"] if "removed API 'Work'" in r]
        assert removed_hits == [], "Word-boundary match should prevent partial-name false positive"


# ---------------------------------------------------------------------------
# TC-203: Reconciliation schema (stale verdict structure)
# ---------------------------------------------------------------------------

class TestReconciliationSchema:
    """TC-203: return dict always has required keys; verdict is deterministic."""

    def test_return_keys_always_present(self, tmp_path):
        page = _page(tmp_path, "Page.md", "Content.")
        result = triage_confirm(page, {})
        assert "stale" in result
        assert "reasons" in result
        assert "confidence" in result
        assert result["verdict"] == "unknown"

    def test_stale_is_bool(self, tmp_path):
        page = _page(tmp_path, "Page.md", "Content.")
        result = triage_confirm(page, {})
        assert isinstance(result["stale"], bool)

    def test_reasons_is_list(self, tmp_path):
        page = _page(tmp_path, "Page.md", "Content.")
        result = triage_confirm(page, {})
        assert isinstance(result["reasons"], list)

    def test_confidence_is_float_in_range(self, tmp_path):
        page = _page(tmp_path, "Page.md", "Content.")
        result = triage_confirm(page, {"api_surface": [], "delta": {}})
        assert isinstance(result["confidence"], float)
        assert 0.0 <= result["confidence"] <= 1.0

    def test_stale_true_when_reasons_nonempty(self, tmp_path):
        page = _page(tmp_path, "Page.md", "See OldClass for details.")
        result = triage_confirm(
            page,
            {"api_surface": [], "delta": {"removed_apis": ["OldClass"]}},
        )
        if result["reasons"]:
            assert result["stale"] is True
        else:
            assert result["stale"] is False

    def test_confidence_zero_when_not_stale(self, tmp_path):
        # Use lowercase slug so Signal 3 (slug check) is skipped, and no other signals fire
        page = _page(tmp_path, "installation.md", "No stale references here.")
        result = triage_confirm(
            page,
            {"api_surface": [{"name": "Workbook"}], "delta": {}},
        )
        assert result["confidence"] == 0.0


# ---------------------------------------------------------------------------
# TC-204: read_error verdict (unreadable page)
# ---------------------------------------------------------------------------

class TestReadError:
    """TC-204: unreadable page yields read_error verdict, not a false 'current' result."""

    def test_nonexistent_page_yields_read_error(self, tmp_path):
        missing = tmp_path / "does_not_exist.md"
        result = triage_confirm(missing, {})
        assert result.get("verdict") == "read_error"
        assert result["stale"] is False  # unknown, not stale
        assert any("could not read" in r for r in result["reasons"])

    def test_read_error_confidence_zero(self, tmp_path):
        missing = tmp_path / "missing.md"
        result = triage_confirm(missing, {})
        assert result["confidence"] == 0.0

    def test_readable_page_no_read_error(self, tmp_path):
        page = _page(tmp_path, "Page.md", "Content.")
        result = triage_confirm(page, {})
        assert result.get("verdict") != "read_error"
