# Backlinks v3 Reference

**Status:** FULLY IMPLEMENTED (all 8 amendments, 249 tests passing, 27/27 validators PASS)
**Sprint proof:** `data/backlinks/sprint_execution_proof.json`
**Amendment stack:** v2.0 → A1 → A2/P0 → A3 → A4 → A5 → A6 → A7

---

## 1. Purpose

The backlinks system inserts verified enterprise links from `aspose.org` content pages into `aspose.com` enterprise destinations. Every inserted URL must be HTTP 200 verified before insertion. No URL is ever guessed, constructed ad-hoc, or synthesized without local verification evidence.

**v1 baseline** resolved only `{family}/{platform}` platform-level and `{family}/` family-level landing pages.

**v3** adds: deep reference class matching, KB article matching, variant/bridge slug resolution, best verified ancestor fallback, anchor text config registry, and a three-tier adjudication workflow — while keeping v1 behavior byte-identical when `--deep` is not specified.

---

## 2. Architecture: Layer Model

```
Layer 0.4  Enterprise Target Candidate Inventory
           Script: backlink_build_enterprise_candidate_inventory.py
           Input:  data/aspose_com_targets.json → all_urls
           Output: data/backlinks/workspace/enterprise_target_candidate_inventory.json (gitignored)
           Purpose: Groups variant/bridge slug URLs by canonical base platform

Layer 0.6  Platform Variant Authority
           Script: backlink_build_platform_variant_authority.py
           Input:  Layer 0.4 + data/backlinks/platform_canonical_overrides.yaml
           Output: data/backlinks/workspace/platform_variant_authority.json (gitignored)
           Purpose: Selects exactly one canonical verified URL per (subdomain, family, local_slug)

Layer 1    Verified Endpoint Inventory (Deep Target Index)
           Script: backlink_build_deep_index.py
           Input:  data/aspose_com_targets.json → all_urls
           Output: data/backlinks/workspace/deep_target_index.json (gitignored)
           Purpose: All verified HTTP 200 deep endpoints, path-normalized, metadata-enriched

Layer 1.5  AI-Enriched Metadata Index (advisory only)
           Script: backlink_ai_enrich.py
           Input:  Layer 1 + content/ frontmatter
           Output: data/backlinks/workspace/ai_enrichment_index.json (gitignored)
           Purpose: Embedding vectors + LLM classification labels (advisory only; AI is NEVER authority)

Layer 2    Intelligent Candidate Graph
           Script: backlink_build_candidates.py
           Input:  Layer 1 + Layer 1.5 (optional) + content frontmatter
           Output: data/backlinks/workspace/candidate_graph.json (gitignored)
           Purpose: Multiple ranked candidates per source page with scoring

Layer 3    Approved Backlink Authority
           Script: backlink_approve_authority.py
           Input:  Layer 2
           Output: data/backlinks/workspace/backlink_authority.json (gitignored)
           Purpose: Exactly ONE canonical target per (source_key, link_slot), or BLOCKED

Resolver   scripts/pipeline/lib/backlink_targets.py → resolve_backlink()
           Reads:  Layer 3 (when --deep enabled), Layer 0.6, v1 target map
           Never reads: Layer 1, Layer 2, Layer 1.5

Insertion  scripts/pipeline/commands/ops/backlink_backfill.py
           Reads:  Resolver output only
           Never reads: any layer directly
           Never constructs URLs
           Never calls LLMs or HTTP
```

**Absolute invariants:**
- AI is never authority. Resolver reads Layer 3 only.
- Backfill reads `rendered_anchor_text` from authority record only — never calls `render_anchor_text()` directly.
- `resolve_backlink()` default is `exact_deep_match_enabled=False` (v1 behavior unchanged).
- No HTTP or LLM calls during resolution or insertion.
- `content/` is never written by the deep pipeline itself (content writes are a separate sprint gate).

---

## 3. Core Library: `backlink_targets.py`

**Path:** `scripts/pipeline/lib/backlink_targets.py`

### 3.1 PLATFORM_ALIASES (lines 34–51)

Maps enterprise URL slugs → canonical local platform names. Used throughout the system.

