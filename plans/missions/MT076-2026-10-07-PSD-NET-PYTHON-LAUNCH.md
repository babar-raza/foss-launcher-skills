## Mission: MT076-2026-10-07-PSD-NET-PYTHON-LAUNCH
> Plan file: `~/.claude/plans/present-a-proper-plan-precious-hummingbird.md` (the single authoritative plan; **not copied into the repo**, a copy would be a competing plan)
> Backlog items: `INV-014` (psd/python), `INV-015` (psd/net) in backlog/inbox.md
> Status: **BLOCKED_AT_G0** (2026-10-07): hardening, probes and drafts done; registry/knowledge/launch gated by the missing upstream LICENSE (DEC-01) and, for psd/python, by the missing packaging manifest (F-PSD-07). Hardening fixes are drafted and validated outside the repo but unapplied because another live session held the `scripts/pipeline/**` skill context for more than 58 minutes.
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

- [x] GOV-01 governance bind, baseline, seeding (286 cards; independent review passed with findings fixed)
- [x] PRB-01 upstream probe (net builds, 77/77 tests; python imports, 75 tests), UPS-01 five issue drafts (NOT posted, SC-01)
- [x] DEC-02/03/04/06 resolved; DEC-01 LICENSE gate `BLOCKED_EXTERNAL` (both repos: license API null)
- [x] HRD investigations: HRD-01/04/05 defects reproduced; HRD-03/06 premises not reproduced (no defect); HRD-9N-1/-2 intake cards
- [ ] HRD fix cards (-02..-05): `BLOCKED_EXTERNAL` on the skill-context holder; drafts + validation in evidence `generated-artifacts/hardening-drafts/`
- [ ] REG/KNW/LNC/LPY/XPR/REV/CLS -- gated by G0
- Incident F-PSD-12: this mission's first commit (6ac7cef1a5) was published to origin/main by another session's plumb push; further commits go to branch `mt076-psd-launch`.
- Backlog: INV-014/015 updated; ST-242..ST-251 filed (generic defects and follow-ups).
