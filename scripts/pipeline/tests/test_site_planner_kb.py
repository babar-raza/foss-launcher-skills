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


if __name__ == "__main__":
    unittest.main()