```python
PLATFORM_ALIASES = {
    # Standard platforms
    "net": "net", "java": "java", "cpp": "cpp", "python": "python",
    "nodejs": "nodejs", "go": "go", "android": "android", "php": "php",
    "ruby": "ruby",
    # Python bridge slugs (reference.aspose.com variants)
    "python-net": "python", "python-java": "python", "python-cpp": "python",
    # Node.js bridge slugs
    "nodejs-net": "nodejs", "nodejs-java": "nodejs", "nodejs-cpp": "nodejs",
    "javascript-cpp": "nodejs",
    # Other bridge slugs
    "go-cpp": "go", "androidjava": "android",
    "jasperreports": "jasperreports", "rust": "rust", "rust-cpp": "rust",
    "php-java": "php",
    # TypeScript (added in TypeScript fix sprint)
    "typescript": "typescript",
}
```

Populated from `data/backlinks/platform_variant_registry.yaml` at module load.

### 3.2 PageType Enum (lines 78–107)

21 values covering all content page classifications:

| PageType | Deep Match? | Slot |
|----------|-------------|------|
| REF_CLASS | Yes (Phase 1) | enterprise_deep_primary |
| REF_NESTED_CLASS | Yes (Phase 1) | enterprise_deep_primary |
| REF_PLATFORM_INDEX | Landing only | enterprise_platform_landing |
| REF_FAMILY_INDEX | Landing only | enterprise_family_landing |
| KB_ARTICLE | Yes (Phase 1) | enterprise_deep_primary |
| KB_PLATFORM_INDEX | Landing only | enterprise_platform_landing |
| KB_FAMILY_INDEX | Landing only | enterprise_family_landing |
| DOCS_ARTICLE | Deferred (TC-003) | enterprise_deep_primary |
| DOCS_PLATFORM_INDEX | Landing only | enterprise_platform_landing |
| DOCS_FAMILY_INDEX | Landing only | enterprise_family_landing |
| DOCS_CATEGORY_TOC | Landing only | enterprise_platform_landing |
| PRODUCTS_PLUGIN | Landing only | enterprise_platform_landing |
| PRODUCTS_FAMILY | Landing only | enterprise_family_landing |
| BLOG_POST | Deferred (D-04) | — |
| PRODUCTS_ROOT | SKIP | — |
| BLOG_ARCHIVE | SKIP | — |
| BLOG_UTILITY | SKIP | — |
| SUBDOMAIN_ROOT | SKIP | — |
| LOCALE_FILE | SKIP | — |
| LOCALE_DIR | SKIP | — |
| UNKNOWN_PATTERN | SKIP | — |

### 3.3 Audit Status Constants (lines 110–177)

Key statuses used in `classify_compliance()` and `backlink_audit.py`:

```
FAMILY_FALLBACK_WHILE_PLATFORM_AVAILABLE    ← HARD FAILURE (A2/P0)
SKIPPED_CLOSER_VERIFIED_PARENT              ← HARD FAILURE (A3)
FAMILY_FALLBACK_WHILE_VARIANT_AVAILABLE     ← HARD FAILURE (A4)

EXACT_VERIFIED_TARGET                       ← Resolution kind: exact
ANCESTOR_FALLBACK_USED                      ← A3 ancestor walk result
PLATFORM_FALLBACK_USED
FAMILY_FALLBACK_USED
ROOT_FALLBACK_USED
NO_VERIFIED_FALLBACK
UNVERIFIED_CHILD_TARGET_BLOCKED

EXACT_PLATFORM_VERIFIED                     ← A4 variant
VARIANT_CANONICAL_SELECTED
VARIANT_REVIEW_REQUIRED
VARIANT_BLOCKED_NO_POLICY
SITEMAP_COVERAGE_GAP

ACCEPTABLE_LEGACY_KB_PRE_P0                 ← A7/KB transition
CANONICAL_KB_POST_P0
UPGRADE_CANDIDATE_NOT_YET_FIXED

AI_ENRICHED_PRIMARY / AI_ENRICHED_FALLBACK  ← A1/A9 AI status
AI_UNAVAILABLE_DEGRADED
AI_DEGRADATION_RATE_WARNING

AUTHORITY_ANCHOR_STALE                      ← A6/A7 anchor hash
ANCHOR_CONFIG_HASH_MISMATCH
STRUCTURAL_PAGE_SKIP                        ← auto_updatable: false
DEFERRED_NO_TARGETS                         ← docs/blog deferred
```

