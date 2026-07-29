---
name: body-refresh
id: S-105
description: >
  Execute body prose updates for docs/KB/blog pages based on semantic changes.
args: "{family} {platform} [--dry-run|--execute] [--page path]"
---

# S-105: Body Refresh

Executes body prose updates for docs/KB/blog/products pages. Reads `body_impact.json`
and `semantic_changes.json`, applies one of five deterministic strategies (or a grounded
LLM `PARAGRAPH_REWRITE`), and writes content via `safe_content_write()` under an S-73
context. Every write passes through three generation-time gates before it lands.

**CLI:**
```bash
PYTHONPATH=scripts/pipeline .venv/Scripts/python -m commands.content.body_refresh {family} {platform} --dry-run
PYTHONPATH=scripts/pipeline .venv/Scripts/python -m commands.content.body_refresh \
  {family} {platform} --execute --run-id ID --run-root reports/refresh_runs/{family}/{platform}/ID
```

Mutating execution without `--run-id` fails. Production inputs, receipts, and
`page_decisions.jsonl` are bound to `--run-root`; use S-84 `refresh_run.py` rather
than invoking this command directly. Diagnostic dry runs remain compatible.

## Update strategies

| Strategy | Kind | When |
|---|---|---|
| `SURGICAL_CLAIM_REPLACEMENT` | deterministic | API renamed in prose |
| `TABLE_ROW_RECONCILIATION` | deterministic | API removed/renamed in a markdown table |
| `EXAMPLE_REGENERATION` | deterministic | removed API in a code block |
| `SECTION_REMOVAL` | deterministic | a section only references a removed feature |
| `PARAGRAPH_REWRITE` | LLM (grounded) | FEATURE_ADDED / BEHAVIOR_CHANGED / API_* prose |

`PARAGRAPH_REWRITE` reaches the real LLM callsite (RPR-E-01 fixed a dead-code short-circuit
that had made it unreachable); it falls back to a deterministic template only on an actual
LLM failure, and the receipt records which path ran.

## Surface-differentiated policy (RPR-E-04)

Strategy selection is surface-aware. Each surface has an **explicit** policy — nothing falls
through to a silent default. A strategy disallowed for a page's surface is deferred to its
handoff target (recorded in the receipt's `surface_deferrals`), never silently applied.

| Surface | Allowed strategies | Disallowed strategy handoff |
|---|---|---|
| reference | citation-backed deterministic only (no `PARAGRAPH_REWRITE`) | `batch-reference` (S-62) — reference pages are regenerated from `api_surface.json`, never LLM-rewritten in place |
| products / docs / kb / blog | full set (5 deterministic + `PARAGRAPH_REWRITE`) | — |
| unknown (unclassifiable path) | citation-backed deterministic only | `page-update` (S-20) — the manual/agent path handles the residual |

## Generation-time gates (a write is blocked if any fires)

1. **Forbidden claims (RPR-E-02)** — a candidate that newly introduces an affirmative claim
   about a forbidden API (methods throw `NotImplementedException`) is refused; the original
   content is preserved. Verdict `BLOCKED_FORBIDDEN_CLAIM`. See `lib/forbidden_claims_check.py`.
2. **Template propagation (RPR-E-03)** — a distinctive code/claim span reused verbatim from an
   earlier page in the same run, without the reusing page sharing the originating page's
   grounding, is refused. Verdict `BLOCKED_TEMPLATE_PROPAGATION`. See `lib/regrounding_check.py`.
3. **Surface policy (RPR-E-04)** — a strategy disallowed for the page's surface is deferred (above).

## Related skills

- **S-20 (`page-update`)** — the fallback/handoff path for docs/kb/blog prose that S-105 cannot
  resolve deterministically, and for the `unknown`-surface residual. S-105 is the primary,
  deterministic-first path; S-20 handles what genuinely needs an agent/manual judgment.
- **S-62 (`batch-reference`)** — the regeneration path for reference pages; S-105 never edits
  reference pages in place, it defers them here.
- **S-106 (`refresh-oracle`)** — validates S-105's output against source truth.
