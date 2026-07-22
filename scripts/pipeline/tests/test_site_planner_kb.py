"""Tests for site_planner.py plan_kb() — verifies KB pages are generated
for new product launches even when tier == "placeholder".

Bug fix validation: KC-01 removed the `if tier == "placeholder": return []`
guard that silently dropped all KB pages from every new product launch.

These tests confirm:
  - plan_kb() returns KB pages when clusters are eligible, regardless of tier
  - plan_kb() still filters by cluster eligibility thresholds
  - plan_kb() with tier="placeholder" (new launch) produces the same output as
    tier="launched" given identical clusters
"""
import sys
import unittest
from pathlib import Path

# Add scripts/pipeline/ to sys.path for direct invocation (pytest uses conftest.py).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from site_planner import plan_kb


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_cluster(name: str, claim_count: int = 10, api_method_count: int = 5) -> dict:
    """Build a minimal cluster dict for plan_kb()."""
    return {
        "name": name,
        "category": name,
        "slug": name.lower().replace(" ", "-"),
        "claim_count": claim_count,
        "api_method_count": api_method_count,
        "class_names": [],
        "in_limitations": False,
        "claims": [f"CLM-{name}-{i:03d}" for i in range(claim_count)],
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestPlanKbPlaceholderTier(unittest.TestCase):
    """plan_kb() must generate KB pages for new launches (tier='placeholder')."""

    def test_placeholder_tier_generates_kb_pages(self):
        """KC-01 regression test: placeholder tier must NOT return empty list."""
        clusters = [_make_cluster("spreadsheet-management")]
        pages = plan_kb(
            family="cells",
            platform="net",
            clusters=clusters,
            total_claims=50,
            snippet_count=1,
            tier="placeholder",
        )
        self.assertGreater(len(pages), 0,
            "plan_kb() returned empty list for tier='placeholder' — KC-01 regression!")

    def test_placeholder_tier_same_as_launched(self):
        """placeholder and launched tiers should produce the same KB pages for identical input."""
        clusters = [_make_cluster("spreadsheet-management")]
        pages_placeholder = plan_kb(
            family="cells",
            platform="net",
            clusters=clusters,
            total_claims=50,
            snippet_count=1,
            tier="placeholder",
        )
        pages_launched = plan_kb(
            family="cells",
            platform="net",
            clusters=clusters,
            total_claims=50,
            snippet_count=1,
            tier="launched",
        )
        self.assertEqual(
            [p["slug"] for p in pages_placeholder],
            [p["slug"] for p in pages_launched],
            "placeholder and launched tiers produced different KB slugs",
        )

    def test_kb_index_page_always_generated(self):
        """The _index page must always appear in plan_kb output."""
        clusters = [_make_cluster("myfeature")]
        pages = plan_kb(
            family="cells",
            platform="net",
            clusters=clusters,
            total_claims=10,
            snippet_count=0,
            tier="placeholder",
        )
        slugs = [p["slug"] for p in pages]
        self.assertIn("_index", slugs, "KB _index page not generated")

    def test_faq_page_always_generated(self):
        """The FAQ page must always appear in plan_kb output."""
        clusters = [_make_cluster("myfeature")]
        pages = plan_kb(
            family="cells",
            platform="net",
            clusters=clusters,
            total_claims=10,
            snippet_count=0,
            tier="placeholder",
        )
        slugs = [p["slug"] for p in pages]
        faq_slugs = [s for s in slugs if "faq" in s.lower()]
        self.assertTrue(len(faq_slugs) > 0, "FAQ page not generated")

    def test_eligible_cluster_generates_howto(self):
        """A cluster with claim_count >= 3 and api_method_count >= 1 should generate a how-to."""
        clusters = [_make_cluster("spreadsheet-management", claim_count=5, api_method_count=3)]
        pages = plan_kb(
            family="cells",
            platform="net",
            clusters=clusters,
            total_claims=50,
            snippet_count=0,
            tier="placeholder",
        )
        howto_pages = [p for p in pages if p.get("type") == "howto" or "how-to" in p.get("slug", "")]
        self.assertGreater(len(howto_pages), 0,
            "No how-to page generated for eligible cluster")

    def test_ineligible_cluster_below_threshold_skipped(self):
        """A cluster with claim_count < 3 or api_method_count < 1 must not generate a how-to."""
        clusters = [_make_cluster("tiny", claim_count=1, api_method_count=0)]
        pages = plan_kb(
            family="cells",
            platform="net",
            clusters=clusters,
            total_claims=5,
            snippet_count=0,
            tier="placeholder",
        )
        howto_pages = [p for p in pages if "how-to" in p.get("slug", "")]
        self.assertEqual(len(howto_pages), 0,
            "How-to page generated for ineligible cluster (below threshold)")

    def test_empty_clusters_still_generates_index_and_faq(self):
        """Even with no eligible clusters, _index and FAQ should be present."""
        pages = plan_kb(
            family="cells",
            platform="net",
            clusters=[],
            total_claims=0,
            snippet_count=0,
            tier="placeholder",
        )
        self.assertGreater(len(pages), 0, "No pages generated even for _index/FAQ")



class TestKBSlugRegressions(unittest.TestCase):
    """Regression tests for KB slug defects D-1 and D-2.

    D-1 (TC-KBS-001): C# namespace "JavascriptExtensions" must produce
    hyphenated label "javascript-extensions", not the opaque token
    "javascriptextensions". Root cause: CamelCase leaked into slug.

    D-2 (TC-KBS-003): Cluster "text-extraction" with verb "extract" must
    produce noun "text", not "text-extraction" (verb-noun duplication).
    Root cause: _VERB_NOMINAL_FORMS["extract"] = ["extraction"] strips the
    nominal suffix, but the content file predated the fix.
    """

    # ------------------------------------------------------------------
    # D-1 unit tests — TC-KBS-001 (_subpkg_to_label CamelCase fix)
    # ------------------------------------------------------------------

    def test_subpkg_to_label_javascript_extensions_pascal_case(self):
        """TC-KBS-001: PascalCase 'JavascriptExtensions' -> 'javascript-extensions'."""
        from site_planner import _subpkg_to_label
        result = _subpkg_to_label("JavascriptExtensions", "pdf")
        self.assertEqual(
            result,
            "javascript-extensions",
            f"TC-KBS-001 regression: expected 'javascript-extensions', got {result!r}. "
            "CamelCase C# namespace must be split into kebab-case.",
        )

    def test_subpkg_to_label_javascript_extensions_lowercase(self):
        """TC-KBS-001: All-lowercase 'javascriptextensions' also maps via explicit override."""
        from site_planner import _subpkg_to_label
        result = _subpkg_to_label("javascriptextensions", "pdf")
        self.assertEqual(
            result,
            "javascript-extensions",
            f"TC-KBS-001 regression: lowercase variant should also produce "
            f"'javascript-extensions', got {result!r}",
        )

    # ------------------------------------------------------------------
    # D-2 unit test — TC-KBS-003 (_kb_noun_from_cluster extraction fix)
    # ------------------------------------------------------------------

    def test_kb_noun_strips_extraction_nominal_form(self):
        """TC-KBS-003: 'text-extraction' + verb 'extract' -> noun 'text' (not 'text-extraction')."""
        from site_planner import _kb_noun_from_cluster
        result = _kb_noun_from_cluster("text-extraction", "pdf", "extract")
        self.assertEqual(
            result,
            "text",
            f"TC-KBS-003 regression: expected noun 'text', got {result!r}. "
            "Nominal form 'extraction' must be stripped when verb is 'extract'.",
        )

    # ------------------------------------------------------------------
    # D-1 end-to-end slug test
    # ------------------------------------------------------------------

    def test_slug_d1_javascript_extensions_end_to_end(self):
        """TC-KBS-001 e2e: cluster 'javascript-extensions' -> 'how-to-work-with-javascript-extensions-dotnet'."""
        clusters = [_make_cluster("javascript-extensions")]
        pages = plan_kb(
            family="pdf",
            platform="net",
            clusters=clusters,
            total_claims=50,
            snippet_count=1,
            tier="placeholder",
            existing=[],
        )
        howto_slugs = [p["slug"] for p in pages if "how-to" in p.get("slug", "")]
        self.assertIn(
            "how-to-work-with-javascript-extensions-dotnet",
            howto_slugs,
            "D-1 e2e: correct hyphenated slug not found in plan output",
        )
        self.assertNotIn(
            "how-to-work-with-javascriptextensions-dotnet",
            howto_slugs,
            "D-1 e2e: old defective slug (missing hyphen) must not appear in plan",
        )

    # ------------------------------------------------------------------
    # D-2 end-to-end slug test
    # ------------------------------------------------------------------

    def test_slug_d2_text_extraction_end_to_end(self):
        """TC-KBS-003 e2e: cluster 'text-extraction' -> 'how-to-extract-text-dotnet' (not double-verb)."""
        clusters = [_make_cluster("text-extraction")]
        pages = plan_kb(
            family="pdf",
            platform="net",
            clusters=clusters,
            total_claims=50,
            snippet_count=1,
            tier="placeholder",
            existing=[],
        )
        howto_slugs = [p["slug"] for p in pages if "how-to" in p.get("slug", "")]
        self.assertIn(
            "how-to-extract-text-dotnet",
            howto_slugs,
            "D-2 e2e: correct de-duplicated slug not found in plan output",
        )
        self.assertNotIn(
            "how-to-extract-text-extraction-dotnet",
            howto_slugs,
            "D-2 e2e: old defective double-verb slug must not appear in plan",
        )


class TestKBSlugWordsNetLaunch(unittest.TestCase):
    """Regression tests for KB slug defects D-3 and D-4, found generating the
    words/net site plan (2026-07-23, TC-KBS-021).

    D-3 (C4 / TC-KBS-016): Aspose.Words.NET's real "Drawing",
    "LinksAndReferences", and "IndexAndTables" namespaces either fall through
    to a generic cross-family _SUBPKG_LABEL entry (built for slides'
    PowerPoint-shape "drawing" namespace) or the CamelCase-split fallback —
    neither includes a words-specific qualifier, so C4 rejected the derived
    KB slug as ambiguous without URL context. Fixed by adding a
    _FAMILY_SUBPKG_LABELS["words"] override, mirroring pdf's RC-5/TC-KBS-015
    fix (product qualifier at the label level, not a loosened keyword set).

    D-4: _VERB_NOMINAL_FORMS (used by _kb_noun_from_cluster to strip a verb's
    nominal form from the noun) was missing entries for several verbs
    _VERB_KEYWORDS can actually produce ("load", "export", "build", "add",
    "traverse"). _validate_kb_slugs's Check 2 re-derives the verb generically
    (verb + "ion"/"ing"/"tion"/"ation") straight from the slug text, so a
    missing entry lets an unstripped nominal-form noun through generation and
    then fails validation as a false "duplication". Confirmed live: cluster
    category "loading" + verb "load" produced noun "loading" unstripped,
    yielding the rejected slug "how-to-load-loading-dotnet".
    """

    # ------------------------------------------------------------------
    # D-3 unit tests — TC-KBS-021 (_FAMILY_SUBPKG_LABELS["words"] overrides)
    # ------------------------------------------------------------------

    def test_subpkg_to_label_words_drawing_gets_product_qualifier(self):
        """D-3: words' 'Drawing' namespace must not reuse slides' bare 'drawing-shapes'."""
        from site_planner import _subpkg_to_label
        result = _subpkg_to_label("Drawing", "words")
        self.assertEqual(
            result,
            "word-drawing-shapes",
            f"D-3 regression: expected 'word-drawing-shapes', got {result!r}. "
            "words needs its own qualified label, distinct from slides' generic "
            "'drawing-shapes' _SUBPKG_LABEL entry.",
        )

    def test_subpkg_to_label_words_links_and_references(self):
        """D-3: words' 'LinksAndReferences' namespace gets a words-qualified label."""
        from site_planner import _subpkg_to_label
        result = _subpkg_to_label("LinksAndReferences", "words")
        self.assertEqual(result, "word-links-and-references")

    def test_subpkg_to_label_words_index_and_tables(self):
        """D-3: words' 'IndexAndTables' namespace gets a words-qualified label."""
        from site_planner import _subpkg_to_label
        result = _subpkg_to_label("IndexAndTables", "words")
        self.assertEqual(result, "word-index-and-tables")

    def test_words_family_subpkg_labels_do_not_affect_other_families(self):
        """D-3: the words override must not leak into slides' generic 'drawing' mapping."""
        from site_planner import _subpkg_to_label
        result = _subpkg_to_label("drawing", "slides")
        self.assertEqual(
            result,
            "drawing-shapes",
            "words-specific override must not change slides' existing label",
        )

    # ------------------------------------------------------------------
    # D-4 unit tests — TC-KBS-021 (_kb_noun_from_cluster nominal-form gaps)
    # ------------------------------------------------------------------

    def test_kb_noun_bare_loading_falls_back_to_family_name(self):
        """D-4: category=='loading' (verb's whole-word nominal form) -> family name."""
        from site_planner import _kb_noun_from_cluster
        result = _kb_noun_from_cluster("loading", "words", "load")
        self.assertEqual(
            result,
            "words",
            f"D-4 regression: expected fallback to family name 'words', got {result!r}. "
            "'loading' is the bare nominal form of verb 'load' with no other "
            "meaningful noun content, same edge case as category==verb.",
        )

    def test_kb_noun_strips_hyphenated_loading_nominal_form(self):
        """D-4: compound category 'document-loading' + verb 'load' -> noun 'document'."""
        from site_planner import _kb_noun_from_cluster
        result = _kb_noun_from_cluster("document-loading", "words", "load")
        self.assertEqual(result, "document")

    def test_kb_noun_gerund_form_covers_every_verb_keyword(self):
        """D-4: every verb _VERB_KEYWORDS can produce strips its bare "-ing" gerund
        (the one nominal suffix that is regular for every English verb, unlike
        "-ion"/"-tion"/"-ation" which require per-verb spelling — e.g. "convert"
        + "ion" concatenates to "convertion", not the real word "conversion").
        A missing entry leaves the verb duplicated in the noun, which
        _validate_kb_slugs's Check 2 (generic verb+"ing" match) then rejects —
        exactly how the "load"/"loading" gap surfaced for words/net."""
        from site_planner import _VERB_KEYWORDS, _kb_noun_from_cluster
        produced_verbs = {v for _, v in _VERB_KEYWORDS} | {"work-with"}
        for verb in produced_verbs:
            if verb == "work-with":
                continue  # compound verb, no nominal form expected
            # Standard English rule: drop a trailing silent "e" before "-ing"
            # (create -> creating, not createing).
            stem = verb[:-1] if verb.endswith("e") else verb
            candidate = f"{stem}ing"
            result = _kb_noun_from_cluster(candidate, "words", verb)
            self.assertNotIn(
                verb,
                result,
                f"D-4: verb {verb!r} gerund {candidate!r} was not stripped "
                f"(got noun {result!r}) — add {candidate!r} to "
                f"_VERB_NOMINAL_FORMS[{verb!r}]",
            )

    # ------------------------------------------------------------------
    # D-3 / D-4 end-to-end slug tests
    # ------------------------------------------------------------------

    def test_slug_d3_word_drawing_shapes_end_to_end(self):
        """D-3 e2e: cluster 'word-drawing-shapes' passes C4 and produces a clean slug."""
        clusters = [_make_cluster("word-drawing-shapes")]
        pages = plan_kb(
            family="words",
            platform="net",
            clusters=clusters,
            total_claims=50,
            snippet_count=1,
            tier="placeholder",
            existing=[],
        )
        howto_slugs = [p["slug"] for p in pages if "how-to" in p.get("slug", "")]
        self.assertIn("how-to-add-word-drawing-shapes-dotnet", howto_slugs)

    def test_slug_d3_word_links_and_references_end_to_end(self):
        """D-3 e2e: cluster 'word-links-and-references' passes C4."""
        clusters = [_make_cluster("word-links-and-references")]
        pages = plan_kb(
            family="words",
            platform="net",
            clusters=clusters,
            total_claims=50,
            snippet_count=1,
            tier="placeholder",
            existing=[],
        )
        howto_slugs = [p["slug"] for p in pages if "how-to" in p.get("slug", "")]
        self.assertIn("how-to-work-with-word-links-and-references-dotnet", howto_slugs)

    def test_slug_d3_word_index_and_tables_end_to_end(self):
        """D-3 e2e: cluster 'word-index-and-tables' passes C4."""
        clusters = [_make_cluster("word-index-and-tables")]
        pages = plan_kb(
            family="words",
            platform="net",
            clusters=clusters,
            total_claims=50,
            snippet_count=1,
            tier="placeholder",
            existing=[],
        )
        howto_slugs = [p["slug"] for p in pages if "how-to" in p.get("slug", "")]
        self.assertIn("how-to-work-with-word-index-and-tables-dotnet", howto_slugs)

    def test_slug_d4_loading_end_to_end(self):
        """D-4 e2e: cluster 'loading' -> 'how-to-load-words-dotnet', not double-verb."""
        clusters = [_make_cluster("loading")]
        pages = plan_kb(
            family="words",
            platform="net",
            clusters=clusters,
            total_claims=50,
            snippet_count=1,
            tier="placeholder",
            existing=[],
        )
        howto_slugs = [p["slug"] for p in pages if "how-to" in p.get("slug", "")]
        self.assertIn(
            "how-to-load-words-dotnet",
            howto_slugs,
            "D-4 e2e: correct de-duplicated slug not found in plan output",
        )
        self.assertNotIn(
            "how-to-load-loading-dotnet",
            howto_slugs,
            "D-4 e2e: old defective double-verb slug must not appear in plan",
        )


class TestKBSlugSelfHealingGenericLabels(unittest.TestCase):
    """Regression tests for D-5 (TC-KBS-022), found by a static audit while
    fixing D-3/D-4 for words/net (2026-07-23).

    The audit drove every value in _SUBPKG_LABEL / _FAMILY_SUBPKG_LABELS
    through the real plan_kb(), across all 11 families registered in
    data/products.json (excluding categories KB_SKIP_CLUSTERS filters out
    before they'd ever reach validation), with no dependency on any real
    product's knowledge data — a pure configuration check. It found 110
    (family, category) combinations that would crash _validate_kb_slugs the
    first time any family's actual codebase happened to produce that
    subpackage name (confirmed live for two ALREADY-SHIPPED products,
    independent of the words/net launch: `pdf net` crashed on its own
    pre-existing "generator"/"stamps" -> "page-generation" label, then again on
    "logicalstructure"/"tagged"/"structure" -> "logical-structure"; `words
    python` crashed on the default root-label fallback "core-management").

    Rather than hand-curate a _FAMILY_SUBPKG_LABELS override for each of the
    110 (an unbounded, whack-a-mole fix, since any newly-launched product can
    introduce a new colliding subpackage name), _kb_noun_from_cluster now
    mirrors _validate_kb_slugs's own Check 3 (_KB_GENERIC_NOUNS) and Check 4 /
    C4 (_FAMILY_PRODUCT_KEYWORDS) and pre-emptively prefixes the family name
    whenever a noun would fail either — the exact fix the ValueError message
    itself already suggested as option 1. This can only ever change a noun the
    validator would otherwise reject outright, so it cannot affect any
    already-shipped page that is currently passing.
    """

    def test_generic_root_label_self_heals_for_unconfigured_family(self):
        """D-5: a family with NO _ROOT_LABELS entry no longer crashes on the
        generic "core-management" default — it self-heals via family prefix."""
        from site_planner import _kb_noun_from_cluster, detect_kb_verb
        verb = detect_kb_verb("core-management")
        noun = _kb_noun_from_cluster("core-management", "hypothetical-family", verb)
        self.assertNotEqual(
            noun.split("-")[0],
            "core",
            f"D-5 regression: noun {noun!r} still has generic primary word "
            "'core' — self-heal prefix did not fire",
        )

    def test_cross_family_generic_label_self_heals(self):
        """D-5: a cross-family generic label (e.g. "logical-structure", which
        carries no pdf-specific word) self-heals via family prefix for pdf."""
        from site_planner import _kb_noun_from_cluster
        noun = _kb_noun_from_cluster("logical-structure", "pdf", "create")
        self.assertTrue(
            noun.startswith("pdf-"),
            f"D-5 regression: expected noun prefixed with 'pdf-', got {noun!r}",
        )

    def test_self_heal_is_noop_for_already_qualified_label(self):
        """D-5: a label that already contains its family's keyword (e.g. pdf's
        own "pdf-graphics") must NOT be double-prefixed."""
        from site_planner import _kb_noun_from_cluster
        noun = _kb_noun_from_cluster("pdf-graphics", "pdf", "add")
        self.assertEqual(
            noun,
            "pdf-graphics",
            f"D-5 regression: self-heal must be a no-op for an already-passing "
            f"noun, got {noun!r}",
        )

    def test_slug_d5_pdf_logical_structure_end_to_end(self):
        """D-5 e2e: pdf's real (pre-existing) 'logical-structure' cluster label
        — confirmed live to crash `pdf net` site-plan regeneration — now
        produces a valid, non-crashing slug."""
        clusters = [_make_cluster("logical-structure")]
        pages = plan_kb(
            family="pdf",
            platform="net",
            clusters=clusters,
            total_claims=50,
            snippet_count=1,
            tier="placeholder",
            existing=[],
        )
        howto_slugs = [p["slug"] for p in pages if "how-to" in p.get("slug", "")]
        self.assertTrue(
            any("pdf" in s for s in howto_slugs),
            f"D-5 e2e: expected a pdf-qualified slug, got {howto_slugs}",
        )

    def test_all_family_x_label_combinations_pass_validation(self):
        """D-5 systemic guard: for every family registered in
        data/products.json (11 as of 2026-07-23, not just the 9 implied by
        the union of _FAMILY_PRODUCT_KEYWORDS/_FAMILY_SUBPKG_LABELS/
        _ROOT_LABELS — a reviewer caught that narrower framing missing
        "page"/"tex"), every cluster category label that family's codebase
        could plausibly ever produce (every _SUBPKG_LABEL value, every
        _FAMILY_SUBPKG_LABELS[family] override, and that family's
        _ROOT_LABELS entry / default) must produce a KB how-to slug that
        survives the real _validate_kb_slugs (exercised end-to-end via
        plan_kb, not a reimplementation of its checks) with
        source="derived". Categories KB_SKIP_CLUSTERS filters out are
        excluded — they never reach plan_kb's eligible list in real usage,
        so a hypothetical failure there is not reachable. This is a pure
        configuration check — no dependency on any real product's
        knowledge/ data — so it runs unconditionally in CI and would have
        caught all 110 reachable combinations the 2026-07-23 audit found
        (an initial audit pass that didn't exclude KB_SKIP_CLUSTERS
        over-counted this at 127), plus any future family/label addition
        that reintroduces the gap.
        """
        import json
        from site_planner import (
            _SUBPKG_LABEL, _FAMILY_SUBPKG_LABELS, _ROOT_LABELS, KB_SKIP_CLUSTERS,
        )

        products_path = Path(__file__).resolve().parents[3] / "data" / "products.json"
        registered = json.loads(products_path.read_text(encoding="utf-8"))
        families = sorted({
            e.get("family") for e in registered
            if isinstance(e, dict) and e.get("family")
        })
        self.assertGreaterEqual(
            len(families), 11,
            "expected at least the 11 families registered as of 2026-07-23 — "
            "data/products.json may have been read incorrectly",
        )

        failures = []
        for family in families:
            labels = set(_SUBPKG_LABEL.values())
            labels |= set(_FAMILY_SUBPKG_LABELS.get(family, {}).values())
            labels.add(_ROOT_LABELS.get(family, "core-management"))
            for category in sorted(labels):
                if category.lower() in KB_SKIP_CLUSTERS:
                    continue  # never reaches plan_kb's eligible list in real usage
                clusters = [_make_cluster(category)]
                try:
                    plan_kb(
                        family=family,
                        platform="net",
                        clusters=clusters,
                        total_claims=50,
                        snippet_count=1,
                        tier="placeholder",
                        existing=[],
                    )
                except ValueError as exc:
                    failures.append((family, category, str(exc).splitlines()[0]))
        self.assertEqual(
            failures,
            [],
            f"D-5 regression: {len(failures)} (family, category) combination(s) "
            f"crash _validate_kb_slugs:\n" + "\n".join(
                f"  {f!r} {c!r}: {msg}" for f, c, msg in failures
            ),
        )


if __name__ == "__main__":
    unittest.main()