### 3.4 PREFERRED_TARGET_SUBDOMAIN (lines 191–197) — P0 Fix

```python
PREFERRED_TARGET_SUBDOMAIN = {
    "docs.aspose.org":      "docs.aspose.com",
    "kb.aspose.org":        "kb.aspose.com",    # FIXED: was "docs.aspose.com" (P0 bug)
    "reference.aspose.org": "reference.aspose.com",
    "products.aspose.org":  "products.aspose.com",
    "blog.aspose.org":      "products.aspose.com",
}
```

### 3.5 HOST_MAP and SOURCE_TO_TARGET_PREFIX (lines 200–215)

```python
HOST_MAP = {
    "docs":      "docs.aspose.com",
    "kb":        "kb.aspose.com",
    "products":  "products.aspose.com",
    "reference": "reference.aspose.com",
    "blog":      "blog.aspose.com",
}

SOURCE_TO_TARGET_PREFIX = {
    "docs.aspose.org":      "docs",
    "kb.aspose.org":        "kb",
    "reference.aspose.org": "reference",
    "products.aspose.org":  "products",
    "blog.aspose.org":      "blog",
}
```

URL composition happens **only** in `_resolve_deep()` via HOST_MAP. No other code constructs enterprise URLs.

### 3.6 AncestorResolutionResult (lines 239–250)

```python
@dataclass
class AncestorResolutionResult:
    requested_path: str           # e.g. "docs/cells/python/developer-guide"
    selected_path: Optional[str]  # e.g. "docs/cells/python"
    selected_url: Optional[str]   # e.g. "https://docs.aspose.com/cells/python/"
    resolution_kind: str          # ResolutionKind constant
    fallback_depth: int           # 0=exact, 1=one up, -1=blocked
    fallback_chain: list[dict]    # [{path, status}] all candidates
    fallback_reason: Optional[str]
    root_fallback_used: bool
    verified: bool
```

### 3.7 ResolutionKind Constants

```python
class ResolutionKind:
    EXACT_VERIFIED             = "EXACT_VERIFIED"
    APPROVED_DEEP_AUTHORITY    = "APPROVED_DEEP_AUTHORITY"
    PLATFORM_CANONICAL         = "PLATFORM_CANONICAL"
    BEST_VERIFIED_ANCESTOR     = "BEST_VERIFIED_ANCESTOR"
    FAMILY_FALLBACK            = "FAMILY_FALLBACK"
    ROOT_FALLBACK              = "ROOT_FALLBACK"
    BLOCKED_NO_VERIFIED_TARGET = "BLOCKED_NO_VERIFIED_TARGET"
    AMBIGUOUS_PLATFORM_TARGETS = "AMBIGUOUS_PLATFORM_TARGETS"
    AUTHORITY_STALE_FALLBACK   = "AUTHORITY_STALE_FALLBACK"
```

### 3.8 Ancestor Fallback Functions (lines 403–505)

`build_ancestor_chain(full_path: str) -> list[str]`
- Strips one path segment at a time from most-specific to least-specific
- `"docs/cells/python/developer-guide"` → `["docs/cells/python/developer-guide", "docs/cells/python", "docs/cells", "docs"]`
- Pure function, no I/O

`resolve_best_verified_ancestor(full_path, target_map, *, allowed_root_fallback=True, policy_context=None) -> AncestorResolutionResult`
- Walks chain, checks each against `target_map["all_urls"]` for HTTP 200
- Returns first verified ancestor
- Pure function — reads only `target_map["all_urls"]`, no HTTP, no LLM
- Root fallback blocked unless root URL is in `all_urls` HTTP 200

Chain generation by subdomain type:
- **Standard (docs/kb/products):** strip one segment at a time until subdomain prefix
- **Reference:** up to 6 levels (member→class→namespace→platform→family→root)
- **Blog:** conservative 3 levels only (article→category→root)

### 3.9 `resolve_backlink()` — 6-Step Fallback Chain (lines 558–640)

```python
def resolve_backlink(
    family: Optional[str],
    platform: Optional[str],
    source_subdomain: str,
    target_map: dict,
    *,
    exact_deep_match_enabled: bool = False,   # default False — v1 behavior
    canonical_overrides: Optional[dict] = None,
    authority: Optional[dict] = None,
    source_file: Optional[str] = None,
) -> tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
```

