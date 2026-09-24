# Final Report: MT072-2026-09-23-EXAMPLE-VERIFICATION-PRODUCTIONIZATION

**Date**: 2026-09-24
**Taskcard**: TC-15 (final acceptance)
**Governing plan**: `plans/from_backlog/2026-09-23-example-verification-productionization.md`
**Verdict**: **3 of 4 questions YES with dated evidence; 1 (Q3) YES-with-a-disclosed-scope-boundary that itself surfaced a large new finding, filed rather than fixed.**

All 14 prior taskcards (TC-01 through TC-14) are `CLOSED`. This report re-runs the
mission's own four-question audit methodology against the changed system, as TC-15
requires, rather than re-asserting the taskcards' own closing claims.

## The four questions, re-audited today

### Q1 — "The verifier is thorough: it spans all platforms and products."

**YES.**

- `registry.py`'s `PLATFORM_CONTRACT` is generated from real runner introspection
  (`_build_platform_contract()` / `_introspect_ceiling_tier()`, TC-02) — not hand-typed —
  for all 7 platforms (go, net, java, rust, cpp, python, typescript).
- Live re-run today (2026-09-24, `example_verification_sweep.py`, command:
  `PYTHONPATH="scripts/pipeline;scripts/pipeline/lib" .venv/Scripts/python.exe
  scripts/pipeline/commands/governance/example_verification_sweep.py`):

  | Site | Pages | Pages with code |
  |---|---|---|
  | blog.aspose.org | 192 | 161 |
  | docs.aspose.org | 527 | 326 |
  | kb.aspose.org | 370 | 283 |
  | reference.aspose.org | 8047 | 22 |
  | products.aspose.org | 60 (excluded, frontmatter-embedded, disclosed) | — |

  **Total blocks classified: 3,858. Status counts: PASS 3,597, GRAMMAR-UNAVAILABLE 51,
  SHELL-NOT-CHECKED 138, NOT-EXECUTABLE-LANG 71, EMPTY 1. UNCLASSIFIED: 0.** Zero
  SYNTAX-ERROR remain (TC-10 fixed all 44 known + follow-ups; this re-run confirms none
  regressed and none new appeared). Report:
  `reports/example_verification_sweep/2026-09-24-full-sweep.json`.
- Locale pages get the bounded, explicit equivalence check the plan asks for (TC-14),
  not full re-execution — see Q3 below for what that check found.

### Q2 — "It is fully wired into the system."

**YES.**

- `lib/example_verification/api.py` + `cli.py` exist (TC-01), proven callable directly:
  `PYTHONPATH="scripts/pipeline;scripts/pipeline/lib" .venv/Scripts/python.exe -m
  example_verification.cli verify --file <path> --platform <p> --family <f>
  --max-tier 3 --allow-acquire` (used live throughout TC-13).
- `check_module_consumption.py` (TC-01's AST-based reverse-import walker, not the old
  substring heuristic) re-run today against `api.py` confirms **3 real, non-test
  consumers**: `commands/diagnostics/smoke_test.py` (S-63, TC-03 — `_check_file_tier3()`,
  `--max-tier 3` now real), `commands/foss/readme_refresh_run.py` (S-84/S-120's own
  `_LANGUAGE_RUNNERS`, TC-04 — extended to go/net/java/rust/cpp via
  `_package_verification_runner_for()`), `commands/knowledge/promote.py` (TC-06's
  post-promote proof sweep, `sweep_snippet_execution_proof()`).
- `launch_gate.py`'s `gate_l15_snippet_syntax()` and
  `content_eval/evaluators/example_execution.py`'s `_lookup_proof()` read
  `execution_proof`/the ledger directly (TC-05) — confirmed still wired via grep today
  (`lib.example_verification.registry.PLATFORM_CONTRACT` imported at
  `launch_gate.py:975`).
