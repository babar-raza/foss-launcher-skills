"""Tests for scout_fidelity.py — the Extraction Fidelity Gate (D-2, TC-MT040-41).

Covers all five probes (P1-P5) with fixture-based NEGATIVE CONTROLS: a
synthetic TypeScript package (built fresh per-test under tmp_path, mirroring
the shape of scripts/pipeline/tests/fixtures/ts_flat_package/ but with a
deliberately richer doc-comment set — see _write_ts_fixture()'s docstring
for why) paired with a hand-built "BAD" api_surface.json/snippets_index.json
that reproduces the exact real defect this mission found in
knowledge/3d/typescript (an absent `abstract_class_declaration` entry, zero
captured doc comments, zero example-tier snippets) to prove each probe
actually flags it, and a "GOOD" counterpart that proves no false positive
when the same source is captured correctly.

Two independent roots must be redirected for these tests:
  - scout_fidelity._REPO_ROOT (knowledge/ reads, report writes) via
    scout_fidelity.configure(repo_root=...) — the module's own test seam.
  - the clone cache clone_path() resolves to, via the ASPOSE_CLONE_CACHE
    environment variable — core/clone_cache.py's own documented override
    mechanism (AGENTS.md §11), set with pytest's monkeypatch.setenv (an
    env-var override, not an internal monkeypatch of module attributes/
    functions — distinct from the T1/T2 patterns check_monkeypatch_lint.py
    bans).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_PIPELINE_DIR = Path(__file__).resolve().parent.parent
if str(_PIPELINE_DIR) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_DIR))

import scout_fidelity  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_repo_root():
    yield
    scout_fidelity.configure(repo_root=None)


# ---------------------------------------------------------------------------
# Fixture builders
# ---------------------------------------------------------------------------

_DOCUMENT_TS = """/**
 * Abstract base for all documents.
 */
export abstract class Base {
  /**
   * Load a document from a path.
   */
  abstract load(path: string): void;
}

/**
 * A documented, concrete class.
 */
export class Documented extends Base {
  /**
   * Load implementation.
   */
  load(path: string): void {}

  /**
   * Save implementation.
   */
  save(path: string): void {}
}

export class Undocumented extends Base {
  load(path: string): void {}
}
"""

_INDEX_TS = "export { Base, Documented, Undocumented } from './document.js';\n"

_EXAMPLE_TS = """import { Documented } from '../src/index.js';

export function basicExample(): void {
  const doc = new Documented();
  doc.load('sample.pdf');
}
"""

_TEST_TS = """import { Documented } from '../src/index.js';

describe('Documented', () => {
  it('loads', () => {
    const doc = new Documented();
    doc.load('sample.pdf');
  });
});
"""

_README_MD = """# fake-fixture

## Supported Formats

- docx
- pdf

## Usage

