## Mission: MT035-2026-08-20-README-DISPOSITION-PORTFOLIO-CLOSURE
> Original plan file: `C:\Users\prora\.claude\plans\an-independent-review-reflect-dazzling-elephant.md`
> Taskcard ledgers: `reports/plan_state/readme-disposition-remediation-2026-08-18/taskcards.jsonl`,
> `reports/plan_state/readme-portfolio-closure-2026-08-19/taskcards.jsonl`
> Backlog items closed: TC-MICRO-02, TC-AUDIT-01, RC-C cluster (G-51), F-02
> Status: **CLOSED**

### What was completed

Began as an independent review of external claims about the `readme-refresh` (S-120) system
(origin history, prose authorship, programmatic-knowledge scope, portfolio-audit accuracy — 3 of
4 claims confirmed, 1 refuted). The review surfaced a materially worse finding than the original
critique: `audit_portfolio`'s `clean: true` conflated genuine disposition verification with
`published:true`'s deliberate MT053 skip (comparing a candidate against itself when
byte-identical to the live upstream README) — the "8/30 clean" headline actually meant "3/30
genuinely verified" (**TC-AUDIT-01**). This became the mission's real scope: take all 30 FOSS
README products through genuine, individually source-verified disposition compose, using the
repo's existing `taskcard_store.py` state machine (no new tracking layer), with scratch
control/treatment verification before every canonical promotion.

**TC-AUDIT-01** — CLOSED (`91a4dfd51d`). `audit_portfolio` now reports a real
`disposition_tracking` field (`verified`/`checked_dirty`/`skipped_published`) and
`disposition_verified_count`, so "clean via never-engaged" and "clean via real verification"
can no longer collapse into one boolean.

**F-02** — CLOSED (`fc28d32b9c`). `_do_push` no longer hardcodes a co-author model string;
requires a real `--acting-model`, with a regression test.

**TC-MICRO-02 (the bulk of the mission)** — CLOSED. All 30 products individually taken through:
real-unit extraction from the clone-cache old README, batch programmatic verification of every
class/method/API name in the candidate against live source (never trusting the old README or an
assumption), evidence pre-validation (every `evidence_ref` confirmed to resolve to a real file
before any check ran), scratch-tree control/treatment proof (`configure(reports_root=<scratch>)`,
run twice for determinism, sha256 comparison against canonical), then real canonical-tree
`audit_portfolio` confirmation. ~15 genuine content defects were found and fixed along the way,
not just bookkeeping — most notably `3d/typescript`, where 4 real product bugs (broken OBJ
import/export, broken GLB export, glTF round-trip node duplication) were confirmed by *running
the product's own `npx jest` test suite*, not just reading source, and documented in
`upstream-issues.md`. Other real defects: a false "PDF/X out of scope" claim (`pdf/java`), a
fabricated `SheetVisibility` API (`cells/java`), a fabricated public `FontRepository` type
(`pdf/go`), a stale fabricated dev-dependency claim (`words/python`/`slides/python` — the exact
defect that originally motivated `check_dependency_development_claim_not_in_manifest`), and a
false "leaked internal artifact" claim on `slides/net` that was independently re-verified and
found to actually be a check false positive (root-caused and fixed instead of blindly trusting
the prior label). Full per-product evidence is in the two taskcard ledgers above — not
duplicated here per this file's own "thin index, full content in the mission file, but per-
product evidence stays in its own ledger" convention (30 products' worth of evidence would
defeat the purpose of a summary).

**RC-C cluster (backlog G-51)** — CLOSED (`TC-RC-01` + children). `pdf/net` (58 findings, the
dominant case) and `note/python` (4 findings — 2 real disposition-metadata bugs, 2 genuinely
dropped facts independently re-verified against source and restored to prose) both closed with
real, source-grounded evidence; the fabricated `TC-MICRO-04` reference this cluster's own
finding warned about was never reused.

**3 real check-code bugs**, found live while composing, fixed together in one commit
(`bf9381af81`, 723 scoped tests green): `check_no_upstream_issue_leaked_into_readme` had a
punctuation-only-token false-positive path and a missing `## Dependencies` exemption;
`check_code_example_no_exact_duplicate_merge` lacked the evidence_ref-based exemption its
content-unit sibling already had. Plus one new `data/dependency_overrides.json` entry
(`3d/python`, the only Python product in the portfolio with a setup.py-only manifest — the
sanctioned override escape hatch, not a workaround).

### Verification performed

- Fresh, coherent, unscoped `audit_portfolio()` run (2026-08-20 ~17:45, no per-family timeout
  workaround needed): **30/30 clean, 0 dirty, `disposition_verified_count: 25`** — the other 5
  clean products report `skipped_published` on this specific run only because their candidate is
  currently byte-identical to their live README again (MT053's correct skip re-engaging); all 5
  were independently, genuinely verified during their own taskcard closures earlier in this
  mission (confirmed `CLOSED` with real `evidence_refs` in the ledger).
- Every product's closure included 2 deterministic scratch runs (identical `clean:true`) and a
  sha256 comparison of `readme.md` scratch-vs-canonical before promotion.
- Scoped test suite (`test_readme_refresh_checks.py` + `test_dependency_extract.py`): 723 passed
  after the 3 check-code fixes.
- All commits landed via `git_plumb_commit.py` (isolated temp-index plumbing, per AGENTS.md) with
  Tier-1 pre-commit-audit passing (35/36 steps, 1 skip) each time; retroactive skill-run records
  created and finalized against each real commit SHA.

### Remaining follow-ups (non-blocking, correctly out of scope for this mission)

- **TC-HARDEN-47/48** (P0) — republish `3d/net`/`3d/python` to their live upstream GitHub repos.
  Local candidates confirmed to carry the flat-topology diagram fix. Explicitly **not executed**
  as part of this mission — gated on a fresh, separate, explicit user go-ahead per this system's
  own invariant 9 (never push without per-action authorization).
- **New finding, not yet designed**: `cells/go` and `slides/cpp` both got a real `## Dependencies`
  section added locally this mission that their live upstream READMEs still lack (confirmed via
  live GitHub fetch, not assumed) — a local-ahead-of-live gap distinct from TC-HARDEN-47/48's
  confirmed regression case. Falls under the pre-existing W5 design gap (the `published` check is
  a byte-compare and structurally can't distinguish "local ahead" from "local differs") — flagged,
  not designed or fixed here, matching this mission's own explicitly-scoped-out decision to defer
  W5 as a separate follow-up rather than redesign shared comparison logic mid-mission.
- One accidental, low-risk side effect: a background agent working `pdf/java` ran a stray `rm -f`
  on an untracked scratch file (`scripts/ci/hooks/.tmp_hook_test.sh`, present at the start of this
  mission, unrecoverable via git since never committed). Verified nothing in the codebase
  references it by name, consistent with it being a disposable test artifact — flagged for the
  record, not treated as a defect requiring further action.

---
