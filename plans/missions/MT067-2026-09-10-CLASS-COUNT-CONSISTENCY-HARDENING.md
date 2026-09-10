## Mission: MT067-2026-09-10-CLASS-COUNT-CONSISTENCY-HARDENING
> Investigation/plan file: `C:/Users/prora/.claude/plans/vast-questing-spindle.md`
> Backlog item: `G-23` (CLOSED, `backlog/BACKLOG.md` Recently Completed); `ST-193` (queued, follow-up, out of scope — `backlog/inbox.md`)
> Status: **CLOSED** (2026-09-10)
> Mission contract: not registered in `MISSION_AUTHORITY.yaml` — root slot was locked (`mission_locked: true`) by another active mission (`MT066-2026-09-09-PACKAGE-INSTALL-RECONCILIATION`, genuinely in-progress, not stale) for this mission's entire duration. Used the sanctioned lighter path instead — schema-5f taskcards + this mission file, same precedent as MT030.
> Durable taskcards: `reports/plan_state/MT067-2026-09-10-CLASS-COUNT-CONSISTENCY-HARDENING/taskcards.jsonl` (17 records: TC-01..TC-17, all terminal — CLOSED/FOCUSED_VERIFIED/INTEGRATION_VERIFIED)
> Evidence bundle: `reports/sprint/barcode-python-hardening/EVIDENCE_BUNDLE.md`

### Context

User flagged that barcode/python's "class count" read differently (26, 79, or 146)
depending which knowledge artifact was opened, and asked for a deep first-principles
production assessment: what's actually happening, whether it's a system gap, and a
durable, global fix — via Claude Code Plan Mode, then explicit approval to execute.

### What was found

Not a rerun-nondeterminism bug — a repo-wide structural one. Four independently
reimplemented, non-namespaced `class_count` formulas existed across
`extraction/outputs.py`, `commands/knowledge/scout.py`, `commands/knowledge/promote.py`,
`commands/knowledge/index.py`, and `commands/launch/site_planner.py`, with zero
cross-artifact reconciliation. A direct portfolio scan (not inference) found the same
mechanism live on 15 of 32 launched products, and the identical pattern had already
been caught once before, narrowly, on words/python (backlog `G-23`, filed 2026-07-23,
never generalized) and via a 2026-07-22 staleness fix (`index.py`'s HARDEN-A13) that
solved one problem while permanently creating a second, undocumented divergence.

### What was built

`scripts/pipeline/lib/class_stats.py::compute_class_stats()` — single source of truth,
three namespaced fields (`total_declared`, `public_documented`,
`raw_entries_including_non_class`) replacing the one overloaded `class_count` name.
Every writer switched to it; each artifact's pre-existing `class_count` field kept as a
backward-compatible deprecated alias, pinned to its own historical meaning (never
silently redefined). New `check_knowledge_stats_consistency.py` (cross-artifact
reconciliation, now a hard gate) and `check_no_inline_class_count.py` (preventive lint
against a 5th inline formula reappearing), both wired into pre-commit and CI. A
Tier-B fix (`site_planner.py`'s reference-doc page-count sizing) investigated before
applying, confirmed to change no real generation behavior, then applied.

### Rollout

Pilot-verified end to end on barcode/python (idempotency proven by two consecutive
`promote`+`index` reruns producing byte-identical stats, not just asserted). Fleet
backfill in 3 batches: 17 currently-agreeing products (safety proof), 9 of 15
diverging products, then a final 5 (`cells/net`, `pdf/python`, `pdf/typescript`,
`slides/cpp`, `slides/python`) initially deferred because each carried pre-existing
uncommitted `merged/` state from a now-inactive session — verified safe before
regenerating (the dirty claim counts matched `scout_claims + scout/enriched_claims.json`
closely, confirming a completed-but-uncommitted enrichment pass, not live editing;
`total_claims` came back byte-identical after regenerating, zero data loss). All 32
launched products now agree; the reconciliation gate promoted from WARN to a hard FAIL
once confirmed clean portfolio-wide.

Two real, unrelated bugs found and fixed along the way, each independently verified
before fixing (not assumed): `pre-commit-audit.sh` Step 38 was scanning every staged
`.py`/`.sh` file repo-wide instead of scoping to `scripts/`, wrongly flagging a
verbatim third-party FOSS example snippet; `promote.py`'s `api_surface.md` console
print label had the same "146 vs 79" mislabeling as the artifact bug itself.

### Deliberately out of scope, filed not fixed

- `ST-193` — pre-existing 3d/typescript scout/merged extraction drift (2 test
  failures), surfaced but not caused by the fleet backfill; root-caused to predate
  this mission.
- `index.json`'s `provenance` field found to be a hardcoded literal `"scout_only"`
  across all 32/32 products, never reflecting real `enrichment_status`. Flagged, not
  investigated to root cause.
- `scripts/maintenance/rebuild_snippet_index.py` duplicates the public-API filter
  *criteria* for an unrelated snippet-cross-referencing purpose — noted, untouched
  (outside declared skill-context scope).

### Commits (all pushed to `origin/main`)

`5edbe2bb7e` (core fix + barcode/python pilot), `f8ffc953bd` (fleet Batch 1, 17
products), `c21c89e5ea` (fleet Batch 2, 9 products), `3ae2878b7a` (Tier-B
site_planner.py fix), `b4137bd5c6` (backlog G-23 closure), `a7c95d1a9d` (backlog
ST-193 filing), `5abfee1fcb` (docs), `485eb23b87` (Step 38 scoping fix), `e604fb6d0d`
(fleet Batch 3, final 5 products), `94744a15c2` (WARN→FAIL gate promotion).