```ts
import { Documented } from '@asposefoss/fake-fixture';
const doc = new Documented();
doc.load('sample.pdf');
```
"""

_PACKAGE_JSON = {
    "name": "@asposefoss/fake-fixture",
    "version": "0.1.0",
    "type": "module",
    "main": "dist/index.js",
    "keywords": ["pdf", "docx"],
}


def _write_ts_fixture(clone_dir: Path, *, with_examples: bool = True) -> None:
    """Build a small synthetic TypeScript clone under *clone_dir*.

    Source declarations (all under src/, matching detect_package_root's
    fallback to src/ when package.json's declared `main` doesn't exist on
    disk — same convention as tests/fixtures/ts_flat_package/):
      - Base            (export abstract class, doc'd, + doc'd abstract method)
      - Documented       (export class extends Base, doc'd, 2 doc'd methods)
      - Undocumented     (export class extends Base, no doc, 1 undoc'd method)
    That is 5 real doc comments in source (Base, Base.load, Documented,
    Documented.load, Documented.save) — deliberately >=
    scout_fidelity.P3_MIN_SOURCE_DOC_COUNT (5) so the P3 "meaningful sample"
    gate is actually exercised by this fixture, not skipped as too small.
    """
    src = clone_dir / "src"
    src.mkdir(parents=True, exist_ok=True)
    (src / "index.ts").write_text(_INDEX_TS, encoding="utf-8")
    (src / "document.ts").write_text(_DOCUMENT_TS, encoding="utf-8")
    (clone_dir / "package.json").write_text(json.dumps(_PACKAGE_JSON, indent=2), encoding="utf-8")
    (clone_dir / "README.md").write_text(_README_MD, encoding="utf-8")
    if with_examples:
        examples = clone_dir / "examples"
        examples.mkdir(parents=True, exist_ok=True)
        (examples / "basic.ts").write_text(_EXAMPLE_TS, encoding="utf-8")
    test_dir = clone_dir / "test"
    test_dir.mkdir(parents=True, exist_ok=True)
    (test_dir / "document.test.ts").write_text(_TEST_TS, encoding="utf-8")


def _good_api_surface_entries() -> list:
    """Everything a correctly-hardened scout would capture."""
    return [
        {
            "name": "Base", "kind": "abstract_class_declaration",
            "doc": "Abstract base for all documents.", "reachable": True,
            "methods": [{"name": "load", "doc": "Load a document from a path."}],
        },
        {
            "name": "Documented", "kind": "class_declaration",
            "doc": "A documented, concrete class.", "reachable": True,
            "methods": [
                {"name": "load", "doc": "Load implementation."},
                {"name": "save", "doc": "Save implementation."},
            ],
        },
        {
            "name": "Undocumented", "kind": "class_declaration",
            "doc": "", "reachable": True,
            "methods": [{"name": "load", "doc": ""}],
        },
    ]


def _bad_api_surface_entries() -> list:
    """Reproduces the real pre-TC-MT040-10/12 defect shape: the abstract
    class is entirely absent (no entry under any kind) and every captured
    doc field is empty — exactly knowledge/3d/typescript/merged/
    api_surface.json's real, currently-tracked state (162/162 entries,
    0 abstract_class_declaration, 0/162 non-empty `doc`)."""
    return [
        {
            "name": "Documented", "kind": "class_declaration",
            "doc": "", "reachable": True,
            "methods": [
                {"name": "load", "doc": ""},
                {"name": "save", "doc": ""},
            ],
        },
        {
            "name": "Undocumented", "kind": "class_declaration",
            "doc": "", "reachable": True,
            "methods": [{"name": "load", "doc": ""}],
        },
    ]


def _write_knowledge(
    repo_root: Path, family: str, platform: str, *,
    api_surface: list, formats: "list | None" = None, snippets: "list | None" = None,
) -> None:
    merged = repo_root / "knowledge" / family / platform / "merged"
    merged.mkdir(parents=True, exist_ok=True)
    (merged / "api_surface.json").write_text(json.dumps(api_surface, indent=2), encoding="utf-8")
    (merged / "formats.json").write_text(json.dumps(formats or [], indent=2), encoding="utf-8")
    snip_dir = merged / "snippets"
    snip_dir.mkdir(parents=True, exist_ok=True)
    (snip_dir / "snippets_index.json").write_text(json.dumps(snippets or [], indent=2), encoding="utf-8")


def _setup_product(
    tmp_path: Path, monkeypatch, *, family="fake", platform="typescript",
    api_surface: list, formats: "list | None" = None, snippets: "list | None" = None,
    with_clone: bool = True, with_examples: bool = True,
) -> None:
    scout_fidelity.configure(repo_root=tmp_path)
    _write_knowledge(tmp_path, family, platform, api_surface=api_surface, formats=formats, snippets=snippets)
    clone_root = tmp_path / "clone_cache"
    monkeypatch.setenv("ASPOSE_CLONE_CACHE", str(clone_root))
    if with_clone:
        clone_dir = clone_root / f"aspose_{family}_{platform}"
        _write_ts_fixture(clone_dir, with_examples=with_examples)


def _good_snippets() -> list:
    return [
        {"source_file": "test/document.test.ts", "source_function": "Documented", "id": "snippet_001"},
        {"source_file": "examples/basic.ts", "source_function": "basicExample", "id": "snippet_002"},
        {"source_file": "README.md", "source_function": "(readme_block)", "id": "snippet_003"},
    ]


def _bad_snippets_all_tests() -> list:
    """100/100-from-tests shape, real 3d/typescript defect (G-TS-04)."""
    return [
        {"source_file": "test/document.test.ts", "source_function": f"case{i}", "id": f"snippet_{i:03d}"}
        for i in range(1, 6)
    ]


# ---------------------------------------------------------------------------
# P1 — declaration census
# ---------------------------------------------------------------------------

class TestP1DeclarationCensus:
    def test_unavailable_without_clone_cache(self, tmp_path, monkeypatch):
        _setup_product(tmp_path, monkeypatch, api_surface=_good_api_surface_entries(), with_clone=False)
        result = scout_fidelity.probe_p1_declaration_census("fake", "typescript")
        assert result["status"] == "UNAVAILABLE"
        assert result["would_fail_if_enabled"] is False

    def test_ok_when_all_class_kinds_captured(self, tmp_path, monkeypatch):
        _setup_product(tmp_path, monkeypatch, api_surface=_good_api_surface_entries())
        result = scout_fidelity.probe_p1_declaration_census("fake", "typescript")
        assert result["status"] == "OK", result["message"]
        assert result["would_fail_if_enabled"] is False
        assert result["details"]["per_kind"]["abstract_class_declaration"]["missing_count"] == 0

    def test_negative_control_flags_hidden_abstract_class(self, tmp_path, monkeypatch):
        """The exact TC-MT040-10 shape: Base is a real `export abstract
        class` in source but has NO entry (of any kind) in api_surface.json
        — P1 must flag it as missing under abstract_class_declaration."""
        _setup_product(tmp_path, monkeypatch, api_surface=_bad_api_surface_entries())
        result = scout_fidelity.probe_p1_declaration_census("fake", "typescript")
        assert result["status"] == "WARN"
        assert result["would_fail_if_enabled"] is True
        per_kind = result["details"]["per_kind"]
        assert "Base" in per_kind["abstract_class_declaration"]["missing_names"]
        assert per_kind["abstract_class_declaration"]["missing_count"] == 1

    def test_never_fails_today_regardless_of_finding(self, tmp_path, monkeypatch):
        """Decision 13: advisory-only until calibration enables a probe."""
        assert scout_fidelity.PROBE_FAIL_ENABLED["P1"] is False
        _setup_product(tmp_path, monkeypatch, api_surface=_bad_api_surface_entries())
        result = scout_fidelity.probe_p1_declaration_census("fake", "typescript")
        assert result["status"] != "FAIL"


# ---------------------------------------------------------------------------
# P2 — entry-point coverage
# ---------------------------------------------------------------------------

class TestP2EntryPointCoverage:
    def test_ok_when_barrel_exports_all_present_and_reachable(self, tmp_path, monkeypatch):
        _setup_product(tmp_path, monkeypatch, api_surface=_good_api_surface_entries())
        result = scout_fidelity.probe_p2_entry_point_coverage("fake", "typescript")
        assert result["status"] == "OK", result["message"]
        assert result["details"]["export_count"] == 3  # Base, Documented, Undocumented

    def test_negative_control_flags_hidden_abstract_class(self, tmp_path, monkeypatch):
        _setup_product(tmp_path, monkeypatch, api_surface=_bad_api_surface_entries())
        result = scout_fidelity.probe_p2_entry_point_coverage("fake", "typescript")
        assert result["status"] == "WARN"
        assert result["would_fail_if_enabled"] is True
        assert "Base" in result["details"]["missing_from_api_surface"]

    def test_flags_exported_but_marked_unreachable_inconsistency(self, tmp_path, monkeypatch):
        entries = _good_api_surface_entries()
        for e in entries:
            if e["name"] == "Documented":
                e["reachable"] = False  # barrel exports it, but scout marked it unreachable
        _setup_product(tmp_path, monkeypatch, api_surface=entries)
        result = scout_fidelity.probe_p2_entry_point_coverage("fake", "typescript")
        assert result["status"] == "WARN"
        assert "Documented" in result["details"]["exported_but_marked_unreachable"]

    def test_unavailable_when_barrel_cannot_be_resolved(self, tmp_path, monkeypatch):
        """No src/index.ts at all -> entry point unresolvable -> fail-safe
        UNAVAILABLE, never a false 'everything missing' finding."""
        scout_fidelity.configure(repo_root=tmp_path)
        _write_knowledge(tmp_path, "fake", "typescript", api_surface=_good_api_surface_entries())
        clone_root = tmp_path / "clone_cache"
        monkeypatch.setenv("ASPOSE_CLONE_CACHE", str(clone_root))
        clone_dir = clone_root / "aspose_fake_typescript"
        clone_dir.mkdir(parents=True)
        (clone_dir / "package.json").write_text(json.dumps({"name": "x"}), encoding="utf-8")
        result = scout_fidelity.probe_p2_entry_point_coverage("fake", "typescript")
        assert result["status"] == "UNAVAILABLE"
        assert result["would_fail_if_enabled"] is False


class TestP2CsharpPolarity:
    """csharp's export_surface() returns a CONFIRMED-INTERNAL denylist, the
    opposite polarity from every other language — this must not be treated
    as a positive allowlist (which would silently invert every finding)."""

    def _write_csharp_fixture(self, clone_dir: Path) -> None:
        clone_dir.mkdir(parents=True, exist_ok=True)
        (clone_dir / "Fake.csproj").write_text(
            "<Project Sdk=\"Microsoft.NET.Sdk\"></Project>", encoding="utf-8")
        (clone_dir / "Public.cs").write_text(
            "namespace Fake {\n"
            "  public class PublicThing {\n"
            "    public void Do() {}\n"
            "  }\n"
            "  internal class InternalThing {\n"
            "    public void Do() {}\n"
            "  }\n"
            "}\n",
            encoding="utf-8",
        )

    def test_flags_internal_name_not_marked_unreachable(self, tmp_path, monkeypatch):
        scout_fidelity.configure(repo_root=tmp_path)
        entries = [
            {"name": "PublicThing", "kind": "class_declaration", "doc": "", "reachable": True},
            # BAD: InternalThing is confirmed `internal` in source but scout
            # never marked it reachable:false.
            {"name": "InternalThing", "kind": "class_declaration", "doc": "", "reachable": True},
        ]
        _write_knowledge(tmp_path, "fake", "net", api_surface=entries)
        clone_root = tmp_path / "clone_cache"
        monkeypatch.setenv("ASPOSE_CLONE_CACHE", str(clone_root))
        self._write_csharp_fixture(clone_root / "aspose_fake_net")
        result = scout_fidelity.probe_p2_entry_point_coverage("fake", "net")
        if result["status"] == "UNAVAILABLE":
            pytest.skip(f"csharp export_surface adapter could not resolve this fixture: {result['message']}")
        assert result["details"]["polarity"] == "internal_denylist"
        assert "InternalThing" in result["details"]["internal_but_not_marked_unreachable"]
        assert result["would_fail_if_enabled"] is True

    def test_ok_when_internal_name_correctly_marked_unreachable(self, tmp_path, monkeypatch):
        scout_fidelity.configure(repo_root=tmp_path)
        entries = [
            {"name": "PublicThing", "kind": "class_declaration", "doc": "", "reachable": True},
            {"name": "InternalThing", "kind": "class_declaration", "doc": "", "reachable": False},
        ]
        _write_knowledge(tmp_path, "fake", "net", api_surface=entries)
        clone_root = tmp_path / "clone_cache"
        monkeypatch.setenv("ASPOSE_CLONE_CACHE", str(clone_root))
        self._write_csharp_fixture(clone_root / "aspose_fake_net")
        result = scout_fidelity.probe_p2_entry_point_coverage("fake", "net")
        if result["status"] == "UNAVAILABLE":
            pytest.skip(f"csharp export_surface adapter could not resolve this fixture: {result['message']}")
        assert result["status"] == "OK", result["message"]


# ---------------------------------------------------------------------------
# P3 — doc-comment census
# ---------------------------------------------------------------------------

class TestP3DocCommentCensus:
    def test_ok_when_docs_captured(self, tmp_path, monkeypatch):
        _setup_product(tmp_path, monkeypatch, api_surface=_good_api_surface_entries())
        result = scout_fidelity.probe_p3_doc_comment_census("fake", "typescript")
        assert result["status"] == "OK", result["message"]
        assert result["details"]["source_doc_count"] == 5
        assert result["details"]["api_doc_count"] == 5

    def test_negative_control_flags_hidden_doc_comments(self, tmp_path, monkeypatch):
        """5 real source doc comments (>= P3_MIN_SOURCE_DOC_COUNT), 0
        captured — the real 3d/typescript shape (0/162 docs captured).

        ST-224/TC-TSGAP-09 (2026-09-24): P3 graduated to FAIL-enabled after a
        fleet-wide recalibration over 33 products found 0 would_fail_if_enabled
        -- the first probe to clear the zero-false-positive bar. This
        negative control must now assert FAIL, not WARN; would_fail_if_enabled
        stays true regardless (it reports what WOULD happen if disabled, per
        its own field name)."""
        _setup_product(tmp_path, monkeypatch, api_surface=_bad_api_surface_entries())
        result = scout_fidelity.probe_p3_doc_comment_census("fake", "typescript")
        assert result["status"] == "FAIL"
        assert result["would_fail_if_enabled"] is True
        assert result["details"]["source_doc_count"] == 5
        assert result["details"]["api_doc_count"] == 0

    def test_below_threshold_sample_never_flags(self, tmp_path, monkeypatch):
        """A product with too few source doc comments to be a meaningful
        sample must not alarm on a single missed doc — see
        P3_MIN_SOURCE_DOC_COUNT's own reasoning comment."""
        clone_dir_name = "aspose_tiny_typescript"
        scout_fidelity.configure(repo_root=tmp_path)
        src = tmp_path / "clone_cache" / clone_dir_name / "src"
        src.mkdir(parents=True)
        (src / "index.ts").write_text("export { Thing } from './thing.js';\n", encoding="utf-8")
        (src / "thing.ts").write_text(
            "/**\n * One documented thing.\n */\nexport class Thing {}\n", encoding="utf-8")
        (tmp_path / "clone_cache" / clone_dir_name / "package.json").write_text(
            json.dumps({"name": "x", "main": "dist/index.js"}), encoding="utf-8")
        monkeypatch.setenv("ASPOSE_CLONE_CACHE", str(tmp_path / "clone_cache"))
        _write_knowledge(tmp_path, "tiny", "typescript",
                          api_surface=[{"name": "Thing", "kind": "class_declaration", "doc": ""}])
        result = scout_fidelity.probe_p3_doc_comment_census("tiny", "typescript")
        assert result["details"]["source_doc_count"] == 1
        assert result["status"] == "OK"
        assert result["would_fail_if_enabled"] is False