Resolution order:
1. **Deep authority** (`exact_deep_match_enabled=True` + authority record with `allowed_for_generation: true`)
2. **Canonical override** (`platform_canonical_overrides.yaml` explicit entry)
3. **Platform URL** on `PREFERRED_TARGET_SUBDOMAIN` (HTTP 200 in target_map)
4. **Family URL** on `PREFERRED_TARGET_SUBDOMAIN` (HTTP 200 in target_map)
5. **Platform URL** on `products.aspose.com` (cross-subdomain fallback)
6. **Family URL** on `products.aspose.com` (broadest fallback)

Returns `(url, type, subdomain, fallback_reason)` — same v1 tuple signature.

---

## 4. Config Registries

### 4.1 `data/backlinks/anchor_text_registry.yaml` — A6

10 anchor text templates. Rendered at approval time; stored as `rendered_anchor_text` in authority records.

| Template ID | Source Subdomain | Target Subdomain | Target Type | Anchor Text Pattern |
|-------------|-----------------|-----------------|-------------|---------------------|
| docs-platform | docs.aspose.org | docs.aspose.com | platform | `{fam} for {plat} — Enterprise Documentation` |
| docs-family | docs.aspose.org | docs.aspose.com | family | `{fam} — Enterprise Documentation` |
| kb-platform | kb.aspose.org | kb.aspose.com | platform | `{fam} for {plat} — Enterprise Knowledge Base` |
| kb-family | kb.aspose.org | kb.aspose.com | family | `{fam} — Enterprise Knowledge Base` |
| reference-platform | reference.aspose.org | reference.aspose.com | platform | `{fam} for {plat} — Enterprise API Reference` |
| reference-family | reference.aspose.org | reference.aspose.com | family | `{fam} — Enterprise API Reference` |
| products-platform | products.aspose.org | products.aspose.com | platform | `{fam} for {plat} — Enterprise Product` |
| products-family | products.aspose.org | products.aspose.com | family | `{fam} — Enterprise Product Family` |
| blog-products-platform | blog.aspose.org | products.aspose.com | platform | `{fam} for {plat} — Enterprise Product` |
| blog-products-family | blog.aspose.org | products.aspose.com | family | `{fam} — Enterprise Product Family` |

`{fam}` comes from `data/families.json` (e.g. `"3d" → "Aspose.3D"`).
`{plat}` comes from `scripts/pipeline/config/metrics_taxonomy.yaml` → `platforms:` (e.g. `"net" → ".NET"`, `"cpp" → "C++"`).
`{plat}` is **always the canonical display name**, never a bridge slug like `python-net`.

**Anchor config hash algorithm (A7):**
```python
import yaml, json, hashlib
data = yaml.safe_load(registry_path.read_text(encoding="utf-8"))
data.pop("config_hash", None)
canonical = json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(',', ':'))
digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
# Returns: "sha256:" + digest
```
Comments and whitespace do not affect the hash. Key ordering is stable (sort_keys=True).

**Bridge slug detection:** `render_anchor_text()` raises `AnchorPolicyError` if platform arg is one of the 12 known bridge slugs (python-net, python-java, python-cpp, nodejs-net, nodejs-java, nodejs-cpp, go-cpp, androidjava, javascript-cpp, rust-cpp, jasperreports, php-java). Callers must pass the canonical key.

### 4.2 `data/backlinks/link_slot_registry.yaml` — A5, schema 1.1.0

3 link slots:

```
enterprise_deep_primary
  section:        ## See Also
  max_per_page:   1
  eligible:       REF_CLASS, REF_NESTED_CLASS, KB_ARTICLE, DOCS_ARTICLE
  target_types:   reference_class, reference_namespace, kb_article, platform_landing

enterprise_platform_landing
  section:        ## See Also
  max_per_page:   1
  eligible:       REF_FAMILY_INDEX, REF_PLATFORM_INDEX, KB_FAMILY_INDEX, KB_PLATFORM_INDEX,
                  DOCS_FAMILY_INDEX, DOCS_PLATFORM_INDEX, DOCS_CATEGORY_TOC,
                  PRODUCTS_FAMILY, PRODUCTS_PLUGIN
  target_types:   platform_landing, family_landing

enterprise_family_landing
  section:        ## Related Resources
  max_per_page:   1
  eligible:       REF_FAMILY_INDEX, KB_FAMILY_INDEX, DOCS_FAMILY_INDEX, PRODUCTS_FAMILY
  target_types:   family_landing

global:
  max_enterprise_links_per_page: 2
  blocked_page_types: [BLOG_ARCHIVE, BLOG_UTILITY, SUBDOMAIN_ROOT, LOCALE_FILE, LOCALE_DIR, UNKNOWN_PATTERN]
```