- Pre-commit Step 18/19 ("Go code block vet") dispatches through
  `example_verification.runners.go` (TC-08's ratchet-baseline generalization), with the
  one real GRADE_CONTRACT §10 Safety-Override-Findings entry added for `example_execution`
  (EX), FAIL-only/deterministic/already-tested, verified with a live full-portfolio
  re-run showing 0 real downgrades (commit `774746c810`).
- Each consumer's enforcement level is explicit, not uniform: S-63/S-84/knowledge-promote
  are advisory-integration (they call through and record, they don't yet block);
  `example_execution`'s SYNTAX-ERROR is the one fully-graduated, blocking
  Safety-Override-Findings category; everything else stays EXPERIMENTAL pending this
  repo's own 14-day/corpus/sign-off rule, exactly as the plan's own "Out of scope"
  section requires.

### Q3 — "It has run on all public examples."

**YES, with a disclosed scope boundary that itself found a new, real, large gap.**

- The durable, git-tracked execution-proof ledger (TC-07,
  `lib/example_verification_ledger.py`) is real and populated: **7,195 rows across 33
  `{family}_{platform}.jsonl` files** (66 files incl. `.head.json` sidecars, 5.7 MB),
  covering every family/platform this mission's sweeps have touched, schema-versioned,
  append-only, O_EXCL-locked.
- **Live, previously-undisclosed gap found and fixed during this taskcard**: the ledger
  was NOT actually git-tracked despite `git_tracking_policy.yaml`/the generated
  `.gitignore` block correctly negating it. A stray, hand-appended `/reports` +
  `/reports/plan_state` pair sat AFTER the generated block (`.gitignore`, uncommitted
  local diff present since before this session started — TC-09's own evidence log
  already disclosed this exact shadow live on 2026-09-23, "confirmed absent from HEAD,
  not caused by this taskcard," but it was never actually removed until now).
  `.gitignore` patterns are order-sensitive; a later pattern re-excludes what an earlier
  negation allowed. Confirmed via `git ls-files reports/example_verification_ledger/`
  returning 0 of 66 real on-disk files before the fix, 66 of 66 after. Fixed (override
  token `20260924-133436--gitignore`, consumed against this taskcard's own commit —
  removed the stray pair, deduplicated a 3x-repeated `/deletion-approvals` line to 1x,
  re-verified `git_tracking_policy_sync.py --check` still passes). The 66 ledger files
  plus both dated sweep reports (`reports/example_verification_sweep/2026-09-2{3,4}-full-sweep.json`)
  are committed in this same taskcard's commit as real, durable evidence — not merely
  claimed.
- Locale coverage (TC-14, new this taskcard): a bounded equivalence gate
  (`locale_code_block_equivalence.py`) compares every locale code block against its
  English counterpart (byte-equal, normalized) instead of re-executing the ~124k locale
  blocks (explicitly out of scope per the plan). Live run, 2026-09-24: 158,710 content
  files walked, 675 English pages-with-code compared against 19,618 real locale
  counterparts, **12,513 drift findings** (CONTENT_DRIFT 10,120, COUNT_MISMATCH 1,369,
  LANG_MISMATCH 1,024). This is a real, large, previously-unknown defect class — filed as
  backlog **ST-215** (not fixed here; the scale and the demonstrated mix of root causes —
  stale-English-vs-locale drift running in BOTH directions, fence-info-string loss —
  means a blanket fix would be guessing). This is why Q3 is YES-with-a-boundary rather
  than an unqualified YES: the plan's own bar for Q3 is "a bounded equivalence check,
  stated as a scope boundary, not silently dropped" — that bar is met; the underlying
  content defects it surfaced are a new, disclosed follow-on, exactly as intended.

### Q4 — "It has changed something real, with dated, attributable evidence of what and where."

**YES.**

Every taskcard's fix is a real, pushed commit on `main`, not a claim:

| Commit | Date | Taskcards | What |
|---|---|---|---|
| `bc69cdd05a` | 2026-09-23 | TC-01–TC-07 | Built + wired the missing `api.py` seam, registry introspection, ledger, post-promote sweep |
| `8bc75bdf01` | 2026-09-23 | TC-09, TC-10 | Fixed 44 real broken code examples found by the portfolio sweep |
| `774746c810` | 2026-09-23 | TC-08 | Activated `example_execution` (EX) as a GRADE_CONTRACT §10 Safety-Override-Findings category |
| `c519742679` | 2026-09-23 | TC-10 | Repaired 2 more real broken examples found by independent review |
| `7497d64ba4` | 2026-09-23 | TC-10 | Replaced "Example removed" placeholder markers with real examples or full page retirement (user correction) |
| `b22e412fb1` | 2026-09-24 | TC-13 | Fixed a real, previously-undisclosed bug: a tier-2 BUILD-VERIFIED-ONLY PASS was mislabeled TOOLCHAIN-UNAVAILABLE |
| `ad6faf2355` | 2026-09-24 | TC-11 | Collapsed `code_syntax_check.py`'s duplicate tree-sitter loader onto the shared `syntax.py` one |
| `f519ec9ca4` | 2026-09-24 | TC-12 | Pointed CI at all ~19 real test files (was 1); added toolchain setup; corrected the MT069 GHA-cost dossier |
| `2bd39f5626` | 2026-09-24 | TC-14 | Built the locale code-block equivalence gate; filed ST-215 for 12,513 real drift findings |
| *(this commit)* | 2026-09-24 | TC-15 | Fixed the `.gitignore` shadow blocking the ledger from being git-tracked; committed 66 real ledger files + 2 dated sweep reports + this report |

Defects this mission found but correctly did NOT fix — filed to backlog with a named
reason, per the plan's own disposition rule, not silently dropped:

| ID | What | Why not fixed here |
|---|---|---|
| ST-211 | ~2,290 locale files / 7,322 blocks with real SYNTAX-ERROR code (incl. a systemic `Aspose.3D.Converter` mistranslation) | Needs its own categorization pass before any bulk fix; out of TC-10's English-only scope |
| ST-212 | A classification blind spot in the sweep's own swallowed-fence handling | Needs a classifier fix + full re-run to reconcile counts |
| ST-213 | A section-evidence recompute side effect (grading pipeline drops tracked sections that are still present) | Found by review, not reproduced/root-caused by this mission |
| ST-214 | An unrelated `install_recipe` FAIL on one Arabic locale page | Pre-existing, in a section this mission's fix never touched |
| **ST-215** | 12,513 locale code-block drift findings (this taskcard, TC-14) | Scale + mixed root causes; needs its own scoped triage mission |

## Root causes closed (from the plan's own list)

| RC | Status |
|---|---|
| RC1 (no integration seam) | Closed — `api.py`/`cli.py` built and has 3 real consumers |
| RC2 (no persisted execution proof) | Closed — 7,195-row durable ledger, now actually git-tracked |
| RC3 (advisory-forever) | Partially closed — EX graduated to blocking via the repo's own 14-day rule; everything else deliberately stays advisory, per the plan's own scope |
| RC4 (5 separate syntax-check paths) | Closed for code_syntax_check.py (TC-11); Go's own path was already fixed pre-mission (MT065 C4) |
| RC5 (registry decoupled from runners) | Closed — `PLATFORM_CONTRACT` is introspected, not hand-mirrored |
| RC6 (proof sweep never built) | Closed — TC-06 + TC-09 |
| RC7 (CI runs 1 of 18 test files) | Closed — TC-12 |

## Honest self-assessment

This mission does not claim every locale code block is correct — it claims the
opposite is now measured, not assumed: 12,513 real drift findings exist and are
disclosed, not hidden. It does not claim full tier-3 execution across the whole
portfolio — java/rust/cpp toolchains were installed with explicit user consent
(TC-13) and real end-to-end builds were proven, but a full portfolio-wide tier-3 sweep
was never this mission's stated bar (Q1's own "YES means" table asks for classification
completeness, not universal execution depth). It does claim: every one of the four
original questions has a dated, re-checked-today answer; every defect found was either
fixed with a real commit or filed with a named reason; and this taskcard's own audit
found and fixed one more real, previously-disclosed-but-unfixed gap (the `.gitignore`
shadow) rather than accepting TC-07's "durable ledger" claim at face value.