# ---------------------------------------------------------------------------
# P4 — README/manifest format cross-check
# ---------------------------------------------------------------------------

class TestP4ReadmeManifestFormatCrosscheck:
    def test_ok_when_named_formats_present(self, tmp_path, monkeypatch):
        _setup_product(
            tmp_path, monkeypatch, api_surface=_good_api_surface_entries(),
            formats=[{"format": "docx"}, {"format": "pdf"}],
        )
        result = scout_fidelity.probe_p4_readme_manifest_format_crosscheck("fake", "typescript")
        assert result["status"] == "OK", result["message"]
        assert result["would_fail_if_enabled"] is False

    def test_warns_on_named_misses_never_fails(self, tmp_path, monkeypatch):
        """README's 'Supported Formats' section and package.json keywords
        both name docx/pdf; formats.json is empty (0 entries) — WARN with
        both tokens named, and P4 has no FAIL path at all (unlike P1/P2/P3/
        P5) even in principle."""
        _setup_product(tmp_path, monkeypatch, api_surface=_good_api_surface_entries(), formats=[])
        result = scout_fidelity.probe_p4_readme_manifest_format_crosscheck("fake", "typescript")
        assert result["status"] == "WARN"
        assert result["would_fail_if_enabled"] is False
        assert "docx" in result["details"]["named_misses"]
        assert "pdf" in result["details"]["named_misses"]
        assert "docx" in result["details"]["manifest_tokens"]