Note: `anchor_template` field was removed in schema 1.1.0 — anchor rendering is exclusively in `anchor_text_registry.yaml`.

### 4.3 `data/backlinks/platform_variant_registry.yaml` — A4/A5-L8

12 canonical platforms: net, java, cpp, python, nodejs, go, android, php, ruby, typescript, jasperreports, rust.

Exhaustive bridge slug → canonical mappings with HTTP 200 evidence counts:
- python-net: 8,437 reference URLs
- nodejs-net: 1,997
- nodejs-cpp: 656
- androidjava: 685
- jasperreports: 473
- go-cpp: 416
- python-java: 1,087
- nodejs-java: 178
- python-cpp: 1
- typescript: local platform dirs

### 4.4 `data/backlinks/platform_canonical_overrides.yaml` — A2

Explicit platform URL overrides. Schema requires `http_verified: true` for any entry to be used. Default: `overrides: {}`.

### 4.5 `data/backlinks/anchor_overrides.yaml` — A6

Page-specific anchor text exceptions. Default: `overrides: {}`. Each entry requires `reason`, `evidence`, and `review_policy`. All entries validated via `validate_anchor_suffix()`.

---

## 5. Target Map

**File:** `data/aspose_com_targets.json`

- Size: ~19.9MB
- `all_urls` flat index: 79,789 verified HTTP 200 URLs
- URL keys: full URL with trailing slash (e.g. `https://docs.aspose.com/cells/python/`)
- Top-level structure: `schema_version`, `provenance`, `targets`, `all_urls`, `variant_slugs`
- `variant_slugs` index: groups bridge variant URLs by canonical per family (added by A4)

Key counts by type (approximately):
- `nested-class-reference`: 62,668
- `class-reference`: 1,837
- `platform-kb-root` / `deep-kb`: 3,431+
- `platform-products`: 16
- `family-landing` + `platform-landing`: ~181

---

## 6. Scripts Reference

All backlink scripts are in `scripts/pipeline/commands/ops/`.

| Script | Purpose | Amendment |
|--------|---------|-----------|
| `backlink_audit.py` | Compliance audit of content backlinks | v1 |
| `backlink_backfill.py` | Insert missing/wrong links into content | v1 |
| `backlink_build_deep_index.py` | Build Layer 1 (deep endpoint index) | P1 |
| `backlink_build_candidates.py` | Build Layer 2 (scored candidates) | P2 |
| `backlink_approve_authority.py` | Build Layer 3 (approved authority) | P3 |
| `backlink_ai_enrich.py` | Build Layer 1.5 (AI advisory) | A1/P2.5 |
| `backlink_build_enterprise_candidate_inventory.py` | Build Layer 0.4 (variant inventory) | A4 |
| `backlink_build_platform_variant_authority.py` | Build Layer 0.6 (variant authority) | A4 |
| `backlink_run_validators.py` | Run all V1–V27 validators | A5-L11 |
| `backlink_compare_tracks.py` | Compare Track A vs Track B (AI impact) | A1 |
| `backlink_adjudicate_review.py` | Three-tier REVIEW_REQUIRED adjudication | A5-L2 |
| `backlink_capture_current_anchors.py` | Capture live anchor inventory from content | A6/A7 |
| `backlink_generate_anchor_inventory.py` | Generate anchor compatibility matrix | A6/A7 |
| `backlink_validate_migration.py` | Validate evidence bundle manifest | A6/A7 |
| `backlink_html_audit.py` | HTML-level backlink audit | utility |
| `generate_product_backlink_copy.py` | Generate product YAML overview copy (CS-010) | v1 |
| `fetch_aspose_com_targets.py` | Refresh target map from sitemaps | v1 |

