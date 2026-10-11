# TC-MT070-03: IMAGING-NET-BATCHREF-HARNESS-001 fix direction (a) — BLOCKED, human action required

**Status: `BLOCKED_LOCAL`**, matching the exact same class of blocker MT068's own H5
finding hit for a skill-doc edit
(`reports/skill-gaps/2026-09-11-imaging-net-pipeline-hardening-prerequisites.md`, "H5
verification" section, "Attempted direct fix, blocked"). `.agents/skills/` (the
canonical skill-doc source, synced to `.claude/commands/`/`.kilocode/skills/` mirrors
via `scripts/pipeline/commands/ops/sync_providers.py`) is not in `path_guard.py`'s
allowed-path list for agent writes — confirmed live: `check_skill_context_hook.sh`
refuses the edit with `FORBIDDEN_PATH` even under a correctly-opened S-62 skill
context. `SKIP_SKILL_CONTEXT_CHECK=1` is explicitly documented as operator-only; not
used here per the same restraint MT068's H5 exercised.

**Root cause (already fully diagnosed by MT068's "Fourth addendum", not re-derived
here)**: `.agents/skills/batch-reference/SKILL.md`'s own "Generate pages" section
(lines 141-144) documents:
```bash
.venv/Scripts/python scripts/pipeline/commands/content/batch_reference.py {family} {platform} \
  --run-id ID --run-root reports/refresh_runs/{family}/{platform}/ID
```
Passing `--run-root` sets `explicit_run_root=True`, routing generation through
`body_refresh.py`'s strict `_validated_run_scope()` gate, which requires a manifest +
pinned `scope.json` that only `refresh_run.py` (S-84) produces — and S-84's own
`start --mode combined`/`upstream` path hard-requires `knowledge_delta.json`, which
cannot exist for a product generating its reference batch for the first time. The
actual working invocation for a first launch (confirmed against imaging/net's own
successful batch and MT040's pdf/typescript launch commits `f93411ed59`/`4ee59ff425`)
is `--run-id` alone, omitting `--run-root` entirely — `resolved_run_root` auto-derives
and the strict gate is skipped. The doc was never updated to say so, and its own
literal example is broken for the exact case (first launch) most likely to be
followed literally.

**Ready-to-apply diff** (for a human operator or a session with explicit prior
authorization to write under `.agents/skills/`, matching the precedent MT068's H5
proposed diff set for `.claude/commands/publish-readiness-review.md`):

```diff
--- a/.agents/skills/batch-reference/SKILL.md
+++ b/.agents/skills/batch-reference/SKILL.md
@@ -140,6 +140,23 @@
 ```bash
 .venv/Scripts/python scripts/pipeline/commands/content/batch_reference.py {family} {platform} \
   --run-id ID --run-root reports/refresh_runs/{family}/{platform}/ID
 ```
 
+> **First-launch note (2026-09-16, found live during MT068's imaging/net launch, see
+> `reports/skill-gaps/2026-09-11-imaging-net-pipeline-hardening-prerequisites.md`'s
+> "Fourth addendum" for the full trace)**: passing `--run-root` sets
+> `explicit_run_root=True` and routes generation through `body_refresh.py`'s strict
+> `_validated_run_scope()` gate, which requires a real manifest + pinned `scope.json`
+> that only `refresh_run.py` (S-84) produces — and S-84's own `start --mode
+> combined`/`upstream` path then hard-requires `knowledge_delta.json`, a diff artifact
+> that cannot exist for a product generating its reference batch for the first time
+> (no prior knowledge snapshot to diff against). **For a brand-new product's first
+> reference batch (its target platform has zero existing pages under
+> `content/reference.aspose.org/en/{family}/{platform}/`), omit `--run-root` and pass
+> `--run-id` alone**: `resolved_run_root` auto-derives to
+> `reports/refresh_runs/{family}/{platform}/{run_id}`, `explicit_run_root` stays
+> `False`, and the strict scope-pin gate is correctly skipped. This is the invocation
+> every first launch has actually used successfully (e.g. MT040's pdf/typescript
+> reference batch, commits `f93411ed59`/`4ee59ff425`), even though the code block
+> above — written for the refresh case — was never updated to say so. Use the
+> `--run-root` form above only for a genuine refresh of an already-launched product's
+> existing reference pages.
+
 The script generates all class pages using templates from `api_surface.json`. For each page it:
```

After applying, run `sync_providers.py` (the sanctioned one-directional canonical→mirror
sync — `.claude/commands/batch-reference.md` and
`.kilocode/skills/batch-reference/SKILL.md` are downstream mirrors, never hand-edited
directly) to propagate to the two mirrors.

**Fix direction (b)** (a genuine first-launch mode in `refresh_run.py` that restores
S-84's full validation coverage, including automatic Check-8 wiring, for first
launches) remains out of scope for this mission, as already decided in the governing
plan — this is a larger harness change, not a doc correction.

**Not fixed by this mission; escalated for human/operator action.** Taskcard left at
`BLOCKED_LOCAL` with this evidence rather than closed, per
`docs/workflows/gap-escalation.md`'s "await human decision" requirement — the
diagnosis and fix are both complete, only the write permission is missing.