# ---------------------------------------------------------------------------
# P5 — snippet provenance
# ---------------------------------------------------------------------------

class TestP5SnippetProvenance:
    def test_ok_when_examples_and_readme_represented(self, tmp_path, monkeypatch):
        _setup_product(tmp_path, monkeypatch, api_surface=_good_api_surface_entries(), snippets=_good_snippets())
        result = scout_fidelity.probe_p5_snippet_provenance("fake", "typescript")
        assert result["status"] == "OK", result["message"]
        assert result["details"]["confidence"] == "disk_confirmed"

    def test_negative_control_flags_hidden_example_snippets(self, tmp_path, monkeypatch):
        """Exact G-TS-04 shape: examples/ has a real .ts file on disk, but
        every collected snippet came from test/ — must FAIL-shaped-flag."""
        _setup_product(tmp_path, monkeypatch, api_surface=_good_api_surface_entries(),
                        snippets=_bad_snippets_all_tests())
        result = scout_fidelity.probe_p5_snippet_provenance("fake", "typescript")
        assert result["status"] == "WARN"
        assert result["would_fail_if_enabled"] is True
        assert result["details"]["confidence"] == "disk_confirmed"
        assert any("examples" in f for f in result["details"]["findings"])

    def test_index_only_mode_without_clone_cache(self, tmp_path, monkeypatch):
        _setup_product(tmp_path, monkeypatch, api_surface=_good_api_surface_entries(),
                        snippets=_bad_snippets_all_tests(), with_clone=False)
        result = scout_fidelity.probe_p5_snippet_provenance("fake", "typescript")
        assert result["details"]["confidence"] == "index_only"
        assert result["would_fail_if_enabled"] is False  # index-only never claims a confirmed finding
        assert result["status"] == "WARN"  # still surfaces the suspicious shape

    def test_skip_when_no_snippets_at_all(self, tmp_path, monkeypatch):
        _setup_product(tmp_path, monkeypatch, api_surface=_good_api_surface_entries(), snippets=[])
        result = scout_fidelity.probe_p5_snippet_provenance("fake", "typescript")
        assert result["status"] == "SKIP"