**Library:**
- `scripts/pipeline/lib/backlink_targets.py` — core resolver and all shared utilities

---

## 7. Test Structure

Three test files, 252 tests collected (249 passed, 1 skipped, 0 failed):

| File | Test Classes | Count |
|------|-------------|-------|
| `test_backlink_targets.py` | 7 baseline + TestPlatformLandingAuthority(15) + TestBestVerifiedAncestorFallback(16) + TestPlatformVariantAuthority(16) + TestLinkSlotRegistry(8) + TestAgentAdjudication(8) + TestAIEnrichment(10) + TestDeepBacklinks(10) | ~187 |
| `test_backlink_backfill.py` | Baseline backfill behavior | ~48 |
| `test_backlink_anchor.py` | TestAnchorCurrentInventory(10) + TestAnchorRegistrySchema(8) + TestAnchorRendererCompatibility(13) + TestAnchorConfigMutation(6) + TestAuthorityAnchorConfigHash(7) + TestBackfillUsesApprovedRenderedAnchorOnly(8) + TestAnchorTransitionMode(4) + TestBridgeDisplayPolicy(5) | 61 |

**Run all tests:**
```bash
cd d:/onedrive/Documents/GitHub/aspose.org
.venv/Scripts/python -m pytest scripts/pipeline/tests/test_backlink_targets.py scripts/pipeline/tests/test_backlink_backfill.py scripts/pipeline/tests/test_backlink_anchor.py -v
```

Gate: ≥248 (current: 249 passing).

---

## 8. Validator Inventory (V1–V27)

All run via `backlink_run_validators.py`. Output: `validator_summary.json` → `{"overall":"PASS"}`.

| # | Name | What it checks |
|---|------|----------------|
| V1 | Schema | All generated JSON artifacts validate against their JSON schemas |
| V2 | Authority Integrity | No REVIEW_REQUIRED with `allowed_for_generation:true`; no duplicate (source_key, link_slot) |
| V3 | Content Backlink | 0 unapproved deep links in content (future sprint) |
| V4 | Code Bypass | No new `f"https.*aspose"` string in insertion code paths |
| V5 | Skill Text | All 14 backlink skills have 4-line governance block |
| V6 | Pilot Regression | v1 output byte-identical with `--deep` disabled |
| V7 | Staleness | All authority `target_index_hash` values match current Layer 1; no STALE records |
| V8 | Evidence Bundle | All required_entries present in ZIP |
| V9 | AI Boundary | `ai_enrichment_index.json` never imported by resolver/approval/insertion |
| V10 | AI Score Cap | No `ai_boost` > 0.05; no Stage 1 < 0.30 with any AI boost |
| V11 | AI Degradation | Degraded count < 20% of total (graceful degradation) |
| V12 | AI Provenance | All enrichment records have embedding_model, provider, token_usage |
| V13 | Ancestor Chain Completeness | No gaps in fallback_chain; len = fallback_depth + 1 |
| V14 | No-Skip Invariant | No closer verified parent skipped for any resolution result |
| V15 | No I/O in Resolver | No `requests`/`httpx`/`llm_router` imports in `backlink_targets.py` |
| V16 | Root Fallback Verification | All `root_fallback_used:true` entries have root URL in `all_urls` HTTP 200 |
| V17 | Anchor Registry Schema | All 10 template IDs present; no empty `anchor_text` |
| V18 | Current Anchor Compatibility | 100% exact match on non-exception pages; `suspected_defect_count:0` |
| V19 | Config Mutation Proof | Docs template mutation changes only docs anchors; others unchanged |
| V20 | Authority Anchor Config Hash | All `allowed_for_generation:true` records have matching anchor_config_hash |
| V21 | Backfill Anchor Boundary | `render_anchor_text()` never called in backfill; reads `rendered_anchor_text` only; `--anchor-compat-mode` not in backfill argparse |
| V22 | Anchor Override Integrity | All overrides pass `validate_anchor_suffix()`; non-empty reason+evidence |
| V23 | PageType Anchor Coverage | All 15 non-skip PageTypes → valid template_id; all 6 SKIP/BLOCKED → AnchorPolicyError |
| V24 | Active Verdict Uniqueness | Exactly 1 ACTIVE verdict; all prior marked SUPERSEDED |
| V25 | Skill Anchor Coverage | All content-writing skills have anchor governance block |
| V26 | Evidence Bundle Manifest | Manifest-based ZIP validation (not file count) |
| V27 | Bridge Slug Display Safety | Zero bridge slugs in any `rendered_anchor_text` in authority |

