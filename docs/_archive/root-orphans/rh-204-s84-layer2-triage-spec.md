# RH-204: S-84 Layer 2 Triage — Step 13a Specification

> Created: 2026-04-17
> Backlog item: RH-204 — S-84 chain integration (wire triage_confirm into refresh chain)
> Status: Pending operator application (agent-blocked by path_guard FORBIDDEN_PREFIXES: skills/)
> Code: `scripts/pipeline/lib/triage_confirm.py` + `scripts/pipeline/lib/reconcile_triage.py` (both complete)

## Operator Action Required

The `skills/refresh-product.md` and `.claude/commands/refresh-product.md` files must be
updated to include Step 13a. Agent writes to `skills/` and `.claude/` are blocked by
`path_guard.py` FORBIDDEN_PREFIXES. Apply this change manually or with
`SKIP_SKILL_CONTEXT_CHECK=1`.

## Step 13a to Insert

Insert the following block **between Step 13 and Step 14** in `skills/refresh-product.md`
and its mirror `.claude/commands/refresh-product.md`:

```markdown
13a. **Layer 2 body-prose triage** (reconcile_triage.py — RH-203/204):
     For each page updated or generated in Steps 4-7, run `reconcile_triage_page()` to
     detect body-prose staleness that Layer 1 (SHA heuristic) may have missed. Advisory
     only — does not block commit. Routes Layer 2-flagged pages to `/heal-page` or
     flags them for next cycle.
     ```python
     from reconcile_triage import reconcile_triage_page
     result = reconcile_triage_page(
         page_path=page,
         knowledge={"api_surface": api_surface, "claims": claims, "delta": delta},
         layer1_stale=sha_stale,
         family=family,
         platform=platform,
     )
     # result.final_verdict: 'needs_update' | 'current' | 'missing'
     # result.final_reasons: list of human-readable reason strings
     ```
     If `final_verdict == 'needs_update'` and page was not already updated in Step 4:
     - Log advisory: `Layer 2 triage: {page} needs update (confidence: {final_confidence:.2f})`
     - Add to `reports/refresh_state/{family}/{platform}/layer2_triage_advisory.json`
     - Do NOT re-run page-update automatically — this is advisory only
     Record progress: `post_refresh_verify.py {family} {platform} --step layer2_triage`
```

Also update the `CONTRACT` header comment to change `postcondition` from:
```
postcondition: content updated from knowledge delta; verification gate passed; changes committed
```
to:
```
postcondition: content updated from knowledge delta; Layer 2 body-prose advisory run; verification gate passed; changes committed
```

And update the `Skills invoked` line in Step 14 from:
```
Skills invoked: [refresh-product, S-12, S-14, S-82, S-20, S-83, S-62, S-48]
```
to:
```
Skills invoked: [refresh-product, S-12, S-14, S-82, S-20, S-83, S-62, S-48, triage_confirm, reconcile_triage]
```

## Why This Was Blocked

`path_guard.py` `FORBIDDEN_PREFIXES` includes `"skills/"` at line 88. The
`check_skill_context_hook.sh` PreToolUse hook invokes `path_guard.py` for all paths not
in its governed or ungoverned allowlists, and exits 2 (block) when `path_guard.py` returns
DENY.

This is intentional governance — skill specification files are operator-only documents.

## Evidence

- `triage_confirm.py` created: `scripts/pipeline/lib/triage_confirm.py` (RH-201, 2026-04-17)
- `reconcile_triage.py` created: `scripts/pipeline/lib/reconcile_triage.py` (RH-203, 2026-04-17)
- 108 tests passing (includes RH-201 and RH-203 test coverage)
- Operator must apply skill doc update; code integration is complete