# ---------------------------------------------------------------------------
# Real-repo regression proof: knowledge/3d/typescript's TRACKED (committed)
# api_surface.json was the actual pre-TC-MT040-10/12 output. Two of the three
# tests originally here — test_zero_abstract_class_declarations_in_tracked_api_surface
# and test_p5_flags_real_tracked_snippet_distribution — were retired 2026-09-10
# (ST-193): 3d/typescript was re-scouted/re-promoted 2026-08-31 (commit 1ace625a02)
# and its tracked artifacts now correctly show 8 abstract_class_declaration entries
# (verified against real upstream source) and a 9/91 README/tests snippet split, so
# the pre-fix defect shape they pinned no longer reproduces — exactly as their own
# assertion messages anticipated. Durable regression coverage for both defect
# classes lives in the synthetic-fixture tests instead (TestP1DeclarationCensus::
# test_negative_control_flags_hidden_abstract_class above, and the P5
# synthetic-fixture tests above), which don't depend on 3d/typescript's own data
# drifting over time the way these two did.
# ---------------------------------------------------------------------------

class TestRealTrackedThreeDTypescriptEvidence:
    def test_zero_docs_captured_in_tracked_api_surface(self):
        real_root = scout_fidelity._DEFAULT_REPO_ROOT
        path = real_root / "knowledge" / "3d" / "typescript" / "merged" / "api_surface.json"
        if not path.is_file():
            pytest.skip("knowledge/3d/typescript/merged/api_surface.json not present in this checkout")
        entries = json.loads(path.read_text(encoding="utf-8"))
        with_doc = sum(1 for e in entries if e.get("doc"))
        assert with_doc == 0, (
            "3d/typescript's tracked api_surface.json now HAS captured doc comments -- "
            "the pre-fix defect this test pins no longer reproduces from the tracked tree"
        )


