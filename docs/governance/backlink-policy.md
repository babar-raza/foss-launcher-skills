# Enterprise Backlink Policy
Version: 1.0.0
Sprint: BL-DEEP-EXEC-2026-05-27

## 1. Three-Layer Model

All enterprise backlinks are produced by a three-layer pipeline. Each layer has a strict
read/write boundary:

```
Layer 1: Verified Endpoint Inventory
  Source: data/aspose_com_targets.json (all_urls index, HTTP 200 verified)
  Script: backlink_build_deep_index.py
  Output: data/backlinks/workspace/deep_target_index.json (gitignored)
  Read by: Layer 2 only

Layer 2: Intelligent Candidate Graph
  Source: Layer 1 + content/ frontmatter
  Script: backlink_build_candidates.py
  Output: data/backlinks/workspace/candidate_graph.json (gitignored)
  Read by: Layer 3 only

Layer 3: Approved Backlink Authority
  Source: Layer 2
  Script: backlink_approve_authority.py
  Output: data/backlinks/workspace/backlink_authority.json (gitignored)
  Read by: Resolver (backlink_targets.py) only

Resolver: backlink_targets.py
  Reads: Layer 3 (when --deep enabled) + v1 target map (always)
  Returns: (url, type, subdomain, reason)
  Read by: backfill only

Backfill: backlink_backfill.py
  Reads: Resolver output only
  Writes: content/ files (with appropriate guardrails)
```

## 2. Approved-Authority-Only Rule

**Agents and scripts MUST NOT construct enterprise URLs manually.**

All enterprise links must come from one of:
- The verified target map (v1 landing-page fallback chain)
- An approved entry in `data/backlinks/workspace/backlink_authority.json`
  with `allowed_for_generation: true`

Guessing, composing, or interpolating enterprise URLs is forbidden.
Pattern `f"https://{subdomain}.aspose.com/..."` is only permitted inside
`_resolve_deep()` in `backlink_targets.py`.

## 3. Fail-Closed Behavior

When the deep authority is unavailable, stale, or has a hash mismatch, the
resolver returns `None` and falls back to the v1 landing-page chain. It does
NOT raise an error or block content rendering.

Conditions that trigger fail-closed fallback:
- `backlink_authority.json` missing
- `target_index_hash` in authority does not match Layer 1 hash (stale index)
- `anchor_config_hash` does not match current `anchor_text_registry.yaml` hash
- Authority record has `allowed_for_generation: false`
- Authority record is for REVIEW_REQUIRED or BLOCKED decision

## 4. Deep Mode is Opt-In

`--deep` flag enables deep authority resolution. Default is always v1 landing-page only.

```bash
# Default (v1 only):
backlink_backfill.py --family words --platform python

# Deep mode (uses Layer 3 authority when available):
backlink_backfill.py --family words --platform python --deep
```

`exact_deep_match_enabled=False` is the permanent default in `resolve_backlink()`.

## 5. No Manual URL Construction

Agents writing or editing content files MUST NOT:
- Hand-write enterprise link URLs in See Also sections
- Interpolate family/platform variables to construct enterprise URLs
- Copy-paste enterprise URLs from browser or documentation
- Modify existing anchor text in See Also or Related Resources sections

All such links must flow through the verified pipeline above.

## 6. Anchor Text Policy

Anchor text for enterprise links is determined by `anchor_text_registry.yaml`.
The rendered text is stored in `backlink_authority.json` as `rendered_anchor_text`.
Backfill reads this stored value -- it never re-renders anchors at insertion time.

Page-specific anchor exceptions require an approved entry in
`data/backlinks/anchor_overrides.yaml` with `reason` and `evidence` fields.

## 7. Evidence Requirements

Every approved authority record stores:
- `source_hash` -- hash of source page at approval time
- `target_index_hash` -- hash of Layer 1 at approval time
- `anchor_config_hash` -- hash of `anchor_text_registry.yaml` at approval time
- `policy_version` -- approval policy version
- `approved_at` -- ISO 8601 timestamp
- `freshness_status` -- FRESH / AGING / STALE

Authority is automatically invalidated (fail-closed) when any input hash changes.

## 8. Staleness Policy

| Condition | Behavior |
|-----------|----------|
| Map age < 90 days | FRESH -- full confidence |
| Map age 90-180 days | AGING -- allowed with freshness_warning: true |
| Map age > 180 days | STALE -- allowed_for_generation: false, must rebuild |
| Hash mismatch (any) | Fail-closed to v1 fallback |

## 9. Audit and Compliance

Run `backlink_audit.py` to check compliance:
```bash
# Standard audit (v1 only):
.venv/Scripts/python scripts/pipeline/commands/ops/backlink_audit.py

# Deep audit (includes deep authority):
.venv/Scripts/python scripts/pipeline/commands/ops/backlink_audit.py --deep
```

Audit statuses are defined in `scripts/pipeline/lib/backlink_targets.py`.

## 10. KB Anchor Transition

KB pages currently link to `docs.aspose.com` (pre-P0 legacy). After the P0 fix,
new KB insertions link to `kb.aspose.com` with "Enterprise Knowledge Base" anchor text.

During transition (LEGACY_COMPAT_MODE, default):
- Pre-P0 KB pages with `docs.aspose.com` links: `ACCEPTABLE_LEGACY_KB_PRE_P0`
- Post-P0 KB pages with `kb.aspose.com` links: `CANONICAL_KB_POST_P0`

Remediation of legacy KB anchors: see `reports/backlinks/taskcards/TC-004-kb-anchor-upgrade.md`.
