# Enterprise Backlink Policy

> **Version:** 1.0.0
> **Status:** ACTIVE
> **Sprint:** POST-BL-DEEP-HARDEN-2026-06-02 (wiggly-watching-finch)
> **Authoritative location:** `docs/governance/backlink-policy.md`
> All 15 skill governance blocks reference this file.

---

## 1. Three-Layer Architecture

The backlink system operates in three verified layers. No URL ever enters content pages
without passing through all applicable layers.

```
Layer 1    Verified Endpoint Inventory (deep_target_index.json)
           All enterprise URLs confirmed HTTP 200. No guessing.

Layer 1.5  AI-Enriched Metadata Index (ai_enrichment_index.json)
           LLM/embedding classification of Layer 1 URLs.
           ADVISORY ONLY — AI is never authority for link selection.

Layer 2    Intelligent Candidate Graph (candidate_graph.json)
           Multiple ranked candidates per source page.
           Still not authoritative — adjudication required.

Layer 3    Approved Backlink Authority (backlink_authority.json)
           Exactly ONE canonical target per (source_key, link_slot), or BLOCKED.
           This is the only source the Resolver reads.
```

**Invariant:** The Resolver (`backlink_targets.py`) reads Layer 3 only.
It never reads Layer 1, Layer 2, or Layer 1.5.

---

## 2. Approved-Authority-Only Insertion Rule

> **All enterprise links in content pages must originate from the approved authority.**

- Backfill (`backlink_backfill.py`) reads Resolver output only.
- Resolver reads `backlink_authority.json` (Layer 3) only.
- No script, agent, or human may construct or embed an enterprise URL directly.
- No URL may be inferred, interpolated, or synthesized from a pattern.
- `allowed_for_generation: true` must be set in the authority record before a link is insertable.

**Violation:** Manually inserting an enterprise URL in a content file (e.g., via Edit tool)
without going through the Resolver/Backfill pipeline is a policy violation regardless of
whether the URL appears valid.

---

## 3. Fail-Closed to v1 Fallback Behavior

When `--deep` is not specified (default), the system operates in v1 mode:

- Resolver calls `resolve_backlink()` with `exact_deep_match_enabled=False`.
- Only platform-level (`{family}/{platform}`) and family-level (`{family}/`) landing pages
  are eligible targets.
- Deep reference class matching, KB article matching, and anchor text config registry are
  all disabled.
- v1 behavior is byte-identical to the pre-v3 system.

**Purpose:** Any skill invoked without `--deep` cannot accidentally insert deep links.
Deep authority is opt-in, never default.

---

## 4. `--deep` Is Opt-In Only

Deep backlink matching (Layer 3, exact reference class resolution) is enabled exclusively via
explicit `--deep` flag on `backlink_backfill.py`.

Skills that support deep mode must document this explicitly and require the `--deep` flag to be
passed by the operator. No skill activates deep mode automatically based on content type.

Current skills supporting `--deep`: `batch-reference`, `batch-remediate`, `content-enrich`,
`page-update`, `refresh-product`, `heal-page`, `launch-product`.

---

## 5. No Manual URL Construction

> **Prohibited:** Writing enterprise URLs (`aspose.com/...`) directly into content frontmatter
> or markdown body.

This prohibition applies to:
- Human editors using the Edit tool
- Agent-executed skill paths
- Template generation scripts
- Any automated pipeline that does not go through `backlink_backfill.py`

**Rationale:** Enterprise URL structure changes over time. Hard-coded URLs become stale and
fail silently. Only the verified target map (`data/aspose_com_targets.json`) and approved
authority (`backlink_authority.json`) guarantee that inserted URLs resolve to HTTP 200 pages.

---

## 6. Evidence Requirements for Authority Records

Every record in `backlink_authority.json` must have:

| Field | Required | Description |
|-------|----------|-------------|
| `target_path` | Yes | Relative path on aspose.com (not full URL) |
| `target_subdomain` | Yes | Enterprise subdomain (e.g., `reference.aspose.com`) |
| `decision` | Yes | `AUTO_APPROVE_EXACT` or `REVIEW_REQUIRED` |
| `allowed_for_generation` | Yes | `true` only for records cleared for insertion |
| `approved_at` | Yes | ISO 8601 timestamp of approval |
| `policy_version` | Yes | Must match current policy version (e.g., `1.0.0`) |
| `source_hash` | Yes | SHA of source content file at time of approval |
| `target_index_hash` | Yes | SHA of Layer 1 index used during approval |
| `anchor_template_id` | Required if deep | ID from `anchor_text_registry.yaml` |
| `rendered_anchor_text` | Required if deep | Pre-rendered; Backfill reads this field directly |

Records with `decision: REVIEW_REQUIRED` must not have `allowed_for_generation: true` without
explicit human approval (see Tier 3 adjudication workflow in `docs/backlinks-v3-reference.md`).

---

## 7. Staleness Policy

### Target Map (`data/aspose_com_targets.json`)

- **Recommended refresh interval:** 30 days
- **Hard maximum:** 90 days before authority records using the map are considered stale
- **Staleness indicator:** `target_map_hash` in authority records no longer matches the
  current map's SHA-256
- **Effect:** V7 validator reports informational mismatch; no content blocking until >90 days
- **Resolution:** Run Layer 1→3 rebuild pipeline (see §8)

### Authority Records

- Records become stale when `source_hash` no longer matches the current content file SHA.
- Stale records are not deleted automatically — they remain with their last `decision`.
- Re-approval is required before stale records can be used for new insertions.

---

## 8. Authority Rebuild SOP

Run this sequence whenever the target map is refreshed or significant content changes occur:

