## Mission: MT060-2026-09-01-MISSION-ID-LEDGER
> Investigation/plan file: `C:/Users/prora/.claude/plans/inherited-baking-goose.md`
> Backlog item: `ST-157` (`backlog/inbox.md:94`, resolved via commit `0139189e42`)
> Status: **CLOSED** (2026-09-01)
> Mission contract: not root-bound — hand-authored archive record, root
> `MISSION_AUTHORITY.yaml` held by `MT058-2026-08-31-STALE-GUARD-WINDOW-IDENTITY-ENCODING`
> (open) for this mission's entire duration.
> Durable taskcards: `reports/plan_state/MT060-2026-09-01-MISSION-ID-LEDGER/taskcards.jsonl`
> (15 records, TC-00..TC-14, all terminal — CLOSED/IMPLEMENTED/INDEPENDENTLY_REVIEWED)
>
> Note: this mission id is unrelated to the differently-named
> "MT060-2026-08-31-REFRESH-PROSE-CAPABILITY" that several other artifacts (including
> `backlog/BACKLOG.md`, before this reconciliation) referred to — that mission was
> later renumbered to `MT063-2026-09-04-REFRESH-PROSE-CAPABILITY` after colliding
> with this real, already-closed mission's number. See
> `plans/missions/MT059-2026-08-31-PDF-GO-S84-FANOUT.md` for the collision history.

### Context

Fixed ST-157: mission-ID allocation had no protection mechanism at all — every
`MT0NN` id was chosen by an agent grepping several directories and picking
"highest + 1" by eye, which had already produced a confirmed on-disk duplicate
(`MT018` issued to two unrelated missions, `plans/master-plan.md`) and a second,
entirely separate `MT0NN`-shaped numbering track run by `/readme-refresh`
(independently reaching MT056) with zero visibility into the main track.

### What was built

- `scripts/pipeline/lib/mission_id_ledger.py` — FileLock-protected, append-only
  ledger at `scripts/pipeline/config/mission-ids.jsonl`, modeled on
  `baseline_ledger.py`. Concurrency proven via an N-concurrent-`allocate()`
  regression test that fails against the unlocked path (a negative control
  reproduced 4/6 number collisions per run, 20 across 5 runs) and passes fixed.
- `mission_authority.py allocate --track --slug [--date]` verb; `archive_mission()`
  collision guard (`MissionIdCollisionError`) with a regression test; `list` extended
  with a ledger-coverage cross-check scoped to `MT0NN`-shaped ids only.
- Backfill of `mission-ids.jsonl` from git history + a local `reports/plan_state/`
  scan + `plans/missions/*.md` + the readme-refresh Track B table — 46 entries,
  `highest_number()=60` at the time. Self-caught and fixed 3 real backfill bugs along
  the way (directory-name vs. file-content scanning dropping MT018/038/039;
  `plans/missions/*.md` missing entirely as a source; Track B's bare-number rows
  silently rejected by the ID regex). Recovered 3 further previously-undocumented
  historical collisions (MT014, MT023, MT034 each also issued twice).
- `scripts/ci/checks/check_mission_id_ledger_coverage.py`, wired as an advisory,
  `continue-on-error` step in `content-governance-checks.yml` and
  `simulate_pr_checks.sh`, mirroring `check_pipeline_registration.py`'s landing
  pattern; proven to actually execute (not just present on disk).
- `docs/readme-refresh/plan-system-forensic-reconciliation.md`'s D-15 row updated
  directly with the Track B numbering convention (confirmed not under
  `path_guard.py`'s `FORBIDDEN_PREFIXES`, unlike `docs/governance/`).

### Deliberately out of scope

- Editing `docs/governance/planning-methodology.md` directly, or the `/readme-refresh`
  skill's own mission-start instructions — both `path_guard.py`-forbidden for direct
  agent edit; a diff was drafted in the evidence bundle for human application instead.
- Collision protection for non-numeric, free-text mission ids.
- Retroactively un-colliding the historical MT018 duplicate — left as a documented
  incident.
- ST-056/ST-057 (identical root cause on the backlog's own ST-xxx id sequence) —
  flagged as a fast-follow, not fixed here.

### Independent verification

A fresh agent (did not implement) verified the fix holds up with no contradictions,
vacuous tests, or scope creep. One material gap was found and repaired same-cycle:
the concurrency test was thread-only, not process-only — a real 4-process
multiprocessing test was added (112 tests total).

### Commits

`d039330649` (core fix, pushed to `origin/main`), `3c088acc4d` (independent-review
follow-up: process-level concurrency test). Evidence bundle:
`reports/evidence/ST-157-mission-id-ledger/`.