# ---------------------------------------------------------------------------
# Orchestration: run_probes(), write_fidelity_report(), update_scout_report_summary()
# ---------------------------------------------------------------------------

class TestRunProbesOrchestration:
    def test_overall_status_ok_when_nothing_found(self, tmp_path, monkeypatch):
        _setup_product(tmp_path, monkeypatch, api_surface=_good_api_surface_entries(),
                        formats=[{"format": "docx"}, {"format": "pdf"}], snippets=_good_snippets())
        report = scout_fidelity.run_probes("fake", "typescript")
        assert report["overall_status"] == "OK"
        assert report["findings_count"] == 0
        assert report["fail_count"] == 0

    def test_overall_status_fail_when_p3_finding_present(self, tmp_path, monkeypatch):
        """ST-224/TC-TSGAP-09 (2026-09-24): P3 graduated to FAIL-enabled, so
        this fixture (which trips P3's doc-comment census) now produces a
        real FAIL, not just an advisory WARN. Renamed from
        test_overall_status_warn_when_findings_present, which this fixture's
        outcome no longer matches."""
        _setup_product(tmp_path, monkeypatch, api_surface=_bad_api_surface_entries())
        report = scout_fidelity.run_probes("fake", "typescript")
        assert report["overall_status"] == "FAIL"
        assert report["findings_count"] > 0
        assert report["fail_count"] == 1  # P3 only; P1/P2/P4 still WARN-only

    def test_write_fidelity_report_writes_expected_path(self, tmp_path, monkeypatch):
        _setup_product(tmp_path, monkeypatch, api_surface=_good_api_surface_entries())
        report = scout_fidelity.run_probes("fake", "typescript")
        out_path = scout_fidelity.write_fidelity_report(report, "fake", "typescript")
        assert out_path == tmp_path / "knowledge" / "fake" / "typescript" / "scout" / "fidelity_report.json"
        assert out_path.is_file()
        reloaded = json.loads(out_path.read_text(encoding="utf-8"))
        assert reloaded["family"] == "fake"

    def test_update_scout_report_summary_noop_without_existing_report(self, tmp_path, monkeypatch):
        _setup_product(tmp_path, monkeypatch, api_surface=_good_api_surface_entries())
        report = scout_fidelity.run_probes("fake", "typescript")
        updated = scout_fidelity.update_scout_report_summary("fake", "typescript", report)
        assert updated is False

    def test_update_scout_report_summary_merges_additively(self, tmp_path, monkeypatch):
        _setup_product(tmp_path, monkeypatch, api_surface=_good_api_surface_entries())
        scout_dir = tmp_path / "knowledge" / "fake" / "typescript" / "scout"
        scout_dir.mkdir(parents=True)
        (scout_dir / "scout_report.json").write_text(
            json.dumps({"files_attempted": 3, "files_parsed": 3}), encoding="utf-8")
        report = scout_fidelity.run_probes("fake", "typescript")
        updated = scout_fidelity.update_scout_report_summary("fake", "typescript", report)
        assert updated is True
        merged = json.loads((scout_dir / "scout_report.json").read_text(encoding="utf-8"))
        assert merged["files_attempted"] == 3  # untouched
        assert merged["fidelity_summary"]["overall_status"] == report["overall_status"]


