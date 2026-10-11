"""HARDEN-A13: KB/blog page-count scaling regression fixtures.

A dedicated audit found `site_planner.py` genuinely scales docs (uncapped
cluster loop) and reference (1:1 with API surface via batch_reference.py) —
but KB how-tos were hard-sliced at `eligible[:7]` and blog capped at exactly
one optional deep-dive post, BOTH independent of product size. Empirical
proof: pdf/net (5.85x the classes, 8.9x the claims of words/python) got only
1.08x the KB pages and 1.5x the blog posts, vs. docs' 2.1x and reference's
5.9x.

These tests are the "regression fixtures, not just new tests" the hardening
plan called for:
  1. `words/python`-shaped and `pdf/net`-shaped fixtures (using each product's
     REAL cluster/claim counts) must not shrink relative to the old flat cap
     — proving no regression for already-shipped products.
  2. A synthetic large-product fixture (beyond pdf/net's real size) must
     demonstrably produce MORE KB/blog pages than the old flat cap
     (`eligible[:7]` / single deep-dive) would have — proving the fix
     actually scales, not just "doesn't shrink."

Every cluster below is given a pre-matched `existing` page (frontmatter_cluster
set to the cluster's category), so `_match_existing_to_cluster` resolves via
the "discovered" path for every one. This is deliberate: these tests exercise
PAGE-COUNT scaling, not slug derivation — `_validate_kb_slugs`'s quality
checks (verb-noun duplication, generic-noun, compound-without-family-keyword)
only raise for `source == "derived"`, so matched/discovered clusters sidestep
them entirely, exactly like a real re-plan of an already-launched product
would (site_planner's own primary real-world use case).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from site_planner import _deep_dive_post_cap, _kb_howto_cap, plan_blog, plan_kb


def _cluster(name: str, claim_count: int = 10, api_method_count: int = 5,
            snippet_count: int = 5) -> dict:
    return {
        "name": name,
        "category": name,
        "slug": name.lower().replace(" ", "-").replace("_", "-"),
        "claim_count": claim_count,
        "api_method_count": api_method_count,
        "snippet_count": snippet_count,
        "class_names": [],
        "in_limitations": False,
        "claims": [f"CLM-{name}-{i:03d}" for i in range(claim_count)],
    }


def _existing_for(cluster: dict, site: str, family: str, platform: str, kind: str) -> dict:
    """A pre-existing page matched to `cluster` via frontmatter_cluster — puts
    every planner call on the 'discovered' path, not 'derived'."""
    slug = cluster["slug"]
    if kind == "kb":
        path = f"content/kb.aspose.org/en/{family}/{platform}/how-to-{slug}.md"
    else:
        path = f"content/blog.aspose.org/{family}/{platform}/{family}-{slug}-in-{platform}/index.md"
    return {
        "slug": slug, "path": path,
        "frontmatter_cluster": cluster["category"],
        "title": "", "auto_updatable": True,
    }


def _clusters_with_existing(n: int, *, prefix: str, site: str, family: str, platform: str,
                            kind: str, claim_count: int, api_method_count: int = 5,
                            snippet_count: int = 5) -> tuple[list[dict], list[dict]]:
    clusters = [_cluster(f"{prefix}{i}", claim_count=claim_count,
                        api_method_count=api_method_count, snippet_count=snippet_count)
               for i in range(n)]
    existing = [_existing_for(c, site, family, platform, kind) for c in clusters]
    return clusters, existing


def _kb_howto_pages(pages: list[dict]) -> list[dict]:
    return [p for p in pages if p.get("cluster") and p.get("mandatory") is False
            and p.get("slug") not in ("troubleshooting", "use-cases")]


def _deep_dive_pages(pages: list[dict]) -> list[dict]:
    return [p for p in pages if p.get("blog_role") == "deep-dive"]


# ---------------------------------------------------------------------------
# Cap functions — direct unit coverage
# ---------------------------------------------------------------------------

def test_kb_howto_cap_step_function():
    assert _kb_howto_cap(50) == 7     # unchanged floor for small products
    assert _kb_howto_cap(299) == 7
    assert _kb_howto_cap(300) == 9
    assert _kb_howto_cap(499) == 9
    assert _kb_howto_cap(500) == 12
    assert _kb_howto_cap(999) == 12
    assert _kb_howto_cap(1000) == 20
    assert _kb_howto_cap(50000) == 20


def test_deep_dive_cap_step_function():
    assert _deep_dive_post_cap(50) == 1        # unchanged floor
    assert _deep_dive_post_cap(999) == 1
    assert _deep_dive_post_cap(1000) == 2
    assert _deep_dive_post_cap(1999) == 2
    assert _deep_dive_post_cap(2000) == 3


# ---------------------------------------------------------------------------
# Regression fixtures — real, already-shipped product shapes must not shrink
# ---------------------------------------------------------------------------

def test_words_python_shaped_fixture_kb_not_shrunk():
    """words/python: 146 classes, 972 claims, 11 real clusters (per the
    hardening audit) — today's flat cap of 7 already covered most, but the
    fixed cap (12, since 972 is in the 500-999 bracket) must include ALL 11,
    strictly more than the old cap, never fewer."""
    clusters, existing = _clusters_with_existing(
        11, prefix="cluster", site="kb", family="words", platform="python",
        kind="kb", claim_count=15, api_method_count=2)
    pages = plan_kb("words", "python", clusters, total_claims=972,
                    snippet_count=18, tier="launched", existing=existing)
    howtos = _kb_howto_pages(pages)
    assert len(howtos) == 11, f"expected all 11 eligible clusters covered, got {len(howtos)}"
    assert len(howtos) >= 7, "must never regress below the old flat cap"


def test_pdf_net_shaped_fixture_kb_not_shrunk_and_grows():
    """pdf/net: 854 classes, 8635 claims, ~21 real clusters — the ORIGINAL
    bug capped this at 7 KB pages regardless. The fix (cap=20 at this claim
    volume) must produce strictly MORE than 7."""
    clusters, existing = _clusters_with_existing(
        21, prefix="cluster", site="kb", family="pdf", platform="net",
        kind="kb", claim_count=30, api_method_count=4)
    pages = plan_kb("pdf", "net", clusters, total_claims=8635,
                    snippet_count=100, tier="launched", existing=existing)
    howtos = _kb_howto_pages(pages)
    assert len(howtos) == 20, f"expected cap of 20 applied to 21 eligible clusters, got {len(howtos)}"
    assert len(howtos) > 7, "must grow beyond the old flat cap for a large product"


def test_pdf_net_shaped_fixture_blog_not_shrunk_and_grows():
    """pdf/net's real claim volume (8635) is at/above the 2000+ tier used for
    a 3-post cap here (_deep_dive_post_cap(8635) == 3) — the old code could
    only ever produce 1 deep-dive post no matter how many eligible clusters
    remained. The Post-2 features cluster is given a HIGHER claim_count so
    kf-cluster selection deterministically picks it over the deep-dive pool,
    leaving all 6 deep-dive-eligible clusters available (capped to 3)."""
    kf_cluster = _cluster("featurestopic", claim_count=200, snippet_count=20)
    dive_clusters, dive_existing = _clusters_with_existing(
        6, prefix="divetopic", site="blog", family="pdf", platform="net",
        kind="blog", claim_count=25, snippet_count=10)
    clusters = [kf_cluster] + dive_clusters
    existing = [_existing_for(kf_cluster, "blog", "pdf", "net", "blog")] + dive_existing

    pages, justified, _retired = plan_blog(
        "pdf", "net", total_claims=8635, snippet_count=100, clusters=clusters,
        existing=existing,
    )
    assert justified is True
    dive_pages = _deep_dive_pages(pages)
    assert len(dive_pages) == 3, f"expected cap of 3 deep-dive posts, got {len(dive_pages)}"
    assert len(dive_pages) > 1, "must grow beyond the old single-post cap for a large product"


# ---------------------------------------------------------------------------
# Synthetic large-product fixture — beyond any currently-shipped product
# ---------------------------------------------------------------------------

def test_synthetic_xl_product_kb_scales_up():
    """A hypothetical product larger than any currently shipped (matches the
    plan's expectation that Aspose.Words, historically one of the largest
    Aspose APIs, could plausibly land here) — must get proportionally more
    KB coverage than the old flat 7, not a silently reused small-product plan."""
    clusters, existing = _clusters_with_existing(
        30, prefix="xl", site="kb", family="hypothetical-xl", platform="net",
        kind="kb", claim_count=40, api_method_count=6)
    pages = plan_kb("hypothetical-xl", "net", clusters, total_claims=15000,
                    snippet_count=200, tier="launched", existing=existing)
    howtos = _kb_howto_pages(pages)
    assert len(howtos) == 20  # cap ceiling, not all 30 (a deliberate ceiling, not unbounded)
    assert len(howtos) > 7


def test_small_product_kb_and_blog_unaffected():
    """A genuinely small product (< 300 claims) must see NO behavior change —
    this is the floor every currently-shipped small product depends on."""
    clusters, existing = _clusters_with_existing(
        3, prefix="tiny", site="kb", family="tiny-fam", platform="python",
        kind="kb", claim_count=5, api_method_count=2)
    pages = plan_kb("tiny-fam", "python", clusters, total_claims=60,
                    snippet_count=2, tier="launched", existing=existing)
    howtos = _kb_howto_pages(pages)
    assert len(howtos) == 3  # all 3 eligible, well under any cap — no behavior change


# ---------------------------------------------------------------------------
# force_justify — human-gated override of the total_claims/snippet_count gate
# (cells/go: real product with total_claims=136 < 200, snippet_count=15 >= 5,
# genuinely below threshold on real upstream source, not an extraction bug)
# ---------------------------------------------------------------------------

def test_force_justify_false_default_unaffected():
    """H-4 (MT074-2026-09-25-GIS-NET-LAUNCH-AND-READINESS-GATE-HARDENING):
    a below-threshold product still gets the mandatory announcement post
    (INV-021 fix) even when force_justify is not passed -- only the
    optional features/deep-dive posts stay gated. `justified` still
    correctly reports False (the full section's threshold wasn't met);
    `pages` is no longer empty (was the actual INV-021 bug: cells/go's real
    68-136-claim shape used to get zero blog pages at all, requiring a
    human to notice and manually intervene)."""
    cluster = _cluster("spreadsheet-management", claim_count=87, api_method_count=56,
                       snippet_count=15)
    pages, justified, _retired = plan_blog(
        "cells", "go", total_claims=136, snippet_count=15, clusters=[cluster],
    )
    assert justified is False
    assert len(pages) == 1
    assert pages[0]["blog_role"] == "announcement"
    assert pages[0]["mandatory"] is True


def test_existing_post_preserved_even_when_not_justified():
    """H-4: the existing-post preservation loop must run unconditionally too
    -- this is the actual mechanism behind imaging/net's real site_plan.yaml
    desync (blog_justified: false, pages: [] on disk, while a real
    announcement post existed and was invisible to the plan). A real,
    already-published post that doesn't match the intro/features pattern
    (e.g. a human-authored one-off) must survive into `pages` even when the
    product is below threshold."""
    cluster = _cluster("spreadsheet-management", claim_count=10, api_method_count=5,
                       snippet_count=1)
    existing_post = {
        "slug": "a-human-authored-deep-dive",
        "path": "content/blog.aspose.org/cells/go/a-human-authored-deep-dive/index.md",
    }
    pages, justified, _retired = plan_blog(
        "cells", "go", total_claims=50, snippet_count=1, clusters=[cluster],
        existing=[existing_post],
    )
    assert justified is False
    slugs = {p["slug"] for p in pages}
    assert "a-human-authored-deep-dive" in slugs, (
        f"existing post silently dropped when not justified -- the exact "
        f"imaging/net desync shape. pages={pages!r}"
    )


def test_imaging_net_shaped_fixture_gets_announcement_post_not_zero():
    """H-4 real-precedent fixture: imaging/net's actual historical shape
    (68 total_claims, 50 snippets -- still under the 200-claim leg of the
    AND-gate) launched with ZERO blog posts before this fix, and needed a
    human to notice the resulting 404 and patch it in separately (see the
    real commit 84ffeabff5, "explicit operator override... not a
    retroactive claim that the threshold was wrong"). Proves the split is
    real: announcement post ships, features post does not, at the exact
    number that broke in production."""
    cluster = _cluster("image-probing", claim_count=40, api_method_count=20,
                       snippet_count=50)
    pages, justified, _retired = plan_blog(
        "imaging", "net", total_claims=68, snippet_count=50, clusters=[cluster],
    )
    assert justified is False  # total_claims=68 < 200 -- features/deep-dive correctly still gated
    assert len(pages) == 1
    assert pages[0]["blog_role"] == "announcement"
    assert pages[0]["slug"] == "introducing-imaging-foss-net"
    roles = {p["blog_role"] for p in pages}
    assert "features" not in roles
    assert "deep-dive" not in roles


def test_force_justify_true_bypasses_claims_threshold():
    """cells/go-shaped fixture: total_claims=136 (< 200) but snippet_count=15
    (>= 5) — force_justify=True must still plan real Post 1 (intro) + Post 2
    (cluster-derived features) pages, exactly as if the product had cleared
    the threshold normally."""
    cluster = _cluster("spreadsheet-management", claim_count=87, api_method_count=56,
                       snippet_count=15)
    pages, justified, _retired = plan_blog(
        "cells", "go", total_claims=136, snippet_count=15, clusters=[cluster],
        force_justify=True,
    )
    assert justified is True
    assert len(pages) == 2
    slugs = {p["slug"] for p in pages}
    assert "introducing-cells-foss-go" in slugs
    assert "cells-spreadsheet-management-go" in slugs


def test_force_justify_true_bypasses_both_legs():
    """force_justify overrides the full `total_claims >= 200 and snippet_count
    >= 5` gate, not just one leg — a product failing both must still plan
    pages when explicitly forced."""
    cluster = _cluster("tiny-topic", claim_count=8, api_method_count=2, snippet_count=1)
    pages, justified, _retired = plan_blog(
        "tiny-fam", "python", total_claims=40, snippet_count=1, clusters=[cluster],
        force_justify=True,
    )
    assert justified is True
    assert len(pages) == 2


# ---------------------------------------------------------------------------
# Reviewer note: docs/reference already scale correctly (per the audit) and
# are intentionally NOT touched by this change — only KB/blog caps moved.
# ---------------------------------------------------------------------------
