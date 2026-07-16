<!-- CONTRACT: scripts/pipeline/lib/triage_confirm.py (main entrypoint), scripts/pipeline/lib/reconcile_triage.py (3-source reconciliation)
     purpose: detect whether a content page's body prose has become stale relative to the
              current knowledge model by scanning for references to changed or removed API
              classes and claims (Layer 2 staleness detection)
     preconditions: page file exists under content/; knowledge/{family}/{platform}/merged/ current
     postcondition: stale/current verdict written with per-finding reasons; no content modified
     idempotent: yes — read-only scan; safe to re-run
     depends_on: [S-54, S-84]
     verified: 2026-07-16 (RPR-F-03) — real CLI added; prior "agent-executed" contract was
       inaccurate: the backing files had no argparse/__main__, so the CLI invocation this
       document previously specified silently no-op'd (defined functions, touched nothing,
       exited 0) if run literally as written. Wired into post_refresh_verify.py --verify
       Check 9 as a real blocking gate (exit 1 = stale pages found, blocks commit).
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
> PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/commands/governance/skill_context.py begin --skill S-92 --scope "*"
> ```

### 1. Knowledge bootstrap check

```bash
PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/commands/knowledge/refresh_knowledge.py {family} {platform} --check-only
```

If stale_since is set and clone cache is missing → halt: "Knowledge is stale. Run /knowledge-update first."

### 2. Load knowledge model

The scanner uses `knowledge/{family}/{platform}/merged/` artifacts:
- `api_surface.json` — current API class/method/property names
- `claims.json` — current claim IDs and statements
- `knowledge_delta.json` — changed/removed APIs and claims since last update

### 3. Run Layer 2 scan

```bash
PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/lib/triage_confirm.py {family} {platform} [--files path1 path2 ...] [--json]
```

Positional `{family} {platform}` args, matching this repo's other refresh-pipeline CLIs
(`body_impact.py`, `body_refresh.py`, `page_impact_assess.py`) — not `--family`/`--platform`
flags. Writes `reports/refresh_review/{family}/{platform}/triage_verdict.yaml`.

For each page, `triage_confirm()` checks:
- Whether prose references any API class in `knowledge_delta.json` `modified_apis`
- Whether prose references any claim in `knowledge_delta.json` removed/modified claims
- Returns `{'stale': bool, 'reasons': list[str]}`

Exit codes: `0` = confirmed (no page stale), `1` = unresolved (≥1 page stale — blocks
`post_refresh_verify.py --verify` Check 9), `2` = error (knowledge artifacts absent).

### 4. Run 3-source reconciliation (optional, full triage)

To combine Layer 1 + Layer 2 signals (page-spec source not wired into the CLI path — see
`reconcile_triage.py`'s module docstring for the documented simplification):

```bash
PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/lib/reconcile_triage.py {family} {platform} [--files path1 path2 ...] [--json]
```

Writes `reports/refresh_review/{family}/{platform}/reconcile_triage.json`. Output: per-page
`final_verdict` (`needs_update` / `missing` / `current`) with source breakdown. Exit codes
mirror step 3 above.

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
> PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/commands/governance/skill_context.py end --skill S-92 --status completed
> ```

## Backing Scripts

- `scripts/pipeline/lib/triage_confirm.py` — Layer 2 body-prose scanner
- `scripts/pipeline/lib/reconcile_triage.py` — 3-source reconciliation (Layer 1 + Layer 2 + page-spec)
