# S-117: Mechanism Sweep — Cross-Product Pipeline-Improvement Propagation

<!-- CONTRACT: agent-executed workflow (no single script runs the full skill; orchestrates
     existing S-12/S-14/S-84 primitives and promote.py's own delta-generation logic)
     purpose: detect which already-launched products are stale because OUR OWN pipeline
       code (extraction/enrichment/snippet/format detection) improved, independent of any
       upstream FOSS repo change
     preconditions:
       - the triggering fix has already landed (its own tests pass) in
         scripts/pipeline/extraction/, an enrichment/scout step, snippet extraction, or
         format detection
       - data/products.json / reports/phase_state.json list the already-launched products
         to consider
     postcondition: reports/mechanism_sweep/{mechanism-id}-{date}.md written, listing every
       candidate product's disposition; a precisely-scoped backlog row filed/updated per
       affected product
     idempotent: yes for the sweep itself (diff-only, no promotion) — re-running with the
       same mechanism-id and commit produces the same classification; promoting a product's
       corrected knowledge (step 5) is a one-time action per product per mechanism
     verified: '2026-07-29'
-->

**Arguments**: $ARGUMENTS
Expected format:
```
--since-commit <sha> --language <lang> [--exclude <family/platform>[,<family/platform>...]]
```

| Parameter | Required | Values |
|-----------|----------|--------|
| `--since-commit` | Yes | The commit SHA that landed the pipeline improvement (extraction/enrichment/snippet/format fix). |
| `--language` | Yes | The language or mechanism the fix applies to (e.g. `go`, `rust`, `cpp`), used to enumerate candidate products. |
| `--exclude` | No | Comma-separated `family/platform` pairs to skip — normally the product already being worked on when the fix landed, since it's handled by the triggering mission, not this sweep. |

## Purpose

`change-sweep` (S-94) answers "did the *upstream FOSS repo* change for any launched
product?" This skill answers the complementary question: **"did *our own* extraction,
enrichment, snippet, or format-detection code just get smarter, in a way that would change
what re-running it produces for other already-launched products sharing that language or
mechanism — even though nothing upstream changed at all?"**

This situation has recurred at least three times without a formal sweep: a Go interface/
embedding extraction fix left pdf/go's published content stale relative to its own,
already-re-scouted knowledge model (`PDFGO-STALE-001`); an LLM-credential fix improved
cells/rust's enrichment retroactively (`RUST-ENRICH-001`); a directory-name-matching fix
elsewhere corrected cells/cpp's snippet extraction retroactively (`PDFCPP-SNIPPET-PREMISE-001`).
Each time, discovery was incidental — someone noticed while working on something unrelated.
This skill makes that discovery deterministic and repeatable.

## When to use

Invoke immediately after landing any fix under `scripts/pipeline/extraction/`, an
enrichment/scout step, snippet extraction, or format detection that changes what gets
captured for a shared language or mechanism — before considering that fix "done." Treat it
as a standard follow-up step of the mission that lands such a fix, the same way S-95
(discovery-triage) is the standard follow-up of S-94.

## Steps

> **Skill context gate** — run before step 1:
> ```bash
> PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/commands/governance/skill_context.py begin --skill S-117 --scope "reports/mechanism_sweep/*"
> ```

1. **Enumerate candidates**: read `data/products.json` and `reports/phase_state.json` for
   every already-launched product whose `language` (or platform) matches `--language`,
   excluding any product listed in `--exclude`.

2. **Diff-only re-run per candidate**: for each candidate, re-run *only* the fixed
   extraction/enrichment/snippet/format step against the product's **current, already-
   cloned** source in `runs/.clone_cache/` — do not pull upstream (that is `change-sweep`'s
   axis, not this skill's). Produce a hypothetical diff using the same delta shape
   `promote.py` already generates (`knowledge_delta.json` — `modified_apis` / `new_apis`
   keys) rather than inventing a new diff format. Do not promote or mutate the live
   knowledge model in this step.

3. **Classify each candidate**:
   - `NONE` — no difference; re-running the fixed step produces byte-identical output.
   - `METADATA_ONLY` — stats change (e.g. `snippet_count`, coverage percentages) but no
     currently-published page claim is wrong or incomplete. Matches the
     `PDFCPP-SNIPPET-PREMISE-001` pattern.
   - `CONTENT_AFFECTING` — a currently-published page's claims are now wrong or incomplete
     under the corrected extraction (e.g. an interface documented as `methods: []` that the
     fix now shows has real methods). Matches the pdf/go 42-class pattern.

4. **Separate the two drift axes explicitly.** If the same diff-only pass also surfaces
   upstream additions unrelated to the fix itself (new upstream classes/functions that would
   exist regardless of this mechanism change), do **not** fold them into this skill's
   `modified_apis`-style classification. File them as a separate `change-sweep`/backlog
   finding instead. This is the exact conflation `PDFGO-STALE-001` had to untangle by hand
   (`modified_apis` vs `new_apis`) — this skill produces the separation natively.

5. **Promote and file, per candidate**:
   - `NONE`: no action. Record the clean negative result in the sweep report — a confirmed
     absence of drift is evidence too, not silently discardable.
   - `METADATA_ONLY`: promote the corrected knowledge (S-14/`promote.py`) only. File a
     low-priority backlog row noting the metadata correction; no content regeneration needed.
   - `CONTENT_AFFECTING`: promote the corrected knowledge (S-14/`promote.py`). File a
     precisely-scoped backlog row naming the exact affected classes/pages (mirroring
     `PDFGO-STALE-001`'s style). **Recommend** — do not auto-invoke — a
     `/refresh-product {family} {platform} --mode remediation|combined` cycle to close it.

6. **Write the sweep report** to `reports/mechanism_sweep/{mechanism-id}-{date}.md`, where
   `{mechanism-id}` is a short slug for `--language` + the fix (e.g.
   `go-interface-embedding`). List every candidate product and its disposition
   (`NONE`/`METADATA_ONLY`/`CONTENT_AFFECTING`), the backlog row it produced (if any), and
   any separated upstream-drift findings routed elsewhere per step 4.

> **Skill context close** — run after the last step:
> ```bash
> PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/commands/governance/skill_context.py end --skill S-117 --status completed
> ```

## Output

```
# Mechanism Sweep: {mechanism-id} ({date})
Trigger: {--since-commit} — {language}
Candidates checked: N (excluding {--exclude})

## CONTENT_AFFECTING
- {family}/{platform} — {M} classes affected — filed {BACKLOG-ID}

## METADATA_ONLY
- {family}/{platform} — {stat} corrected — filed {BACKLOG-ID}

## NONE
- {family}/{platform} — confirmed no drift

## Separated upstream-drift findings (routed to change-sweep/backlog, not this sweep)
- {family}/{platform} — {N} new upstream classes unrelated to this mechanism
```

## Post-conditions

- One sweep report exists under `reports/mechanism_sweep/` naming every candidate product's
  disposition, including clean `NONE` results.
- Every `METADATA_ONLY`/`CONTENT_AFFECTING` candidate has a backlog row citing the report.
- No candidate's live knowledge model or content was regenerated by this skill directly —
  it recommends `/refresh-product`; it does not invoke it.

## Notes

- This is the deliberate sibling of `change-sweep` (S-94): change-sweep watches the
  *upstream FOSS repo* axis; mechanism-sweep watches the *our own pipeline code* axis. They
  answer different questions and should not be merged.
- v1 is agent-executed by design, reusing `promote.py`'s existing diff generation rather than
  a new backing script. If this pattern recurs enough to justify dedicated automation, a
  `scripts/pipeline/commands/diagnostics/mechanism_sweep.py` script (matching
  `change-sweep`'s `repo_patrol.py sweep` shape) is the natural hardening step.
- Does not invoke `/refresh-product` (S-84) itself — matches `change-sweep`'s own convention
  of separating detection from remediation.
- A product's exclusion via `--exclude` does not mean it is unaffected — it means this sweep
  assumes the triggering mission already handles it directly (verify this assumption before
  relying on it for products excluded for other reasons).

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

