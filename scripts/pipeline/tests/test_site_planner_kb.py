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


if __name__ == "__main__":
    unittest.main()
