<!-- CONTRACT: agent-executed
     purpose: independent-agent review gate for pending SEO frontmatter recommendations —
              replaces the "human review" bottleneck with a bounded, fresh-context agent
              decision table, modeled directly on S-90 (publish-readiness-review)
     preconditions: reports/seo/safe_recommendations.json exists (produced by safety.py);
                    invoked as a FRESH agent/session context with no memory of the
                    recommend.py generation step that produced the candidates under review
     postcondition: patches/seo/patch_manifest.json updated with requires_human_review:false
                    for every APPROVED page; REJECTED pages recorded with a reason, never
                    silently dropped; AMBIGUOUS pages routed to real human escalation per
                    AGENTS.md §7c/§8 (narrow — legal/brand/license claims only)
     idempotent: no — re-running re-reviews the current safe_recommendations.json snapshot
     verified: 2026-07-29
     id: S-116
     depends_on: [S-90]
-->
# S-116: SEO Review — Independent-Agent Review Gate for Pending SEO Recommendations

**Arguments**: $ARGUMENTS
Expected format: `[--level HIGH|MEDIUM|LOW|all] [--site <site>] [--family <family>] [--limit <N>]`
Default: review MEDIUM + HIGH opportunities, all sites.

## Purpose

Load `safe_recommendations.json`, independently re-verify each proposed `description`/
`keywords`/`seoTitle` change against a bounded decision table, then write approved
patches to `patches/seo/patch_manifest.json` with `requires_human_review: false` —
unblocking `apply.py`'s now-real enforcement of that flag (SEO-APPLY-HARDEN).

**This is not a "wait for a human" skill.** Per AGENTS.md §7c, "human review required"
means an agent performs bounded inspection, judgment, and a final verdict — the same
doctrine S-90 (`publish-readiness-review`) already applies to content grading. S-116
applies it to SEO recommendations specifically. Real human escalation is reserved for
the narrow conditions in §7c/§8 (legal/license/business claims requiring external
verification) — everything else is decided here, by this skill, not deferred.

**Independence is a procedural precondition, not a suggestion.** This skill MUST be
invoked as a fresh agent/session context with no conversation memory of the
`recommend.py` run that generated the candidates it is reviewing — the same principle
this repo's own forensic-review passes use to avoid a reviewer re-confirming its own
prior work instead of actually checking it. If the invoking session authored the
recommendations under review, spawn a separate agent (e.g. via the Agent tool) to run
this skill instead of reviewing inline.

## Pre-conditions

1. `reports/seo/safe_recommendations.json` exists (produced by `scripts/seo/pipeline/safety.py`).
   ```bash
   ls reports/seo/safe_recommendations.json 2>/dev/null || echo "MISSING — run the pipeline through safety.py first"
   ```
2. The reviewing context is independent of the generating context (see above).

## Steps

> **Skill context gate** — run before step 1:
> ```bash
> PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/commands/governance/skill_context.py begin --skill S-116 --scope "patches/seo/*"
> ```

### 1. Locate and load inputs

```bash
RECS_PATH="reports/seo/safe_recommendations.json"
ls "$RECS_PATH" 2>/dev/null || echo "MISSING — run pipeline first"
```

Load `safe_recommendations.json`. Filter based on `$ARGUMENTS`:
- Default: `opportunity_level` in {MEDIUM, HIGH}
- `--level LOW` / `--level all`: as named
- `--site <site>` / `--family <family>` / `--limit <N>`: scope as named

Skip pages where `safety_checks_passed=False` or every field's `proposed` value is null.

### 2. Independent decision table

For each candidate page, evaluate every row below. All rows must pass for **APPROVE**;
any deterministic-row failure is **REJECT** (no escalation — these are mechanical);
a failed grounding check is **REJECT** if clearly fabricated, or **ESCALATE** if
genuinely ambiguous (see Step 4).

