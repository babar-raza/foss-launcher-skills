---
name: truth-audit-content
id: S-85
description: >
  Decompose all English content pages for a family/platform into reviewable units, verify
  each unit against the knowledge model, and produce a structured gap ledger with stable
  finding IDs and evidence chains. Read-only — never modifies content.
args: "{family} {platform} [--scope all|docs|blog|kb|reference] [--no-llm] [--max-units N] [--unit-types H,P,C,T,L]"
---

# S-85: Truth Audit Content — Line-Level Content Truth Audit

**Arguments**: $ARGUMENTS
Expected format: `{family} {platform} [--scope all|docs|blog|kb|reference] [--no-llm] [--max-units N] [--unit-types H,P,C,T,L]`

## Purpose

Decompose all English content pages for a family/platform into individually addressable reviewable
units (headings, paragraphs, code blocks, table rows, list items), verify each unit against the
knowledge model, and produce a structured gap ledger with stable finding IDs and evidence chains.
**Read-only — never modifies content.**

This skill fills the gap between S-90 (member-level API token verification) and page-level
publishability checks by providing line-level truth verification with defect origin classification.

## Pre-conditions

1. `knowledge/{family}/{platform}/merged/api_surface.json` must exist
2. `knowledge/{family}/{platform}/merged/model.yaml` `stale_since` must be null
3. At least one content page must exist for the family/platform

> **Optional context gate** — if `scripts/skill_context.py` exists, run before step 1:
> ```bash
> python scripts/skill_context.py begin --skill S-85 --scope "*"
> ```

## Steps

### Step 1: Run the audit

If `scripts/truth_audit_content.py` exists:

Full run (all configured site sections):
```bash
python scripts/truth_audit_content.py {family} {platform} --scope all
```

Quick pilot (single site section, limited units):
```bash
python scripts/truth_audit_content.py {family} {platform} --scope docs --max-units 200
```

With JSON output:
```bash
python scripts/truth_audit_content.py {family} {platform} --json
```

If the script does not exist, proceed to manual agent-executed verification (Step 1a).

#### Step 1a: Manual agent-executed verification (when script absent)

1. Read `config.yaml sites` to determine content paths for `{family}/{platform}`
2. Glob all `.md` files under those content paths
3. For each file, decompose into reviewable units (see Content Decomposition below)
4. Verify each unit against knowledge files (see Verification Tiers below)
5. Accumulate findings into the gap ledger format

### Step 2: Review output

- **Gap ledger (JSON)**: `reports/truth-audit/{family}-{platform}-{date}.json`
- **Human report (Markdown)**: `reports/truth-audit/{family}-{platform}-{date}.md`
- **State file (delta tracking)**: `reports/truth-audit/state/{family}-{platform}.json`

### Step 3: Interpret verdicts

| Verdict | Meaning | Action |
|---------|---------|--------|
| VERIFIED | Unit confirmed by knowledge model | None |
| UNVERIFIABLE | Evidence insufficient | Review manually if critical |
| UNSUPPORTED | No evidence found | Investigate; may need fixing |
| CONTRADICTED | Evidence contradicts unit | Must fix before publication |
| FABRICATED | Unit references nonexistent API/class | Must fix before publication |

### Step 4: Review defect origins

| Origin | Meaning | Remediation |
|--------|---------|-------------|
| KNOWLEDGE_GAP | Source has it, knowledge doesn't | Re-run `/repo-scout` then `/knowledge-update` |
| GENERATION_FABRICATION | Content invented something | Fix via `/manual-edit` or `/heal-page` |
| EVALUATOR_MISS | Wrong content passed evaluators | File skill gap report |
| SCOUT_MISS | Scout didn't extract from source | Re-run `/repo-scout` with enhanced extraction |
| ENRICHMENT_HALLUCINATION | Enriched claim contradicts source | Re-run `/knowledge-enrich` |

### Step 5: Act on findings

