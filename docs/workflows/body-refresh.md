# Body Refresh Pipeline

> Status: IMPLEMENTED (2026-06-26)
> Override token: 20260627-023723-docs-workflows-body-refresh-md
> Mission: dazzling-strolling-shell

## Overview

The body refresh pipeline closes the **first failing boundary** in the content maintenance
system: after a FOSS repository changes and `knowledge_delta.json` is produced, the body
prose of docs/KB/blog pages was previously not updated automatically. This pipeline provides
that automation.

**First failing boundary (the problem before WAVES 1-8)**:
```
knowledge_delta.json → [GAP] → docs/KB/blog body prose
```

**After WAVES 1-8**:
```
knowledge_delta.json → semantic_diff (S-104) → semantic_changes.json
                     → body_impact (S-105 input) → body_impact.json
                     → body_refresh (S-105) → updated content files + receipts/
                     → refresh_oracle (S-106) → oracle_verdicts/*.yaml
                     → locale_refresh_handoff (S-107) → locale_handoff.yaml
```

## Pipeline Scripts

| Script | Skill | Input | Output |
|--------|-------|-------|--------|
| `commands/knowledge/semantic_diff.py` | S-104 | `knowledge/{f}/{p}/merged/knowledge_delta.json` | `reports/refresh_review/{f}/{p}/semantic_changes.json` |
| `commands/content/claim_parser.py` | — | content files | claim map |
| `commands/content/body_impact.py` | — | semantic_changes.json + claim map | `body_impact.json` |
| `commands/content/body_refresh.py` | S-105 | `body_impact.json` + `semantic_changes.json` | updated files + `receipts/*.yaml` |
| `commands/content/refresh_oracle.py` | S-106 | `receipts/*.yaml` | `oracle_verdicts/*.yaml` |
| `commands/content/frontmatter_body_consistency.py` | S-108 | content files | consistency report |
| `commands/content/locale_refresh_handoff.py` | S-107 | `receipts/*.yaml` | `locale_handoff.yaml` |
| `commands/knowledge/scan_stale.py` | — | knowledge/ | stale product list |

## CLI Quick Reference

```bash
PYTHONPATH=scripts/pipeline

# Step 1: Produce typed semantic changes from knowledge delta
.venv/Scripts/python -m commands.knowledge.semantic_diff pdf net

# Step 2: Assess body impact (which pages need updating)
.venv/Scripts/python -m commands.content.body_impact pdf net

# Step 3: Dry-run to preview changes (no writes)
.venv/Scripts/python -m commands.content.body_refresh pdf net --dry-run

# Step 4: Execute (writes content files + emits receipts)
.venv/Scripts/python -m commands.content.body_refresh pdf net --execute

# Step 4a: Single-page targeted execute
.venv/Scripts/python -m commands.content.body_refresh pdf net --execute \
    --page content/docs.aspose.org/en/pdf/net/getting-started/installation.md

# Step 5: Validate refreshed content against source truth
.venv/Scripts/python -m commands.content.refresh_oracle pdf net

# Step 6: Queue locale equivalents for re-translation
.venv/Scripts/python -m commands.content.locale_refresh_handoff pdf net \
    --receipts reports/refresh_review/pdf/net/receipts/
```

## S-73 Integration

`body_refresh.py` calls `safe_content_write()` which requires an active S-73 context
for each target page. The script activates context internally by calling:

```
skill_context.py begin --skill S-73 --scope "<page_glob>"
```

The S-73 context EXPIRES after each file edit. `body_refresh.py` re-activates context
before each write. This is handled transparently by the `safe_content_write()` wrapper.

Pages with `auto_updatable: false` in frontmatter are SKIPPED unconditionally.

## Update Types

`body_refresh.py` selects one of five update strategies per impacted section:

| Update Type | When Used | Mechanism |
|-------------|-----------|-----------|
| `SURGICAL_CLAIM_REPLACEMENT` | API name changed | Regex sentence swap |
| `TABLE_ROW_RECONCILIATION` | Table row data changed | Parse markdown table, update/remove rows |
| `EXAMPLE_REGENERATION` | Code example outdated | Replace code block from snippets/ |
| `SECTION_REMOVAL` | Claim fully removed | Remove section block |
| `PARAGRAPH_REWRITE` | Semantic meaning changed | LLMRouter call_chat (CS-015) |

`PARAGRAPH_REWRITE` is the only LLM callsite. It is registered as CS-015 in
`scripts/pipeline/config/metrics_callsite_registry.yaml`.

## Preserve-First Enforcement

`body_refresh.py` enforces these non-negotiable constraints:

- NEVER rewrite sections not targeted by a specific semantic change
- NEVER remove See Also / Related Links / navigation lists
- NEVER write to pages with `auto_updatable: false`
- Validate old content hash before any write; abort if changed since body_impact.json was produced

Protected section IDs (never modified):
`see-also`, `see-also-links`, `related-links`, `related-resources`, `navigation`,
`nav`, `table-of-contents`, `contents`, `additional-resources`, `further-reading`

## Receipt Schema

Each page updated by `body_refresh.py` produces a YAML receipt in
`reports/refresh_review/{family}/{platform}/receipts/`:

```yaml
content_refresh_receipt:
  receipt_id: <uuid>
  page_path: content/docs.aspose.org/en/pdf/net/...
  source_revision: <git_sha>
  update_type: PARAGRAPH_REWRITE
  sections_updated:
    - heading: "Installation"
      old_hash: <sha256_of_old_prose>
      new_hash: <sha256_of_new_prose>
      update_type: PARAGRAPH_REWRITE
  verdict: BODY_UPDATED
  timestamp: 2026-06-27T00:00:00Z
```

