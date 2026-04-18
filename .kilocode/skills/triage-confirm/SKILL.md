<!-- CONTRACT: agent-executed
     purpose: detect whether a content page's body prose has become stale relative to the
              current knowledge model by scanning for references to changed or removed API
              classes and claims (Layer 2 staleness detection)
     preconditions: page file exists under content/; knowledge/{family}/{platform}/merged/ current
     postcondition: stale/current verdict written with per-finding reasons; no content modified
     idempotent: yes — read-only scan; safe to re-run
     depends_on: [S-54, S-84]
     verified: 2026-04-18
-->
# S-92: Triage Confirm — Layer 2 Body-Prose Staleness Scanner

**Arguments**: $ARGUMENTS
Expected format: `{family} {platform} [--files {glob}] [--output {path}]`

## Purpose

Scan content page body prose for references to API classes or knowledge claims that have
changed or been removed since the last knowledge update. Provides Layer 2 staleness detection
to complement the Layer 1 SHA-based check in `refresh_knowledge.py` / `knowledge_delta.json`.

Use S-92 when:
- Layer 1 reports SHA unchanged but you suspect content drift
- A knowledge update changed API signatures without changing the repo SHA
- Running S-84 (refresh-product) Step 9.5 — the deep-triage pass

Do **not** use S-92 to modify content — it is read-only. Route stale pages to S-20, S-26,
or S-21 based on severity.

## Steps

> **Skill context gate** — run before step 1:
> ```bash
> PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/skill_context.py begin --skill S-92 --scope "*"
> ```

### 1. Knowledge bootstrap check

```bash
PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/refresh_knowledge.py {family} {platform} --check-only
```

If stale_since is set and clone cache is missing → halt: "Knowledge is stale. Run /knowledge-update first."

### 2. Load knowledge model

The scanner uses `knowledge/{family}/{platform}/merged/` artifacts:
- `api_surface.json` — current API class/method/property names
- `claims.json` — current claim IDs and statements
- `knowledge_delta.json` — changed/removed APIs and claims since last update

### 3. Run Layer 2 scan

```bash
PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/triage_confirm.py \
  --family {family} --platform {platform} [--files {glob}]
```

For each page, `triage_confirm()` checks:
- Whether prose references any API class in `knowledge_delta.json` `modified_apis`
- Whether prose references any claim in `knowledge_delta.json` removed/modified claims
- Returns `{'stale': bool, 'reasons': list[str]}`

### 4. Run 3-source reconciliation (optional, full triage)

To combine Layer 1 + Layer 2 + page-spec signals:

```bash
PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/reconcile_triage.py \
  --family {family} --platform {platform} [--output reports/triage/]
```

Output: per-page `final_verdict` (`needs_update` / `missing` / `current`) with source breakdown.

### 5. Route stale pages

| Finding | Route |
|---------|-------|
| `final_verdict: needs_update` | `/page-update` (S-20) for prose drift; `/heal-page` (S-26) for grade D/F |
| `final_verdict: missing` | `/batch-reference` (S-62) or `/page-draft` (S-19) |
| `final_verdict: current` | No action |

### 6. Report

Print summary:
```
=== triage-confirm summary ===
Family:   {family}
Platform: {platform}
Pages scanned: {N}
Stale (Layer 2): {stale_count}
Current:         {current_count}
```

> **Skill context close** — run after the last step:
> ```bash
> PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/skill_context.py end --skill S-92 --status completed
> ```

## Backing Scripts

- `scripts/pipeline/triage_confirm.py` — Layer 2 body-prose scanner
- `scripts/pipeline/reconcile_triage.py` — 3-source reconciliation (Layer 1 + Layer 2 + page-spec)