- **CONTRADICTED/FABRICATED findings**: Route to `/manual-edit` (S-73) or `/heal-page` (S-26)
- **UNSUPPORTED findings**: Investigate; route to `/manual-edit` if confirmed false
- **KNOWLEDGE_GAP / SCOUT_MISS origins**: Re-run knowledge pipeline first, then re-audit

> **Optional context close** — if `scripts/skill_context.py` exists, run after the last step:
> ```bash
> python scripts/skill_context.py end --skill S-85 --status completed
> ```

## Knowledge Files to Load

1. `knowledge/{family}/{platform}/merged/api_surface.json` — API surface
2. `knowledge/{family}/{platform}/merged/claims.json` — enriched claims
3. `knowledge/{family}/{platform}/merged/formats.json` — format support (if present)
4. `knowledge/{family}/{platform}/merged/index.json` — forbidden_claims, classes
5. `knowledge/{family}/{platform}/merged/model.yaml` — version, SHA, stale_since

## Content Decomposition

Each page is split into reviewable units:

| Unit type | Code | What it captures |
|-----------|------|-----------------|
| Heading | H | Section headings (`## Title`) |
| Paragraph | P | Contiguous prose blocks |
| CodeBlock | C | Fenced code blocks (``` delimited) |
| TableRow | T | Pipe-delimited table rows |
| ListItem | L | Bullet or numbered list items |

Each unit gets a stable ID: `U-{family}-{platform}-{path_sha4}-L{line}-{type}`

## Verification Tiers

- **Tier 1 (deterministic)**: Forbidden claim matching, API token verification against api_surface.json, format claim verification, claim token overlap
- **Tier 2 (source grep, optional)**: If source FOSS repo code is available locally, search it for key identifiers from the unit; record file:line evidence. Skip this tier if source is not locally available.
- **Tier 3 (LLM, optional)**: Semantic verification for units that remain UNVERIFIABLE after Tier 1+2. Disabled if `--no-llm` passed.

## Output Format

### Gap Ledger JSON

Key sections in `reports/truth-audit/{family}-{platform}-{date}.json`:
- `summary`: verdict counts, verification rate, defect rate
- `files`: per-file verdict breakdown
- `units`: every decomposed unit with verdict, evidence chain, and defect origin
- `findings`: UNSUPPORTED/CONTRADICTED/FABRICATED units as actionable findings
- `defect_summary`: counts per defect origin code
- `delta`: fixed/new/regression/unchanged counts vs prior run

### Finding ID format

`F-{family}-{platform}-{type_code}-{sha8}` — stable across reruns for the same content location.

## Post-conditions

1. `reports/truth-audit/{family}-{platform}-{date}.json` written
2. `reports/truth-audit/{family}-{platform}-{date}.md` written
3. `reports/truth-audit/state/{family}-{platform}.json` updated (delta tracking)
4. **No content files modified** — this is a read-only audit skill

## Exit Codes

- `0`: All units VERIFIED or UNVERIFIABLE (no defects found)
- `1`: Internal error
- `2`: One or more CONTRADICTED or FABRICATED units found

## Relationship to Other Skills

| Skill | Layer | What it catches | This skill adds |
|-------|-------|----------------|-----------------|
| S-90 truth-audit | Member-level API | Fabricated methods/properties | Line-level decomposition, all site sections, evidence chains |
| S-32 content-audit | Paragraph-level knowledge | Claims contradicting claims.json | Per-unit granularity, defect origin classification |
| S-23 ground-check | Structure-level | Frontmatter, file paths | Truth verification (not structure) |

## Re-run Policy

- Idempotent: same content + same knowledge SHA = same findings (except timestamps)
- Delta tracking: re-run after fixes shows prior findings as `fixed`, new findings as `new`
- Finding IDs are stable across reruns for the same content location

## Failure Modes

| Condition | Behavior |
|-----------|----------|
| Knowledge not found | Exit 1 with error |
| Knowledge stale | Exit 1 with error |
| No content files for scope | Exit 1 with error |
| max-units reached | Stop processing; report partial results |
