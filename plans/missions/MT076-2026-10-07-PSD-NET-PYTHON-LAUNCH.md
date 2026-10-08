## Mission: MT076-2026-10-07-PSD-NET-PYTHON-LAUNCH
> Plan file: `~/.claude/plans/present-a-proper-plan-precious-hummingbird.md` (the single authoritative plan; **not copied into the repo**, a copy would be a competing plan)
> Backlog items: `INV-014` (psd/python), `INV-015` (psd/net) in backlog/inbox.md
> Status: **IN_PROGRESS — psd/net pilot-qualified** (2026-10-08): the original `BLOCKED_AT_G0`
> LICENSE gate was resolved via owner attestation (license wording "MIT licensed" as
> grounded text-only, no link — `evidence/decisions/license-attestation.md`; see
> `ST-251`/`ST-252` for the deferred real-LICENSE-link follow-up). psd/net's content pipeline
> (products page, family sync, 24 reference pages) is generated, independently reviewed
> (PASS), and pilot-qualified (`TC-PSD-LNC-NET-10` CLOSED, `evidence/decisions/pilot-qualified.md`).
> Blog/Docs/KB stages (`LNC-NET-02/03/04`) now unlocked and in progress. psd/python
> (`LPY-*`) remains gated on `TC-PSD-REG-02`/`KNW-PY-01` closing first.
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
- [x] DEC-02/03/04/06 resolved; DEC-01 LICENSE gate resolved via owner attestation (text-only "MIT licensed", no link)
- [x] HRD investigations: HRD-01/02/04/05/07/10 all CLOSED with real portfolio-scale defects found+fixed; HRD-03/06 premises not reproduced (no defect); HRD-9N-4/-6/-7 intake cards (disclosed, not fixed mid-launch — Read/Write mislabeling, destructive cross-product `index.py` side effect, enum-doc-coverage gap respectively)
- [x] `TC-PSD-LNC-NET-01` (Products page + family sync) CLOSED + independently reviewed, PASS
- [x] `TC-PSD-LNC-NET-05` (Reference index + 24 class/enum/struct pages) CLOSED + independently reviewed, PASS
- [x] `TC-PSD-LNC-NET-10` (Pilot qualification: gate slice PASS, grades A, independent read-only review PASS) CLOSED — unlocks Blog/Docs/KB (`LNC-NET-02/03/04`) and (pending `REG-02`/`KNW-PY-01`) psd/python
- [ ] `LNC-NET-02` (Blog) IN PROGRESS: `-01` materialize CLOSED (3 post slugs seeded); `-02` blog index, `-S1..S3` posts, `-90` integration remain TODO
- [ ] `LNC-NET-03/04` (Docs/KB), `06` (family indexes/backlinks), `07` (truth audit/quality), `08` (readiness/CI), `09` (websites sync), `11` (post-launch registrations) not yet started
- [ ] `REG-02`/`KNW-PY-01`/`LPY-*` (psd/python) gated on `REG-02` closing (currently TODO) plus `HRD-04`/`HRD-11` (both already CLOSED)
- [ ] `XPR-01..03`/`REV-01..03`/`CLS-01` not yet started; `AUTH_PUSH=NO`/`AUTH_DEPLOY=NO` still in force — no push/deploy has occurred
- Commit policy update (owner decision 2026-10-07, supersedes the branch-isolation note below):
  commit a mission's own work directly on `main`, gradually in batches, via
  `git_plumb_commit.py --no-push` (never `--branch`); the risk that another session's push
  publishes it is an accepted risk, not a blocker.
- Incident F-PSD-12 (historical): this mission's first commit (6ac7cef1a5) was published to
  origin/main by another session's plumb push. All subsequent work has used `--no-push`
  consistently; 24 commits on `main` as of 2026-10-08, none pushed.
- Backlog: INV-014/015 updated; ST-242..ST-256 filed (generic defects and follow-ups).