# ---------------------------------------------------------------------------
# Calibration (--calibrate): read-only, aggregate evidence file only
# ---------------------------------------------------------------------------

class TestRunCalibration:
    def test_calibration_is_read_only_and_writes_one_evidence_file(self, tmp_path, monkeypatch):
        scout_fidelity.configure(repo_root=tmp_path)
        _write_knowledge(tmp_path, "fake", "typescript", api_surface=_bad_api_surface_entries())
        _write_knowledge(tmp_path, "other", "python", api_surface=_good_api_surface_entries())
        monkeypatch.setenv("ASPOSE_CLONE_CACHE", str(tmp_path / "clone_cache"))  # empty -> no clones anywhere

        products_file = tmp_path / "products.json"
        products_file.write_text(json.dumps([
            {"family": "fake", "platform": "typescript"},
            {"family": "other", "platform": "python"},
        ]), encoding="utf-8")

        out_path = tmp_path / "evidence" / "fidelity_calibration.json"
        result = scout_fidelity.run_calibration(products_file=products_file, output_path=out_path)

        assert result["product_count"] == 2
        assert out_path.is_file()
        # Read-only: no per-product fidelity_report.json/scout_report.json written.
        assert not (tmp_path / "knowledge" / "fake" / "typescript" / "scout" / "fidelity_report.json").exists()
        assert not (tmp_path / "knowledge" / "other" / "python" / "scout" / "fidelity_report.json").exists()
        for pid in ("P1", "P2", "P3", "P4", "P5"):
            assert pid in result["probe_status_distribution"]


