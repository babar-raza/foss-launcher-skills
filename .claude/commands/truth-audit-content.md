# S-85: Truth Audit Content — Line-Level Content Truth Audit

**Arguments**: $ARGUMENTS
Expected format: `{family} {platform} [--scope all|products|docs|blog|kb|reference] [--no-llm] [--max-units N] [--unit-types H,P,C,T,L]`

## Purpose

Decompose all English content pages for a family/platform into individually addressable reviewable units (headings, paragraphs, code blocks, table rows, list items), verify each unit against the clone cache and knowledge model, and produce a structured gap ledger with stable finding IDs and evidence chains. **Read-only — never modifies content.**

This skill fills the gap between S-38 (member-level API token verification) and S-43 (page-level publishability verdict) by providing line-level truth verification with defect origin classification.

## Pre-conditions

1. Clone cache must exist at `runs/.clone_cache/aspose_{family}_{platform}/` (Tier 2 grep disabled if absent)
2. `knowledge/{family}/{platform}/merged/api_surface.json` must exist
3. `knowledge/{family}/{platform}/merged/model.yaml` `stale_since` must be null
4. Knowledge bootstrap must have been run (DAR: S-54)

## Steps

> **Skill context gate** — run before step 1:
> ```bash
> PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/commands/governance/skill_context.py begin --skill S-85 --scope "*"
> ```


### Step 1: Run the audit

```bash
cd scripts/pipeline
.venv/Scripts/python truth_audit_content.py {family} {platform} --scope {scope}
```

Full run (all 5 subdomains):
```bash
.venv/Scripts/python scripts/pipeline/commands/diagnostics/truth_audit_content.py {family} {platform} --scope all
```

Quick pilot (single subdomain, limited units):
```bash
.venv/Scripts/python scripts/pipeline/commands/diagnostics/truth_audit_content.py {family} {platform} --scope docs --max-units 200
```

With JSON output to stdout:
```bash
.venv/Scripts/python scripts/pipeline/commands/diagnostics/truth_audit_content.py {family} {platform} --json
```

### Step 2: Review output

- **Gap ledger (JSON)**: `reports/truth-audit/{family}-{platform}-{date}.json`
- **Human report (Markdown)**: `reports/truth-audit/{family}-{platform}-{date}.md`
- **State file (delta tracking)**: `reports/truth-audit/state/{family}-{platform}.json`

### Step 3: Interpret verdicts

| Verdict | Meaning | Action |
|---------|---------|--------|
| VERIFIED | Unit confirmed by clone cache + knowledge | None |
| UNVERIFIABLE | Evidence insufficient | Review manually if critical |
| UNSUPPORTED | No evidence found | Investigate; may need fixing |
| CONTRADICTED | Evidence contradicts unit | Must fix before publication |
| FABRICATED | Unit references nonexistent API/class | Must fix before publication |

### Step 4: Review defect origins

| Origin | Meaning | Remediation |
|--------|---------|-------------|
| KNOWLEDGE_GAP | Clone cache has it, knowledge doesn't | Re-run `/repo-scout` then `/knowledge-update` |
| GENERATION_FABRICATION | Content invented something | Fix via `/manual-edit` or `/heal-page` |
| EVALUATOR_MISS | Wrong content passed evaluators | File skill gap report for evaluator |
| SCOUT_MISS | Scout didn't extract from source | Re-run `/repo-scout` with enhanced extraction |
| ENRICHMENT_HALLUCINATION | Enriched claim contradicts source | Re-run `/knowledge-enrich` |

### Step 5: Act on findings

- **CONTRADICTED/FABRICATED findings**: Route to `/manual-edit` (S-73) or `/heal-page` (S-26)
- **UNSUPPORTED findings**: Investigate; route to `/manual-edit` if confirmed false
- **KNOWLEDGE_GAP / SCOUT_MISS origins**: Re-run knowledge pipeline first, then re-audit

> **Skill context close** — run after the last step:
> ```bash
> PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/commands/governance/skill_context.py end --skill S-85 --status completed
> ```

## Knowledge Files to Load

1. `knowledge/{family}/{platform}/merged/api_surface.json` — API surface (priority 2)
2. `knowledge/{family}/{platform}/merged/claims.json` — enriched claims (priority 4)
3. `knowledge/{family}/{platform}/merged/formats.json` — format support (priority 3)
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
- **Tier 2 (clone cache grep)**: Search clone cache for key identifiers from the unit; record file:line evidence
- **Tier 3 (LLM, optional)**: Semantic verification for units that remain UNVERIFIABLE after Tier 1+2 (not yet implemented; reserved for future)

## Output Format

### Gap Ledger JSON

See `reports/truth-audit/{family}-{platform}-{date}.json` for the full schema. Key sections:
- `summary`: verdict counts, verification rate, defect rate
- `files`: per-file verdict breakdown
- `units`: every decomposed unit with verdict, evidence chain, and defect origin
- `findings`: UNSUPPORTED/CONTRADICTED/FABRICATED units as actionable findings
- `defect_summary`: counts per defect origin code
- `delta`: fixed/new/regression/unchanged counts vs prior run

### Finding ID format

`F-{family}-{platform}-{type_code}-{sha8}` — compatible with S-43 gap-eval finding IDs.

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
| S-38 truth-audit | Member-level API | Fabricated methods/properties | Line-level decomposition, all 5 subdomains, clone cache evidence |
| S-43 gap-eval | Page-level publishability | Content gaps vs clone cache | Per-unit granularity, evidence chains, defect origin classification |
| S-32 content-audit | Paragraph-level knowledge | Claims contradicting claims.json | Clone cache as truth source, stable finding IDs |
| S-51 content-eval | Page + section quality | 16 evaluator dimensions | Truth verification (not quality rubric) |

## Re-run Policy

- Idempotent: same content + same knowledge SHA = same findings (except timestamps)
- Delta tracking: re-run after fixes shows prior findings as `fixed`, new findings as `new`
- Finding IDs are stable across reruns for the same content location

## Failure Modes

| Condition | Behavior |
|-----------|----------|
| Knowledge not found | Exit 1 with error |
| Knowledge stale | Exit 1 with error |
| Clone cache not found | Continue with Tier 1 only (Tier 2 disabled); warn |
| No content files for scope | Exit 1 with error |
| max-units reached | Stop processing; report partial results |

## Registry

**Skill code**: S-85
**Script**: `scripts/pipeline/commands/diagnostics/truth_audit_content.py`
**Test**: `scripts/pipeline/tests/test_truth_audit_content.py`

---

## LLM Metrics Obligation

If this skill invokes `llm.professionalize.com` directly or through `LLMRouter`,
the run carries a **metrics obligation** (METRICS-PLAN-001, `AGENTS.md §15`):

- All professionalize calls must use `ProfessionalizeClient`, `LLMRouter`, or a
  registered adapter entry in `metrics_callsite_registry.yaml`.
- Each run must capture per-call `MetricsEvent` records and aggregate them into a
  validated `MetricsRow` via `RunMetrics`.
- Default mode is **dry-run**. Live posting requires explicit owner approval and
  `AGENT_METRICS_ENDPOINT` / `AGENT_METRICS_TOKEN` set locally.
- Non-professionalize calls (Gemini, Ollama, M2M) are excluded from
  `token_usage` and `api_calls_count`.
- Metrics failures must not crash or block the parent pipeline job.