---

## 9. AI Advisory Layer (Layer 1.5)

Classification: **MANDATORY_WITH_GRACEFUL_DEGRADATION** — not optional.

**Call sites registered in `scripts/pipeline/config/metrics_callsite_registry.yaml`:**
- CS-011: `backlink_ai_enrich.py` — embeddings via `qwen3-embedding-8b`
- CS-012: `backlink_ai_enrich.py` — relationship classification via `gpt-oss` (temperature=0.0)
- CS-013: `backlink_adjudicate_review.py` — REVIEW_REQUIRED adjudication via `gpt-oss`

**Closed-set classification labels:** `exact_api_class`, `related_api_class`, `same_topic`, `weakly_related`, `unrelated`.

**AI score boost rules:**
- Max boost: +0.05 (hard cap)
- Requires Stage 1 deterministic base ≥ 0.85 to reach AUTO_APPROVE_EXACT (0.85 + 0.05 = 0.90)
- AI-only match (Stage 1 < 0.30) is always BLOCKED regardless of AI confidence
- LLM says `unrelated` but Stage 1 ≥ 0.80: mandatory REVIEW_REQUIRED

**Graceful degradation states:**
- `AI_ENRICHED_PRIMARY`: professionalize available
- `AI_ENRICHED_FALLBACK`: Ollama fallback used
- `AI_UNAVAILABLE_DEGRADED`: both down; pipeline continues without AI boost
- `AI_DEGRADATION_RATE_WARNING`: > 20% records degraded

---

## 10. Confidence Bands (Layer 3 Approval)

| Band | Code | Score | Criteria | allowed_for_generation |
|------|------|-------|----------|------------------------|
| AUTO_APPROVE_EXACT | AAE | ≥ 0.90 | Exact class+family+platform+namespace (reference) or Jaccard ≥ 0.6 + ≥ 3 tokens (KB) | `true` |
| AUTO_APPROVE_LANDING | AAL | N/A | Verified landing page via v1 target map | `true` (v1 resolver) |
| REVIEW_REQUIRED | RR | 0.50–0.89 | Near-miss, metadata-only, tie margin < 0.10, cross-platform | `false` |
| BLOCKED | BLK | < 0.50 | No match, family mismatch, blog target, semantic-only | `false` |
| FALLBACK_TO_V1 | FV1 | N/A | No deep authority entry | N/A (v1 handles) |

**What can NEVER be AUTO_APPROVE:**
- Semantic-only matches (Stage 3, TF-IDF)
- Metadata-only matches (Stage 2)
- Blog targets (any score)
- Cross-platform without confirmed alias
- Same class in different namespaces without exact namespace match

---

## 11. Three-Tier Adjudication (REVIEW_REQUIRED)

Replaces the prior dead-stop behavior for REVIEW_REQUIRED entries.

**Tier 1 — Deterministic (no AI):** Single verified variant → auto-select. Explicit canonical override → auto-select. Exact slug HTTP 200 → auto-select.

**Tier 2 — AI-Assisted (`backlink_adjudicate_review.py`):** Closed-set outcomes:
- `PROMOTE_AUTO_APPROVE`: AI ≥ 0.90 confidence + boosted score ≥ 0.90 → promote
- `PROMOTE_WITH_JUSTIFICATION`: AI `related_api_class` medium + deterministic ≥ 0.75
- `ESCALATE_TO_OPERATOR`: ambiguous AI signals → Tier 3
- `REJECT`: AI `unrelated` + deterministic < 0.50 → BLOCKED

**Tier 3 — Operator:** Review packet generated to `reports/backlinks/adjudication/operator_escalations.md`. Operator adds entry to `platform_canonical_overrides.yaml`. Expected volume: < 5% of REVIEW_REQUIRED.

---

## 12. KB Anchor Transition Policy (A7-03)

