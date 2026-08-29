"""Tests for batch_reference.py's D-4 / TC-MT040-43 consumption of
module_key/module_label -- the knowledge-layer module/topic assignment
promote.py writes onto api_surface.json entries (see
commands/knowledge/promote.py's "Module/topic assignment" section).

Covers:
  - _derive_group_key() reads module_key when present, falls back to the
    existing directory-path logic unchanged when absent.
  - _build_grouped_index_body() uses a group's module_label (when carried
    by its entries) as the rendered heading, falls back to _group_label()
    otherwise.
  - GROUPED_INDEX_GENERATOR_VERSION bump (1 -> 2).
  - A synthetic flat-layout (no directory info at all) fixture with
    keyword-matchable class names produces >= 4 distinct groups through
    the real _derive_group_key()/_build_grouped_index_body() pipeline --
    the concrete regression proof for G-TS-01 (a flat TypeScript repo no
    longer collapses into one "Core API" group).
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import batch_reference as _br
from batch_reference import _derive_group_key, _build_grouped_index_body, _group_label
from commands.knowledge.promote import compute_module_assignment
from lib.reference_filter import GROUPED_INDEX_GENERATOR_VERSION


@pytest.fixture(autouse=True)
def _isolate_paths(tmp_path):
    _br.configure(repo_root=tmp_path)
    yield
    _br.configure()


# ---------------------------------------------------------------------------
# _derive_group_key: module_key precedence + fallback
# ---------------------------------------------------------------------------

class TestDeriveGroupKeyModuleAssignment:
    def test_module_key_used_when_present(self):
        e = {"file": "src/Document.cs", "name": "Document", "module_key": "widgets"}
        # Old .NET directory-path logic alone would return "core" for a
        # root-level src/*.cs file (see TestDeriveGroupKey.test_net_root_cs_file_returns_core
        # in test_batch_reference.py) -- module_key overrides that entirely.
        assert _derive_group_key(e, "pdf", "net") == "widgets"

    def test_falls_back_to_directory_logic_when_module_key_absent(self):
        e = {"file": "src/Annotations/AnnotClass.cs", "name": "AnnotClass"}
        assert _derive_group_key(e, "pdf", "net") == "annotations"

    def test_empty_string_module_key_is_treated_as_absent(self):
        """An explicit empty string is falsy -- must not be treated as a
        real (but empty) group key; falls back to directory logic."""
        e = {"file": "src/Annotations/AnnotClass.cs", "name": "AnnotClass", "module_key": ""}
        assert _derive_group_key(e, "pdf", "net") == "annotations"

    def test_flat_typescript_layout_no_longer_collapses_to_core(self):
        """G-TS-01: before module_key existed, typescript shared the cpp
        branch (needs a {family} directory segment) -- a flat src/ layout
        with no such segment always fell to "core". With module_key
        present this is fixed without touching the fallback branch at
        all."""
        e = {"file": "src/forms.ts", "name": "FormField", "module_key": "forms"}
        assert _derive_group_key(e, "pdf", "typescript") == "forms"


# ---------------------------------------------------------------------------
# _build_grouped_index_body: module_label used as the rendered heading
# ---------------------------------------------------------------------------

class TestBuildGroupedIndexBodyModuleLabel:
    def test_module_label_used_as_heading_when_present(self):
        entries = [
            {"name": "FormField", "file": "src/forms.ts", "kind": "class_declaration",
             "module_key": "forms", "module_label": "PDF Forms",
             "methods": [], "properties": []},
        ]
        body = _build_grouped_index_body(entries, "pdf", "typescript")
        assert "## PDF Forms" in body
        # The generic derivation would have produced "Forms" (Title-Case of
        # the key) -- module_label wins over that fallback.
        assert "## Forms" not in body

    def test_falls_back_to_group_label_when_module_label_absent(self):
        entries = [
            {"name": "AnnotClass", "file": "src/Annotations/AnnotClass.cs", "kind": "class_declaration",
             "methods": [], "properties": []},
        ]
        body = _build_grouped_index_body(entries, "pdf", "net")
        assert f"## {_group_label('annotations', 'pdf', 'net')}" in body

    def test_core_group_label_is_core_api(self):
        entries = [
            {"name": "Widget", "file": "index.ts", "kind": "class_declaration",
             "module_key": "core", "module_label": "Core API",
             "methods": [], "properties": []},
        ]
        body = _build_grouped_index_body(entries, "pdf", "typescript")
        assert "## Core API" in body


# ---------------------------------------------------------------------------
# GROUPED_INDEX_GENERATOR_VERSION bump
# ---------------------------------------------------------------------------

def test_grouped_index_generator_version_bumped_to_2():
    assert GROUPED_INDEX_GENERATOR_VERSION == 2


# ---------------------------------------------------------------------------
# End-to-end: synthetic flat-layout fixture -> >= 4 non-degenerate groups
# ---------------------------------------------------------------------------

class TestFlatLayoutFixtureProducesNonDegenerateGroups:
    """The concrete G-TS-01 regression proof: a flat repo (every file
    directly under src/, no subdirectories at all -- pdf/typescript's real
    shape, ~300 files directly under src/) must not collapse into one
    "Core API" group once promote.py's compute_module_assignment() has run.
    """

    FLAT_API_SURFACE = [
        {"name": "AcroFormField", "file": "src/acroform.ts", "kind": "class_declaration",
         "methods": [], "properties": []},
        {"name": "AnnotationBuilder", "file": "src/annotation.ts", "kind": "class_declaration",
         "methods": [], "properties": []},
        {"name": "DocxExporter", "file": "src/docxexport.ts", "kind": "class_declaration",
         "methods": [], "properties": []},
        {"name": "TableAbsorber", "file": "src/tableabsorber.ts", "kind": "class_declaration",
         "methods": [], "properties": []},
        {"name": "RedactionBuilder", "file": "src/redaction.ts", "kind": "class_declaration",
         "methods": [], "properties": []},
        {"name": "Document", "file": "src/document.ts", "kind": "class_declaration",
         "methods": [], "properties": []},  # no keyword match -> core
    ]

    def test_flat_fixture_yields_at_least_four_groups(self):
        entries = [dict(e) for e in self.FLAT_API_SURFACE]  # don't mutate the class attr
        compute_module_assignment(entries, "pdf", "typescript")

        body = _build_grouped_index_body(entries, "pdf", "typescript")
        import re
        headings = re.findall(r"^## (.+)$", body, re.MULTILINE)
        assert len(headings) >= 4, f"expected >= 4 groups, got {headings}"
        assert "Core API" in headings
        # Each keyword-table hit landed in its own distinct, non-"Core API" group.
        assert {"Forms", "Annotations", "Conversion", "Tables", "Redaction"}.issubset(set(headings))

    def test_flat_fixture_not_degenerate_single_group(self):
        """Direct regression guard for the exact G-TS-01 symptom: without
        module_key, this same flat fixture collapses to one group."""
        entries_without_module_key = [dict(e) for e in self.FLAT_API_SURFACE]
        body = _build_grouped_index_body(entries_without_module_key, "pdf", "typescript")
        import re
        headings = re.findall(r"^## (.+)$", body, re.MULTILINE)
        assert headings == ["Core API"]