| Check | Kind | On fail |
|---|---|---|
| Length bounds (`seoTitle` 50-70 chars, `description` 130-160 chars — `safety.py`'s own thresholds) | Deterministic | REJECT |
| Template conformance — call `title_templates.check_conformance(title, page_type, family=..., platform=..., class_name=..., category=...)` (`scripts/seo/pipeline/title_templates.py`) against the live `scripts/pipeline/config/title_templates.yaml` registry. If the page's `page_type` has no registered entry yet, this row does not apply — record SKIP (not REJECT) and continue to the next row | Deterministic | REJECT (SKIP if `page_type` unregistered) |
| Duplicate check — the proposed title must not collide with an already-`APPROVE`d sibling in this same review batch, AND must not appear as an existing key in `check_duplicate_titles.find_duplicate_titles()`'s live result (`scripts/ci/checks/check_duplicate_titles.py`) unless it is identical to the page's own current title (i.e. not a NEW collision this patch would introduce). The tool's checked-in baseline (`scripts/ci/config/duplicate_titles_baseline.json`) grandfathers 1,097 pre-existing groups — this row is about new collisions this recommendation would create, not that pre-existing debt | Deterministic | REJECT |
| Evidence-block immutability (patch touches nothing under `evidence:`) | Deterministic | REJECT |
| Claim/format grounding — **independently re-verified against `knowledge/{family}/{platform}/merged/claims.json` and `formats.json`, not the generating step's own citation** | Agent judgment | REJECT if fabricated; ESCALATE if genuinely ambiguous |
| `auto_updatable` (skip entirely, never even reaches APPROVE/REJECT — filtered upstream by `apply.py`, but double-check here as defense in depth) | Deterministic | SKIP (not a rejection — expected) |

A query string is evidence of **demand**, never evidence that a claim is **true**. A
recommendation whose wording implies a capability not present in `claims.json`/
`formats.json` is REJECT, full stop — it does not matter how much search volume the
underlying query has.

**Google may substitute the snippet.** Approving a `seoTitle`/`description` here and
`apply.py` publishing it does not guarantee Google's search results display that exact
text — Google frequently generates its own title or snippet from page content when it
judges the supplied one less relevant to a specific query. This is expected, documented
behavior on Google's side, not a pipeline defect. Contract H's post-publication
observation window (`SEO-METADATA-OBSERVATION-LOOP` — not yet shipped as of this
writing; see `registry.yaml`) will therefore need to measure the real, observable
outcome (position/CTR), never whether the literal string survived unedited — a flat or
negative result can mean Google substituted the snippet, not that this review's decision
was wrong. Do not treat "Google rewrote it" as a finding against this skill's APPROVE
decisions; it is a known, unavoidable characteristic of the channel being optimized.

### 3. Present the decision record

For each page, record (not just print — this becomes the evidence trail):

```
Page: content/products.aspose.org/en/3d/_index.md
Level: MEDIUM | Site: products.aspose.org | Family: 3d
Field: description
  Current : "..."
  Proposed: "..."
  Length check: PASS (145 chars)
  Grounding check: PASS (traces to CLM-042, formats.json entry for glTF)
Decision: APPROVE
```

### 4. Real human escalation (narrow — do not over-use)

Escalate only when:
- Grounding is genuinely ambiguous after checking `claims.json`/`formats.json` directly
  (not "I'm not sure" without having checked — check first, then escalate only if the
  artifacts themselves don't resolve it)
- The recommendation makes a legal, license, or business claim requiring external
  verification (AGENTS.md §8)

Every other case is decided by this skill. Do not escalate to avoid making a call the
decision table above already equips you to make.

### 5. Write the patch manifest

Write approved patches to `patches/seo/patch_manifest.json`:

```json
{
  "batch_id": "<ISO-timestamp>",
  "generated_at": "<YYYY-MM-DD>",
  "reviewed_by": "S-116 (independent-agent review)",
  "total_patches": N,
  "patches": [
    {
      "page_path": "content/...",
      "fields_to_update": {
        "seoTitle": "<value or omit if not writable on this site>",
        "description": "<value or omit>",
        "keywords": ["term1", "term2"]
      },
      "requires_human_review": false,
      "safety_checks_passed": true,
      "decision_record": "APPROVE — length PASS, grounding traces to CLM-042"
    }
  ]
}
```

Only include `fields_to_update` entries with a non-null proposed value. Never include
`tags_to_add` — that field is retired (SEO-APPLY-HARDEN, Finding #16). Set
`requires_human_review: false` only for pages that reached APPROVE in Step 2 — REJECTed
and ESCALATEd pages must NOT appear in the manifest with `false`.

### 6. Verify the manifest

```bash
.venv/Scripts/python -c "
import json
m = json.load(open('patches/seo/patch_manifest.json'))
print(f'batch_id: {m[\"batch_id\"]}')
print(f'total_patches: {m[\"total_patches\"]}')
for p in m['patches'][:5]:
    fields = p['fields_to_update']
    print(f'  {p[\"page_path\"]} | fields={list(fields.keys())} | review={p[\"requires_human_review\"]}')
"
```

### 7. Dry-run apply

```bash
.venv/Scripts/python scripts/seo/pipeline/apply.py --dry-run
```

Confirm output shows exactly the approved changes, and that `apply.py`'s own governance
gates (Finding #2/#5/#6, SEO-APPLY-HARDEN) don't flag anything this review already
decided — if they do, that's a real disagreement between this skill's decision and
`apply.py`'s independent enforcement, and must be investigated before proceeding, not
silently overridden by either side.

### 8. Report session summary

Print: pages reviewed, APPROVE/REJECT/ESCALATE counts (with reasons), patches written,
next step (`apply.py` without `--dry-run`).

> **Skill context close** — run after the last step:
> ```bash
> PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/commands/governance/skill_context.py end --skill S-116 --status completed
> ```

## Safety constraints (unchanged from the pre-registration draft, now enforced twice — here AND in apply.py)

- NEVER modify `evidence:`, `model_sha`, `claims`, `apis`, `formats` frontmatter
- NEVER approve a recommendation containing a capability/format claim absent from
  `claims.json`/`formats.json`
- NEVER approve `description` outside 130-160 chars, or `seoTitle` outside 50-70 chars
- ONLY write to `patches/seo/patch_manifest.json` — never modify content files directly
  (that is `apply.py`'s job, gated separately)
- If `model.yaml.stale_since != null` for the page's family/platform, flag and skip

## Post-conditions

- `patches/seo/patch_manifest.json` exists with `total_patches > 0` (if any page was APPROVEd)
- Every entry has `requires_human_review: false` set only after passing Step 2 in full
- No entry modifies evidence blocks or body content
- Every REJECT/ESCALATE decision is recorded somewhere (session output at minimum),
  never silently dropped

## Error handling

| Error | Cause | Fix |
|-------|-------|-----|
| `safe_recommendations.json` missing | Pipeline not run through `safety.py` | Run `validate.py` → `inventory.py` → `map_url.py` → `analyze.py` → `recommend.py` → `safety.py` first |
| Reviewing session authored the recommendations | Independence precondition violated | Spawn a fresh agent context to run this skill instead |
| `apply.py --dry-run` flags something this review approved | Real disagreement between S-116 and `apply.py`'s independent gates | Investigate before proceeding — do not override either side without understanding why they disagree |

## Composition (skills invoked internally)

None directly — this skill is invoked standalone, downstream of the `scripts/seo/`
pipeline's deterministic stages (`validate.py` through `safety.py`), and upstream of
`apply.py` (a script, not itself a registered skill in this repo's skill system).