173 pre-P0 KB pages still show `docs.aspose.com` links ("Enterprise Documentation" suffix). These are classified `ACCEPTABLE_LEGACY_KB_PRE_P0` — not defects.

**`backlink_audit.py --kb-anchor-mode` flag:**
- `LEGACY_COMPAT_MODE` (default): pre-P0 KB links → `ACCEPTABLE_LEGACY_KB_PRE_P0` (not a failure)
- `CANONICAL_POST_P0_MODE`: pre-P0 KB links → `UPGRADE_CANDIDATE_NOT_YET_FIXED` (warning, not hard failure)

Switch to CANONICAL_POST_P0_MODE only after `--kb-upgrade` remediation pass is complete (Taskcard TC-004).

---

## 13. Deferred Capabilities

| Item | Taskcard | Reason |
|------|----------|--------|
| Docs deep matching | TC-003 | 0 deep docs URLs in `all_urls` (only family/platform landings) |
| Blog deep matching | D-04 (RWR) | Only 1 deep-blog URL; not worth infrastructure |
| Semantic matching Stage 3 | TC-001 | Requires TF-IDF corpus build |
| Products sitemap fetch | TC-002 | Products uses canonical synthesis; variants require live sitemap opt-in |
| KB anchor upgrade pass | TC-004 | 173 pre-P0 pages need `--kb-upgrade` remediation |
| `--deep` as default | RWR | Breaks v1 backward compatibility; deferred indefinitely |

---

## 14. Sprint Execution Status

From `data/backlinks/sprint_execution_proof.json`:

```
Sprint:   BL-DEEP-EXEC-v3.1-FINISH-LINE-RECOVERY
Verdict:  ACCEPTED
Tests:    249 passed, 1 skipped, 0 failed (gate ≥248 ✓)
Validators: 27/27 PASS

Pipeline results:
  P1 deep index:   1,227 endpoints (3d family)
  P2 candidates:   89 sources, 3,240 candidates, 66 AUTO_APPROVE_EXACT
  P3 authority:    66 approved, 3 REVIEW_REQUIRED, 0 BLOCKED
  A4 inventory:    176 variant URLs, 171 canonical platforms
  A4 authority:    168 approved, 4 REVIEW_REQUIRED

Pilots: 30/32 pass (1 AI_DEGRADATION_RATE_WARNING expected; 1 deferred architectural)
Content: unchanged
Push: prohibited (local only)
```

---

## 15. Operational Notes

**Refresh target map** (when aspose.com content changes):
```bash
.venv/Scripts/python scripts/pipeline/commands/ops/fetch_aspose_com_targets.py
```

**Run full audit** (v1 landing pages only):
```bash
.venv/Scripts/python scripts/pipeline/commands/ops/backlink_audit.py
```

**Run backfill dry-run** (v1):
```bash
.venv/Scripts/python scripts/pipeline/commands/ops/backlink_backfill.py --dry-run
```

**Run deep pipeline** (opt-in):
```bash
# Build layers sequentially
.venv/Scripts/python scripts/pipeline/commands/ops/backlink_build_deep_index.py --families 3d
.venv/Scripts/python scripts/pipeline/commands/ops/backlink_ai_enrich.py --family 3d --platform java
.venv/Scripts/python scripts/pipeline/commands/ops/backlink_build_candidates.py --family 3d --platform java --subdomain reference.aspose.org
.venv/Scripts/python scripts/pipeline/commands/ops/backlink_approve_authority.py --auto-only
# Run audit with deep mode
.venv/Scripts/python scripts/pipeline/commands/ops/backlink_audit.py --deep --family 3d --platform java
```

**Run all validators:**
```bash
.venv/Scripts/python scripts/pipeline/commands/ops/backlink_run_validators.py
```

**Workspace artifacts** (gitignored, regenerated each run):
```
data/backlinks/workspace/
  deep_target_index.json
  candidate_graph.json
  backlink_authority.json
  ai_enrichment_index.json
  enterprise_target_candidate_inventory.json
  platform_variant_authority.json
```

**Governance policy doc:** `docs/governance/backlink-policy.md`

**Evidence bundle:** Produced at sprint close via:
```bash
echo "EVIDENCE BUNDLE: $(git rev-parse --show-toplevel)/reports/backlinks/evidence-bundle-BL-DEEP-EXEC-v3.1.zip"
```
