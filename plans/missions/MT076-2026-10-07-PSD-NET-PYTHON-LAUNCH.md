## Mission: MT076-2026-10-07-PSD-NET-PYTHON-LAUNCH
> Plan file: `~/.claude/plans/present-a-proper-plan-precious-hummingbird.md` (the single authoritative plan; **not copied into the repo**, a copy would be a competing plan)
> Backlog items: `INV-014` (psd/python), `INV-015` (psd/net) in backlog/inbox.md
> Status: **OPEN** (executing; see Progress)
> Taskcards: `reports/plan_state/MT076-2026-10-07-PSD-NET-PYTHON-LAUNCH/taskcards.jsonl` (51 parents, 235 children)
> Mission contract: archived at `reports/plan_state/MT076-2026-10-07-PSD-NET-PYTHON-LAUNCH/mission_authority.yaml`; this mission does **not** hold the root `MISSION_AUTHORITY.yaml` slot (held by MT071, `mission_locked: true`; no takeover performed)
> Evidence bundle: `reports/plan_state/MT076-2026-10-07-PSD-NET-PYTHON-LAUNCH/evidence/`

### Context

Launch `psd/net` (Aspose.PSD-FOSS-for-.NET) and `psd/python` (Aspose.PSD-FOSS-for-Python) on the five aspose.org
sites through the registered skill chain, and use the two launches to harden the generic launch system.

Sprint constraint SC-01 (user, 2026-10-07): **no upstream repository may be updated in any case.** Both upstream
repos have no LICENSE on `main` (issues #5 / #4 open), and INV-014/INV-015 forbid registry, knowledge and launch work
until one exists, so the expected end state is `BLOCKED_AT_G0` after hardening, probes and drafts.

### Progress

- [x] GOV-01 governance bind, baseline, seeding (see store)
- [ ] PRB-01 upstream probe, UPS-01 drafts
- [ ] HRD-01..08 hardening (blocked while another session holds a skill context on `scripts/pipeline/**`)
- [ ] G0 LICENSE gate (DEC-01) -- `BLOCKED_EXTERNAL`
- [ ] REG/KNW/LNC/LPY/XPR/REV/CLS -- gated by G0