# ---------------------------------------------------------------------------
# Small helper unit tests
# ---------------------------------------------------------------------------

class TestTierClassification:
    def test_readme_block(self):
        assert scout_fidelity._classify_snippet_tier(
            {"source_file": "README.md", "source_function": "(readme_block)"}) == "tier0_readme"

    def test_examples_dir(self):
        assert scout_fidelity._classify_snippet_tier(
            {"source_file": "examples/feature-showcase/forms.ts", "source_function": "x"}) == "tier1_examples"

    def test_test_dir(self):
        assert scout_fidelity._classify_snippet_tier(
            {"source_file": "test/document.test.ts", "source_function": "x"}) == "tier2_tests"

    def test_other(self):
        assert scout_fidelity._classify_snippet_tier(
            {"source_file": "src/document.ts", "source_function": "x"}) == "other"


class TestStatusForNeverFailsByDefault:
    def test_p3_enabled_others_still_disabled_for_fail(self):
        """Renamed from test_all_probes_disabled_for_fail_by_default
        (ST-224/TC-TSGAP-09, 2026-09-24): P3 is now the first probe to
        graduate to FAIL-enabled, per a fleet-wide recalibration finding 0
        would_fail_if_enabled across all 33 products with a clone cache.
        P1/P2/P4/P5 remain WARN-only -- their own calibration runs still show
        real would-be false positives (P1: 6/33, P2: 13/33, P5: 21/33) or are
        WARN-only by design (P4)."""
        assert scout_fidelity.PROBE_FAIL_ENABLED == {
            "P1": False, "P2": False, "P3": True, "P4": False, "P5": False,
        }

    def test_status_for_returns_warn_not_fail_when_disabled(self):
        assert scout_fidelity._status_for(True, "P1") == "WARN"

    def test_status_for_respects_the_sanctioned_switch_when_flipped(self):
        """PROBE_FAIL_ENABLED is the module's own declared config surface
        (see its module-level docstring) -- toggling it in a test proves the
        wiring works without touching any internal function/path constant."""
        assert scout_fidelity.PROBE_FAIL_ENABLED["P1"] is False
        scout_fidelity.PROBE_FAIL_ENABLED["P1"] = True
        try:
            assert scout_fidelity._status_for(True, "P1") == "FAIL"
        finally:
            scout_fidelity.PROBE_FAIL_ENABLED["P1"] = False


class TestCliMain:
    def test_main_exits_nonzero_on_fail(self, tmp_path, monkeypatch, capsys):
        """Renamed from test_main_exits_zero_on_warn (ST-224/TC-TSGAP-09,
        2026-09-24): this fixture trips P3's doc-comment census, which is
        now FAIL-enabled -- main() must exit 1, matching its own
        `return 1 if report["overall_status"] == "FAIL" else 0` contract."""
        _setup_product(tmp_path, monkeypatch, api_surface=_bad_api_surface_entries())
        rc = scout_fidelity.main(["fake", "typescript", "--repo-root", str(tmp_path)])
        assert rc == 1

    def test_main_requires_family_and_platform_without_calibrate(self, tmp_path):
        with pytest.raises(SystemExit):
            scout_fidelity.main(["--repo-root", str(tmp_path)])