```bash
# Step 1: Refresh target map (requires network)
PYTHONPATH=scripts/pipeline .venv/Scripts/python \
  scripts/pipeline/commands/ops/fetch_aspose_com_targets.py

# Step 2: Rebuild Layer 1 (deep target index)
PYTHONPATH=scripts/pipeline .venv/Scripts/python \
  scripts/pipeline/commands/ops/backlink_build_deep_index.py

# Step 3: Rebuild Layer 2 (candidate graph) — reference subdomain, no AI for speed
PYTHONPATH=scripts/pipeline .venv/Scripts/python \
  scripts/pipeline/commands/ops/backlink_build_candidates.py \
  --subdomain reference.aspose.org --no-ai

# Step 4: Approve authority (auto-only tier)
PYTHONPATH=scripts/pipeline .venv/Scripts/python \
  scripts/pipeline/commands/ops/backlink_approve_authority.py --auto-only

# Step 5: Dry-run backfill to inspect changes before writing
PYTHONPATH=scripts/pipeline .venv/Scripts/python \
  scripts/pipeline/commands/ops/backlink_backfill.py \
  --deep --subdomain reference.aspose.org --dry-run
```

Only after dry-run review: re-run Step 5 without `--dry-run` to apply.

**Gate:** Zero false positives in dry-run output before live execution.
**Gate:** `target_map_hash` in rebuilt authority matches `sha256(data/aspose_com_targets.json)`.

---

## 9. Anchor Text Governance

- Anchor texts must not be hand-written, improved, or modified during content edits.
- All anchor text comes from the approved config pipeline (`anchor_text_registry.yaml`).
- Page-specific wording requires an approved entry in `data/backlinks/anchor_overrides.yaml`.
- Backfill reads `rendered_anchor_text` from the authority record directly — it never calls
  `render_anchor_text()` at insertion time.

---

## 10. Compliance Check Commands

```bash
# Audit compliance of content files
PYTHONPATH=scripts/pipeline .venv/Scripts/python \
  scripts/pipeline/commands/ops/backlink_audit.py \
  --subdomain reference.aspose.org

# Validate authority record structure
PYTHONPATH=scripts/pipeline .venv/Scripts/python \
  scripts/pipeline/commands/ops/backlink_approve_authority.py --validate-only

# Run all 27 backlink validators
PYTHONPATH=scripts/pipeline .venv/Scripts/python \
  scripts/pipeline/commands/ops/backlink_validate_all.py
```

---

## 11. Same-Section Mapping Table (§4.1)

Each source subdomain resolves to a specific same-section target on aspose.com.
Cross-section fallback to `products.aspose.com` is **prohibited** except for
`products.aspose.org` (self-referential). Wrong-section links are worse than no link.

| Source | Preferred target | Resolution strategy | Cross-section fallback |
|---|---|---|---|
| `docs.aspose.org` | `docs.aspose.com` | platform → family lookup | BLOCKED (no products fallback) |
| `kb.aspose.org` | `kb.aspose.com` | platform → family lookup | BLOCKED |
| `reference.aspose.org` | `reference.aspose.com` | platform → family lookup | BLOCKED |
| `products.aspose.org` | `products.aspose.com` | platform → family lookup | products self-fallback |
| `blog.aspose.org` | `blog.aspose.com` | ancestor chain (ROOT_FALLBACK) | BLOCKED |

---

## 12. blog.aspose.org Resolution Policy

`blog.aspose.com` has no family/platform structured landing pages. The only
HTTP-200-verified URL is the root `https://blog.aspose.com/`.

- Resolution uses `resolve_best_verified_ancestor("blog/{family}/{platform}", target_map)`.
- Always resolves to ROOT_FALLBACK `https://blog.aspose.com/` (HTTP 200 verified).
- Anchor text: `{fam} — Enterprise Blog` (template: `blog-family`).
- Sentence wrapper: "For enterprise tutorials, see {anchor}."
- If `blog.aspose.com` adds category pages (`/pdf/`, `/cells/` etc.) in future, the
  ancestor chain will find them automatically — no code change required.

---

## 13. Prose Integration Policy

Near-duplicate detection and prose validation run on every backfill injection:

- `_detect_near_duplicate(existing_text, candidate_sentence)` — Jaccard similarity
  ≥ 0.65 (after URL-stripping, excluding Aspose.*/Enterprise* tokens and noise words).
  Detection records a `NEAR_DUPLICATE_DETECTED` warning in `BackfillChange.warning_messages`.
  Warning does NOT suppress injection — the link is still inserted.
- `_validate_prose(section_text, entry, target_url)` — after injection, confirms:
  - Entry anchor text substring is present in section text.
  - Target URL is present unchanged.
  - No duplicate bullet for the same target URL.
  Errors are appended to `BackfillChange.warning_messages`.
- `_validate_llm_output(original, updated, target_url, anchor_text)` — for YAML
  overview updates, validates anchor presence, URL presence, retained prose ratio ≥ 0.80,
  and absence of prohibited phrases (industry-leading, best-in-class, only solution, guarantee).
- Warning messages are recorded in `BackfillChange.warning_messages`; they do **not**
  suppress the injection. Review warnings after each backfill run.

---

## Related Documents

- `docs/backlinks-v3-reference.md` — Full architecture, layer scripts, invariants
- `data/backlinks/` — Config registries (YAML/JSON, committed)
- `data/backlinks/workspace/` — Runtime artifacts (gitignored, never committed)
- `schemas/backlinks/` — 10 JSON schemas for authority and config validation
- `scripts/pipeline/lib/backlink_targets.py` — Resolver implementation
- `scripts/pipeline/commands/ops/backlink_*.py` — Pipeline scripts
