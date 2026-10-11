"""Byte-parity golden tests for the extraction/lang/ adapter refactor (TC-MT040-42).

Purpose (this file's entire reason for existing): prove the python.py and
rust.py adapter relocation in extraction/api_surface.py did not change
python/rust extraction output in ANY way, not even a single field. This is
the one hard rule for TC-MT040-42 -- "Do NOT modify `reachable` semantics or
output for python/rust in any way a golden test would catch."

The golden JSON fixtures under tests/fixtures/extraction_goldens/ were
captured by running the real, PRE-refactor extract_api_surface() (loaded
standalone from `git show HEAD` at the commit immediately before this card's
changes, c8e92b66bf) against:
  - tests/fixtures/rust_crate/ (the existing fixture crate already used by
    test_rust_extraction.py)
  - tests/fixtures/python_pkg/ (a new fixture package created for this card,
    modeled on the real words/python namespace-parent layout: the outer
    __init__.py is empty, the real __all__ lives one level down in
    aspose_core/__init__.py -- this exercises _python_top_level_exports'/
    lang.python.top_level_exports' subdirectory-fallback branch, not just
    the common top-level-__all__ case already covered elsewhere)

These are REAL committed goldens (static JSON files), not a live
re-derivation -- a live re-derivation using the same (now-refactored) code
under test could never catch a regression in that code, which defeats the
entire purpose of this file.

This file only asserts full `classes` list equality (the object RC-W1-004
attaches `reachable`/`doc` to, and everything else _extract_doc_comment /
_compute_reachable / doc_anchor / export_surface can affect) plus
`packages` and the completeness `report` -- run through the CURRENT
(post-refactor) extract_api_surface() against the identical fixtures.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from extraction.api_surface import extract_api_surface  # noqa: E402
from extraction.tree_helpers import get_parser  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures"
GOLDENS = FIXTURES / "extraction_goldens"


def _load_golden(name: str) -> dict:
    with open(GOLDENS / name, encoding="utf-8") as f:
        return json.load(f)


def _run(language: str, pkg_root: Path, repo: Path, family: str) -> dict:
    """Run the CURRENT (post-refactor) extraction and normalize it to the
    same shape/sort-order the golden JSON was captured in."""
    parser = get_parser(language)
    classes, claims, scanned, packages, report = extract_api_surface(
        parser, language, pkg_root, repo, family
    )
    # json round-trip: normalizes tuples -> lists etc. exactly like the
    # golden-capture script's json.dumps(..., default=str) did.
    normalized = json.loads(json.dumps(
        sorted(classes, key=lambda c: (c.get("name", ""), c.get("kind", ""))),
        default=str,
    ))
    return {
        "classes": normalized,
        "packages": sorted(packages),
        "report": json.loads(json.dumps(report, default=str)),
    }


class TestRustGoldenParity:
    """rust_crate/ fixture -- see test_rust_extraction.py for the same
    fixture exercised via many individual assertions; this file instead
    diffs the ENTIRE output against a pre-refactor snapshot."""

    def test_classes_byte_identical(self):
        golden = _load_golden("rust_crate_golden.json")
        rust_fixture = FIXTURES / "rust_crate"
        current = _run("rust", rust_fixture / "src", rust_fixture, "cells")
        assert current["classes"] == golden["classes"]

    def test_packages_identical(self):
        golden = _load_golden("rust_crate_golden.json")
        rust_fixture = FIXTURES / "rust_crate"
        current = _run("rust", rust_fixture / "src", rust_fixture, "cells")
        assert current["packages"] == golden["packages"]

    def test_report_identical(self):
        golden = _load_golden("rust_crate_golden.json")
        rust_fixture = FIXTURES / "rust_crate"
        current = _run("rust", rust_fixture / "src", rust_fixture, "cells")
        assert current["report"] == golden["report"]

    def test_reachable_field_present_and_matches(self):
        """Focused sanity check on exactly the field RC-W1-004/this card's
        refactor is about -- Workbook/FlatType/SaveFormat reachable=True
        (re-exported), everything else reachable=False (internal-only
        crate types, matching the real cells/rust WorkbookModel defect this
        signal exists to catch)."""
        golden = _load_golden("rust_crate_golden.json")
        rust_fixture = FIXTURES / "rust_crate"
        current = _run("rust", rust_fixture / "src", rust_fixture, "cells")
        current_reachable = {c["name"]: c["reachable"] for c in current["classes"]}
        golden_reachable = {c["name"]: c["reachable"] for c in golden["classes"]}
        assert current_reachable == golden_reachable
        assert current_reachable["Workbook"] is True
        assert current_reachable["SheetRef"] is False


class TestPythonGoldenParity:
    """python_pkg/ fixture -- the real words/python namespace-parent layout
    shape (empty outer __init__.py, __all__ one level down)."""

    def test_classes_byte_identical(self):
        golden = _load_golden("python_pkg_golden.json")
        py_fixture = FIXTURES / "python_pkg"
        current = _run("python", py_fixture, py_fixture, "fixture")
        assert current["classes"] == golden["classes"]

    def test_packages_identical(self):
        golden = _load_golden("python_pkg_golden.json")
        py_fixture = FIXTURES / "python_pkg"
        current = _run("python", py_fixture, py_fixture, "fixture")
        assert current["packages"] == golden["packages"]

    def test_report_identical(self):
        golden = _load_golden("python_pkg_golden.json")
        py_fixture = FIXTURES / "python_pkg"
        current = _run("python", py_fixture, py_fixture, "fixture")
        assert current["report"] == golden["report"]

    def test_reachable_field_present_and_matches(self):
        """Document/Writer are in aspose_core's __all__ -> reachable=True;
        UnexportedType/free_function are syntactically public but absent
        from __all__ -> reachable=False (the real words/python
        DocumentReader/LdmDocxWriter defect shape this signal exists to
        catch)."""
        golden = _load_golden("python_pkg_golden.json")
        py_fixture = FIXTURES / "python_pkg"
        current = _run("python", py_fixture, py_fixture, "fixture")
        current_reachable = {c["name"]: c["reachable"] for c in current["classes"]}
        golden_reachable = {c["name"]: c["reachable"] for c in golden["classes"]}
        assert current_reachable == golden_reachable
        assert current_reachable["Document"] is True
        assert current_reachable["Writer"] is True
        assert current_reachable["UnexportedType"] is False
        assert current_reachable["free_function"] is False