Verdict values:
- `BODY_UPDATED` — write succeeded
- `SKIPPED_AUTO_UPDATABLE_FALSE` — page has `auto_updatable: false`
- `SKIPPED_HASH_CHANGED` — content changed since body_impact.json was produced
- `DRY_RUN` — dry-run mode, no write performed
- `NO_ACTIONABLE_SECTIONS` — no impacted sections found in page

## Oracle Verdict Schema

`refresh_oracle.py` produces one YAML verdict per receipted page in
`reports/refresh_review/{family}/{platform}/oracle_verdicts/`:

```yaml
refresh_oracle_verdict:
  page_path: content/docs.aspose.org/en/pdf/net/...
  source_revision: <git_sha>
  claims_checked: 24
  body_sections_checked: 5
  examples_checked: 3
  failures: []
  verdict: PASS
```

Oracle checks:
1. **Stale claim absence** — no removed API symbols remain in body
2. **API symbol validity** — every backtick API token exists in api_surface.json
3. **Frontmatter/body consistency** — format claims do not contradict each other
4. **Heading structure integrity** — no orphan H3s without parent H2
5. **Cross-page propagation** — rerun body_impact; queue any DEFINITE impacts missed

## Locale Handoff

After body updates, `locale_refresh_handoff.py` inspects receipts and queues locale
pages for re-translation:

- Changes **< 3 sentences**: route to S-75 (locale-patch) — targeted text fix
- Changes **>= 3 sentences**: route to S-56 (translate batch) — full re-translation

Output: `reports/refresh_review/{family}/{platform}/locale_handoff.yaml`

```yaml
locale_handoff:
  - source_page: content/docs.aspose.org/en/pdf/net/getting-started/installation.md
    source_revision: <git_sha>
    changed_sections: ["Installation"]
    locales_requiring_update:
      - locale: ar
        path: content/docs.aspose.org/ar/pdf/net/getting-started/installation.md
        handoff_status: QUEUED
        translate_skill: S-75
```

## Governance

This pipeline follows AGENTS.md §6a (Skill-First Execution Mandate). Each component script
is registered as a skill (S-104 through S-108) in `docs/registries/skills.md`.

Write-path enforcement:
- `body_refresh.py` uses `safe_content_write()` — requires active S-73 context per file
- Pages with `auto_updatable: false` are unconditionally skipped
- Content hash validation prevents stale overwrites

Feature flags controlling pipeline behavior are in `data/refresh-feature-flags.json`.
All 8 flags must be `true` for full pipeline operation.

## Integration with S-84 (refresh-product)

**Status (RPR-G-01, 2026-07-17): re-integrated into the CANONICAL skill source.** S-104–S-108 are
wired into `.agents/skills/refresh-product/SKILL.md` (Steps 2.5, 4, 11.7, 11.8, 14) and
`skills/refresh-product.md`, with `page-update` (S-20) demoted to the explicit fallback path — and
propagated byte-consistent to all three provider mirrors (`.agents` / `.claude` / `.kilocode`,
`sync_skills --check` = 0 drift).

> **History (do not repeat):** the original 2026-06-27 integration wired only the
> `.claude/commands/` mirrors (never the canonical `.agents/skills/` files) and was silently
> reverted on 2026-07-02 with no rationale and no backlog entry (filed retroactively as ST-028).
> That mirror-only wiring is exactly why this re-integration targets the canonical source and is
> guarded by the RPR-G-02 skill/command 3-mirror parity check + co-change enforcement, so a future
> mirror-only revert cannot silently un-integrate the pipeline again.

S-84 orchestration sequence with body refresh (per the canonical SKILL.md):
```
S-12 (knowledge-diff, baseline via S-111 resolve_baseline_sha) → S-14 (knowledge-update, S-111 ledger append)
→ S-104 (semantic-diff) → S-82 (delta-site-plan) → PIA v2 (citation-based, RPR-D-01)
→ S-105 (body-refresh — PRIMARY; S-20 page-update — FALLBACK)
→ S-83 (page-retire) | S-62 (batch-reference) | S-48 (family-sync)
→ S-106 (refresh-oracle, BLOCKING) + S-108 (frontmatter-body-consistency, BLOCKING)
→ S-114 (regression-classification, on grade delta)
→ post_refresh_verify --verify --assert-no-skipped (Checks 7/8/9/10/11 all BLOCKING)
→ S-92/S-112 (triage-verdict-gate) → S-76 (commit) → S-107 (locale-refresh-handoff, post-commit)
```

## Troubleshooting

**`knowledge_delta.json` not found**
Run `refresh_knowledge.py` for the product first. The delta file is produced as a side
effect of knowledge update, not by `semantic_diff.py`.

**Hash mismatch abort**
If `body_refresh.py` aborts with `SKIPPED_HASH_CHANGED`, content was modified after
`body_impact.json` was produced. Re-run `body_impact.py` to get fresh hashes, then
re-run `body_refresh.py`.

**Page skipped with `SKIPPED_AUTO_UPDATABLE_FALSE`**
The page has `auto_updatable: false` in frontmatter. Use S-73 (manual-edit) for
operator-directed targeted edit. Do not change the frontmatter flag without a governed
review.

**Oracle FAIL: stale claim in body**
`refresh_oracle.py` found a removed API symbol still referenced in body prose.
Run `body_refresh.py --execute` again for the specific page, or use S-73 for manual fix.

**Blocked by G-001 (uncommitted locale files)**
If 629+ uncommitted locale reference files exist in the working tree (e.g., ar/bg/ca
pdf/net), commit those first via S-76 before running any S-84 refresh that would add
new commits. Mixing uncommitted locale files with refresh commits causes dirty-tree errors.
