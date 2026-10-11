# `/readme-refresh` — Plan-vs-System Forensic Reconciliation

> **Document role**: evidence-backed reconciliation snapshot. This document preserves the history,
> discrepancies, root causes, and full plan-to-system traceability of the `readme-refresh` (S-120)
> plan. It is **not** an execution authority: current execution status lives exclusively in the
> repository's own state machinery (`reports/readme_refresh_runs/`, the plan file's own taskcard
> registers, `reports/plan_state/`), and actionable work lives in the plan's own open taskcards.
> The concise agent-facing companion is
> [current-operational-reference.md](current-operational-reference.md).

---

## 1. Scope and source identity

**Source plan (out-of-repo, session-plan file):**

| Property | Attached snapshot (mission input) | Live at audit start | Live at audit end |
|---|---|---|---|
| Path | `C:\Users\prora\.claude\plans\d-users-prora-onedrive-documents-github-humble-tome.md` | same | same |
| Lines | 20,581 | 20,634 | **20,903** → 20,953 (post-audit re-pin) |
| Bytes | 1,694,099 | 1,697,943 | **1,718,828** → 1,723,163 |
| SHA-256 | `6ec5247d8112b618b85d63054393559821756d104a117eeb7119a012089729ca` | `953bfd… (953fbfd159a2efc7922320ad76fdcd090e4dbdff9430627c5fe998fd11f13b4c)` | `8f5fb4fe6e7c76bc521c85b38b6c7c044e5bf80307a5b46ffb0e9ba159cd09ea` → `09290ac0ef23237642e6cc9ffb013e34266f78eec48b3fd6a2fad7dda1051e3e` |
| Timestamp | — | 2026-08-18 20:34 local | 2026-08-18 21:03 local → ~21:25 local |

A **fourth** growth event (+50 lines, re-pinned during final reconciliation) was read in full: an
MT055-session addendum (before the MT056 section) recording TC-MICRO-03-03's completion — the
first-ever bare-`configure()` `audit-portfolio` run against the new default tree (**7/30 all hard
gates clear, 14 products detected `published`**, baseline captured at
`reports/_scratch/mt055_audit_portfolio_baseline_20260818.txt` explicitly for TC-MICRO-02-01), a
disclosed-unresolved transient `words/net` anomaly (not reproducible; attributed to concurrent
activity), a deliberate decision **not** to start TC-MICRO-02 during the live concurrency window,
and an integrity re-check confirming another agent's concurrent, non-conflicting additions to
`run.py` (530→912 diff lines; `ast.parse` clean; 757 scoped tests still green). See Appendix A
chunk 43.

The live plan was used as the primary source, per mission instruction. **The plan is a live,
actively-growing document**: it grew twice while this audit ran. The growth between the attached
snapshot and audit start, and again between audit start and audit end, is the **MT055 execution
record and the entire MT056 (Fifty-Sixth incident) section**, appended by one or two *other*
concurrently running sessions. All growth was read and is covered by the coverage ledger
(Appendix A); the audit's terminal state is the 20,903-line / `8f5fb4fe…` version, whose final
content is MT056's design register with an **empty execution record**. Any MT056 execution that
lands after 21:03 on 2026-08-18 is outside this snapshot.

The plan file is **not tracked in this git repository** (it lives under `~/.claude/plans/`), so it
has no git identity of its own; the hash above is its durable identity.

**Repository revision audited:**

- Repo: `d:\onedrive\Documents\GitHub\aspose.org`, branch `main`, HEAD `80de6805f3` ("fix(pipeline):
  recursively ground related/nested types in body-refresh's PARAGRAPH_REWRITE (ST-085)").
- **The working tree, not HEAD, is the live implementation.** The tree is heavily dirty: the
  readme-refresh skill's own files (`readme_refresh_run.py`, `readme_refresh_checks.py`, both test
  files, `skills/readme-refresh.md` + 3 mirrors, `data/diagram_archetypes.json`, and more) carry
  substantial staged-and-unstaged modifications from MT041–MT056, deliberately uncommitted per the
  sessions' own standing "no commit without a fresh, explicit go-ahead" practice.
- **Concurrency hazard, observed live**: `readme_refresh_checks.py`'s mtime advanced to 21:08 local
  (3 minutes before this audit's final spot-check) — the MT056 session was actively landing its new
  check functions while this audit ran. Every implementation claim in this document is therefore a
  **timestamped snapshot**, and is labeled as such where the timing matters.
- **Known index hazard**: the plan documents repeatedly (TC-HARDEN-18 et al.) that the shared
  `.git/index` holds stale snapshots of these exact files under concurrent-session load, and that
  committing the staged index as-is would produce a broken `readme_refresh_checks.py`. Nothing in
  this audit staged, committed, or reset anything.

---

## 2. Methodology

1. **Session gate**: `AGENTS.md` read in full first (mandatory per `CLAUDE.md`).
2. **Full sequential read of the plan** — all 20,903 lines, read start to finish in 42 chunks, with
   a durable coverage ledger written after every chunk (Appendix A, entries PC-001…PC-221). No
   search-based sampling substituted for the read; the file's mid-audit growth was detected via
   hash/`wc` re-pinning and the appended content read to EOF.
3. **Bottom-up implementation inventory**, independent of plan claims, via three parallel read-only
   agents: (a) code inventory (skill contracts, state machine, CLI, checks module, composition
   machinery, registries, git history); (b) run-state/evidence/publication-state inventory (run
   records, candidate trees, dispositions, ledgers, skill-run records, backlog, clone cache);
   (c) scoped test execution (the exact three test files, never the full suite, per standing repo
   feedback).
4. **Direct spot verification** of the highest-stakes contested claims (draft-PR flag, default
   candidate tree, MT056 artifact existence, hardcoded co-author trailer, check-function count),
   with mtimes recorded at observation time.
5. **Reconciliation**: every material plan item classified against the actual-status taxonomy;
   discrepancies traced to symptom → cause → root cause → structural weakness.
6. **Constraints honored**: no pending features implemented; no portfolio regeneration; no target
   repository touched; no historical evidence deleted; no commit made; unrelated in-flight changes
   preserved untouched. The only writes are this document, its companion, and session-scratchpad
   working notes.

**Verification commands actually run** (all read-only):

```bash
# identity pinning (run at 20:34 and again at 21:03 local)
wc -l ~/.claude/plans/d-users-prora-onedrive-documents-github-humble-tome.md
sha256sum ~/.claude/plans/d-users-prora-onedrive-documents-github-humble-tome.md
git rev-parse HEAD && git status --porcelain && git worktree list

# scoped tests (via agent; .venv/Scripts/python, PYTHONPATH=scripts/pipeline)
python -m pytest scripts/pipeline/tests/test_readme_refresh_checks.py -q     # 640 passed
python -m pytest scripts/pipeline/tests/test_readme_refresh_run.py -q       # 116 passed
python -m pytest scripts/pipeline/tests/test_dependency_extract.py -q       # 39 passed

# spot checks (snapshot 2026-08-18T16:11:21Z / 21:11 local)
grep -n '"--draft"' scripts/pipeline/commands/foss/readme_refresh_run.py     # :2864 present
grep -n '_DEFAULT_CANDIDATE_TREE_NAME' scripts/pipeline/commands/foss/readme_refresh_run.py  # = "repo-presenter-regen-full"
ls data/readme_candidate_store.json                                          # exists
grep -c '^def check_' scripts/pipeline/commands/foss/readme_refresh_checks.py  # 98 (was 97 an hour earlier)
grep -n 'Co-Authored-By: Claude' scripts/pipeline/commands/foss/readme_refresh_run.py  # :2836 hardcoded
```

**Deliberately not run**: `readme_refresh_run.py audit-portfolio` and any `verify-examples`
invocation — other sessions were actively mutating the exact files and candidate trees these read,
so a fresh run would have produced a misleading mid-mutation snapshot; the plan's own recorded runs
(latest 2026-08-18) plus the state-inventory agent's readings stand in as evidence, labeled as such.

---

## 3. Proof of complete plan coverage

The full coverage ledger is **Appendix A** (PC-001 through PC-221, 42 chunks, each row citing its
exact line range, subject, content type, and reconciliation classification). Properties:

- Line ranges are contiguous from line 1 to line 20,903 with **zero unexplained gaps**.
- The mid-audit file growth (20,634 → 20,903) is covered by PC-220–PC-221.
- Every row cross-references the reconciliation sections below via its classification column.

---

## 4. Historical timeline (missions, in plan order)

The plan is a narrative incident log of ~56 numbered incidents binding ~35 mission IDs. Dates are
the plan's own recorded execution dates; all verified closures were spot-checked against code/tests
where feasible (see §8/§9).

| Mission | Date(s) | Subject | Outcome |
|---|---|---|---|
| (pre-mission) | 2026-08-02–04 | 30-product batch README generation (manual, agent-driven, pre-CLI); compile/run verification sprint (241 code blocks); manual PR-push SOP; first 4 real PRs (`3d` family) | Executed by hand; the origin of the "manual process outran the skill" theme |
| MT015 (dependency) | 2026-07-30–08-04 | `data/package_registry.json` as sole package-identity source | Functionally complete; governance bookkeeping still informally open (out of this plan's authority) |
| MT021 | 2026-08-06 | Diagram capability-dependency edges; taskcard-driven; `check_only_mermaid_block_changed` | CLOSED (3 evidenced products; 27-product survey deferred → later superseded by diagram simplification) |
| MT023 | 2026-08-06 | `readme_refresh_run.py` + skill S-120 registration (build) | CLOSED (registered; but see MT033: unused until 2026-08-11) |
| MT024 | 2026-08-08 | 7 visitor-facing rules; **diagram simplification** (flat `StartingPoints → PRODUCT → Capabilities → Outputs`); 12 checks | CLOSED, 30/30 |
| MT025 | 2026-08-08–09 | Starting-Points presence + container format purity + 2-of-3 `check_diagram_verified_format_claims` | CLOSED, 30/30 |
| MT026 | 2026-08-09 | Mandatory banner (30/30 URLs live-verified) | CLOSED |
| MT027 | 2026-08-09 | API Reference grounded in `reference.aspose.org` graded content | CLOSED |
| MT028 | 2026-08-09 | Module-grouped API Reference tables (mirror of `_index.md`) | CLOSED (3d/typescript exception later fixed 2026-08-11) |
| MT029 | 2026-08-09 | 5 content-quality rules; upstream-leak fingerprints; `check_only_sections_changed` | CLOSED |
| MT030 | 2026-08-09–10 | Content-unit verified merge (`content-dispositions.json` replaces the never-built `dropped_claims.json`) | CLOSED 30/30 (139-unit gap honestly reopened and re-closed) |
| MT031 | 2026-08-10 | `### Project History`, `4_verifiable_history`, mixed-unit recovery | CLOSED |
| Plan File Hardening (4 passes) | 2026-08-10–12 | TC-HARDEN register, gate/evidence contracts, verification matrix, anti-overclaim rules | Landed; register itself later found self-contradicting twice and corrected (MT035) |
| MT032 | 2026-08-10–11 | PR/merge workflow: **draft mode retired**; agent-executed squash-merge; corrected again 2026-08-13 (explicit `--subject`/`--body`) | CLOSED (but see contradiction F-01 below) |
| MT033 | 2026-08-11 | Deep audit: skill never actually used; evidence tree absent; verify-examples a stub | CLOSED as audit → drove TC-HARDEN-12/13/14/15/16/17/18 |
| TC-HARDEN-13 / -01 / -04 | 2026-08-11–12 | First-ever real CLI e2e run (3d/typescript); Python verify-runner (opt-in); disposition-aware dropped-content downgrade | CLOSED |
| MT034 (+ Phase 2) | 2026-08-12 | Enterprise-link resolution wired (`backlink_targets`), license detection widened, duplicate-row check, prose-quality mechanism, Regeneration Comparison Protocol; 27-product rollout | CLOSED |
| MT035 | 2026-08-12–13 | Plan forensics: register self-contradictions fixed; new-product cold-start gaps (TC-HARDEN-30..37) | CLOSED |
| MT036 | 2026-08-13 | cells/java: live upstream package rename; `check_code_example_imports_match_source`; composition-contract port into skill doc | CLOSED |
| MT037 | 2026-08-13 | Key Capabilities SEO/variety/formatting; `keywords/` contamination filter | CLOSED |
| MT038 | 2026-08-14 | cells/net: first .NET product through the real CLI; disposition ID-drift (31/38) found | CLOSED |
| MT039 | 2026-08-14 | "mirrors reference.aspose.org" — 5th narration category; exemplar-contamination guard | CLOSED |
| MT040 | 2026-08-14 | Mermaid clipping reproduced against GitHub's real renderer; root = old wired model on 2 never-republished repos | Investigation CLOSED; **republication TC-HARDEN-47/48 remained open and were later LOST from the register (restored by MT056)** |
| MT041 | 2026-08-14 | Dependency accuracy: `dependency_extract.py` (7 ecosystems), `## Dependencies` required section, Claims Policy, 12 validators; cells/rust pilot | CLOSED |
| MT042 | 2026-08-14 | Badge floor (`_detect_available_badges` + hard gate) | CLOSED |
| MT043/MT044 | 2026-08-14 | Enterprise anchor semantics; **bridge-wording contract adopted then REVOKED same day** — permanent rule: never expose implementation bridges; platform-name-only anchors | CLOSED (17 files fixed both trees) |
| MT045 | 2026-08-15 | API-Reference collapse gate; Scope-limitations bullet-continuation bug fix | CLOSED |
| MT046 | 2026-08-15 | Section-intro meta-narration gate (font/python) | CLOSED |
| MT047 | 2026-08-15 | Code-example preservation system (`extract_old_readme_code_units`, `code-example-dispositions.json`, api-coverage-survives); internal-class-leak detector; `data/api_reference_class_exclusions.json` | CLOSED (portfolio dispositions authoring deferred) |
| MT048 | 2026-08-15 | note/python; **`check_content_unit_excerpt_matches_extraction`** — surfaced near-portfolio-wide disposition drift (58/60 combos) | CLOSED at machinery level; **drift remediation = largest open item** |
| MT049 | 2026-08-15 | Compound-excerpt partial-drop fix (sentence groups) | CLOSED (39 flagged entries deferred) |
| MT050 | 2026-08-16 | Install/Quick-Start leak gate; fingerprint fenced-code bug | CLOSED |
| MT051 | 2026-08-16–17 | page/python images restored; hybrid archetype added; image-exclusion heuristic; pdf/go Feature Showcase restored; 2 more machinery bugs (.NET dev-deps, bulleted names) | CLOSED |
| MT052 | 2026-08-18 | pdf/go "completely complete": mirrors-clause exemption, compound-token preference, 23 content gaps closed; full 59-heading audit | CLOSED (portfolio sweep of new gates deferred) |
| MT053 | 2026-08-18 | Published-state detection (`_readme_matches_published_upstream`; 25 preservation checks skip with disclosure); pdf/cpp 158→1 | CLOSED (published-then-edited state unsolved) |
| MT054 | 2026-08-18 | Audit feeding MT055 (RC-A..RC-H taxonomy; hardcoded tree paths; self-citation) | Referenced in plan (its own report lives in-session; register absorbed into MT055) |
| MT055 | 2026-08-18 | Micro-taskcard hardening: TC-MICRO-01 (tree-name config) CLOSED; TC-MICRO-04 (self-citation) CLOSED; TC-MICRO-03 canonical-tree decision **regen-full promoted to default**; TC-MICRO-02 (drift) OPEN | Partially executed |
| MT056 | 2026-08-18 (parallel session) | Convergent-idempotency design: candidate-store record, change scopes, acceptance registry, label-geometry gate, published-staleness tripwire; **restored lost TC-HARDEN-47/48** | Design registered; **execution record empty at audit end** (some artifacts already landing live: `data/readme_candidate_store.json` exists; 3 new check names present in checks.py at 21:08) |

---

## 5. Decision and supersession chains

Stable IDs D-01…D-15. "Current rule" is what a fresh agent must follow today.

| ID | Problem | Original decision | Implementation | Superseded by | Current rule |
|---|---|---|---|---|---|
| D-01 | README template | A/B/C bake-off (3 synthesized candidates) | Never executed | Golden-sample decision (2026-08-03) | Golden note/python sample + `## Documentation & Resources`; later + `## Dependencies` (MT041), `### Project History` (optional, MT031), `## Feature Showcase` (optional) |
| D-02 | Diagram model | Per-node wired star topology + archetype/FromScratch subgraphs + capability-dependency edges (2026-08-06) | Fully built, 30 products fixed | **MT024 simplification (2026-08-08)** | Flat `StartingPoints? → PRODUCT → Capabilities → Outputs`, zero per-node edges; archetype stores retained for ordering/container decisions only; `check_diagram_shape` blocks the old model |
| D-03 | Starting Points | Hybrid-only container (2026-08-08) | Built | **MT025 (2026-08-08)**: transform/compile REQUIRED, generative FORBIDDEN, hybrid exactly-2 | Archetype-general presence rule + container format purity |
| D-04 | Format truth | `formats.md` authoritative | `check_diagram_format_support_claims` | **MT025 Phase 0c (2026-08-09)**: formats.md unreliable | 2-of-3 multi-signal `check_diagram_verified_format_claims` (formats.md flag + prose w/ negation override + api_surface suffix evidence) |
| D-05 | Dropped content | `dropped_claims.json` (spec'd 2026-08-04) | **Never built** (2 prose mentions only) | MT030 (2026-08-09) | `content-dispositions.json` + 6-gate family; extended by structure/badge/code-example sibling files (MT024th-mission/MT047) |
| D-06 | PR mode | Draft PRs, human clicks merge | Manual SOP used drafts (2026-08-04) | **MT032 (2026-08-10)**: no draft; **2026-08-11**: agent executes squash-merge on explicit per-PR go-ahead; **2026-08-13**: always explicit `--subject`/`--body`, exactly one model co-author trailer | No `--draft`; agent merges via `gh pr merge --squash --delete-branch --subject … --body …` after user reviews and gives per-PR go-ahead. **See F-01: the CLI push code still contradicts this.** |
| D-07 | Enterprise anchor | v1: naming+context check only | `check_enterprise_edition_naming` | MT034 (target resolution) → **MT043 bridge-wording contract → REVOKED same day by MT044** | Platform-name-only anchor (leading public platform from compound slugs via `PLATFORM_ALIASES`); family-neutral only when no platform page exists; **never** expose implementation bridges anywhere (`check_no_implementation_bridge_disclosure`, hard) |
| D-08 | Verify examples | Mandatory compile/run per run (2026-08-03 contract) | Honest stub (`TOOLCHAIN-UNAVAILABLE`) for all languages | TC-HARDEN-01 (2026-08-12): Python-first, opt-in | Real Python runner via `verify-examples --python-runner`; other 6 languages remain disclosed stubs |
| D-09 | Candidate tree | `reports/repo-presenter/` (original) | All early pushes from it | Twenty-Fourth mission (2026-08-13): "use ONLY regen-full for target repos this pass" → **TC-MICRO-03 (2026-08-18)**: user decision, regen-full = default | `_DEFAULT_CANDIDATE_TREE_NAME = "repo-presenter-regen-full"` (verified in code); `repo-presenter` frozen-historical, addressable via `configure(candidate_tree_name=…)`; MT056 adds `data/readme_candidate_store.json` + integrity gates (landing at audit end) |
| D-10 | Skill as mechanism | CLI state machine = the vehicle (design) | Zero real runs until 2026-08-11 (MT033) | TC-HARDEN-13 e2e + MT038/MT053 usage | The CLI chain is proven and used (7 runs, 1 live PUSHED); routing real work through it is required going forward |
| D-11 | Old-README preservation scope | Links + headings only | `check_dropped_content` | MT030 (prose units) → MT047 (code units, unconditional extractor) → MT048 (excerpt-fingerprint drift gate) → MT053 (published-state bypass) | Four disposition families (content/structural/badge/code-example), each with coverage/evidence/merge gates; all 25 preservation keys skip with disclosure when candidate == published upstream README |
| D-12 | check_diagram_connectivity | Directed-BFS orphan check (2026-08-03) | Built, ID-classified (2026-08-06) | **Retired by MT024** | `check_diagram_shape` + `check_diagram_column_balance` (+ `check_diagram_label_token_length` heuristic; MT056's `check_diagram_label_geometry` hard gate landing at audit end) |
| D-13 | Upstream-defect disclosure | PR body carried "Found during verification" | Early 3d PRs | **MT032 retired it**; MT029 leak fingerprints; Twenty-Third-incident public-source allowlist (2026-08-13) | Upstream defects live only in local `upstream-issues.md` (never pushed); README may state a limitation only if in an approved public source; non-forensic pointer sentences only |
| D-14 | Prose quality | Implicit agent judgment | — | TC-HARDEN-22 (2026-08-12) + MT039/MT046 guards | Mandatory tone-exemplar reading (contamination-checked), positive rubric, Regeneration Comparison Protocol; gates catch facts/structure — "reads naturally" stays a human call |
| D-15 | Mission governance | Register in `mission_authority.py` / master-plan | Deliberately never done (root slot occupied; lock contention) | **Partially superseded 2026-09-01 (ST-157, `mission_id_ledger.py`)** | For the mission NUMBER only: root-slot contention no longer blocks getting a collision-free id -- run `python scripts/pipeline/commands/governance/mission_authority.py allocate --track readme-refresh --slug SLUG` (never touches the root slot, never contends with whatever mission currently occupies it). The rest of D-15's original finding stands unchanged: plan file + memory remain this track's actual mission record (TC-HARDEN-06 registering full mission narratives in `mission_authority.py` is still open, P3); repo `reports/plan_state/` still holds only MT021/MT023/MT030/MT034 fragments. This repo's own MT041-MT056 numbers (this table, above) were confirmed live 2026-09-01 to have no numeric-collision risk against the main track's ledger as of MT060 -- backfilled as reserved placeholders in `scripts/pipeline/config/mission-ids.jsonl` so neither track can ever re-mint them. |

**Rejected designs (never revived):** foss-java-publish as architectural model; template
bake-off; per-product freeform diagram shapes; mermaid custom styling; storing GitHub social-preview
URLs in READMEs (proven 5-minute expiry); a `main()` catch-all exception handler (explicitly
declined, recorded); a new `dependency-dispositions.json` sibling file (reversed in favor of enum
extension); the MT043 bridge-anchor contract (revoked by MT044); `git stash` as a baseline
technique (banned after a live ST-021 near-miss).

---

## 6. Current architecture (as of 2026-08-18 ~21:11 local, working tree)

- **Skill**: S-120 `/readme-refresh`, thin CONTRACT doc `skills/readme-refresh.md` (verified:
  2026-08-18) + 3 mirrors (`.agents/`, `.claude/commands/`, `.kilocode/`) — all four in parity.
- **State machine**: `scripts/pipeline/commands/foss/readme_refresh_run.py` (~3,085 lines).
  States: `CREATED → INPUTS_PINNED → PLANNED → VERIFYING_EXAMPLES → AWAITING_REVIEW → APPROVED →
  PUSHING → PUSHED`; `AWAITING_REVIEW→PLANNED` and `APPROVED→PLANNED` rework paths; `PUSHING→APPROVED`
  dry-run return; `BLOCKED` re-enterable from 4 states; terminals `PUSHED`/`ABANDONED`.
  12 CLI verbs: `start` (`--skip-preflight`), `plan`, `ingest-candidate`, `recheck`
  (`--allowed-headings`, `--mermaid-only`), `verify-examples` (`--python-runner`), `status`,
  `verify`, `approve` (`--note` required), `push` (`--dry-run`), `abandon`, `recover`,
  `audit-portfolio` (portfolio-wide, no run-id, `--json`, `published` field). Exit codes 0/2, one
  exception type, `FileLock` + per-product `ACTIVE.json`, session-owner check on every mutating verb.
- **Checks**: `readme_refresh_checks.py` (~8,400+ lines), **98 top-level `check_*` functions**
  (growing live), aggregated by `_run_deterministic_checks` into **~101 result keys (≈64 hard-gate /
  ≈39 advisory)** — hard-gate findings block `ingest-candidate`.
- **Dependency extraction**: `dependency_extract.py` (975 lines) — 7 stdlib-only ecosystem parsers
  → `DependencySnapshot` (`dep-snapshot-v1`), overrides at `data/dependency_overrides.json`.
- **Composition**: **no template engine exists**. The agent composes `readme.md` from
  `facts/factpack.json` (≈20 `_detect_*` fields: license, install, enterprise link + relationship,
  homepage, archetype, SEO keywords (filtered), dependency snapshot, available badges, reference API
  index, old-README inventory incl. content/structural/code/badge units) under the skill-doc's
  composition contract; the check battery enforces.
- **Canonical candidate store**: `reports/repo-presenter-regen-full/{family}/{platform}/`
  (default since TC-MICRO-03, 2026-08-18; `data/readme_candidate_store.json` present).
  `reports/repo-presenter/` = frozen historical tree. Sibling artifacts per product: `readme.md`,
  `upstream-issues.md`, `content-dispositions.json`, `structure-dispositions.json`,
  `badge-dispositions.json`, `code-example-dispositions.json`, (pilot) `acceptance-registry.json`.
- **Run evidence**: `reports/readme_refresh_runs/{f}/{p}/{run_id}/` — 7 CLI runs ever
  (6 ABANDONED verification runs; **1 PUSHED**: note/python `rr-20260815T191258Z…` → live PR #5,
  2026-08-15) + one out-of-band `cells/cpp/healing-2026-08-13` bundle.
- **Action ledger**: `reports/repo_presenter_actions.jsonl` — 1 row (note/python PR #5). Earlier
  manual-SOP pushes predate the ledger and were deliberately not backfilled.
- **Publication state** (per plan records; machine stores know only PR #5): ~14 repos have merged
  README PRs — `3d/{java,net,python,typescript}` (2026-08-04/05, +follow-ups #2 for java/typescript
  2026-08-11), `cells/{cpp,go,java,net,typescript}` (2026-08-13/14), `note/python` (2026-08-15,
  via CLI), plus `pdf/cpp` and `words/net` confirmed byte-identical-published (MT053).
- **Data files consumed (read-only unless noted)**: `data/products.json` (31),
  `registry_exclusions.json`, `package_registry.json`, `aspose_com_targets.json` +
  `backlinks/platform_canonical_overrides.yaml`, `diagram_archetypes.json` (5 entries — writer:
  this skill's archetype passes), `diagram_capability_dependencies.json` (30 entries),
  `format_descriptions.json`, `families.json`, `keywords/{family}.json`,
  `api_reference_class_exclusions.json`, `dependency_overrides.json`,
  `readme_candidate_store.json` (new, MT056).
- **Tests**: `test_readme_refresh_checks.py` (640), `test_readme_refresh_run.py` (116),
  `test_dependency_extract.py` (39) — **795/795 passing** on the working tree (this audit,
  2026-08-18; run.py suite ~2 min).

---

## 7. Capability inventory (bottom-up, status per taxonomy)

Statuses: `IMPLEMENTED_AND_WORKING` (IW), `IMPLEMENTED_BUT_UNVERIFIED` (IU),
`IMPLEMENTED_WITH_LIMITATIONS` (IL), `PARTIALLY_IMPLEMENTED` (PI), `PRESENT_BUT_BROKEN` (PB),
`STUB_OR_PLACEHOLDER` (ST), `NOT_IMPLEMENTED` (NI), `OBSOLETE_IMPLEMENTATION` (OB), `UNVERIFIED` (UV).

| ID | Capability | Component / entry point | Status | Evidence / limitation |
|---|---|---|---|---|
| CAP-01 | Run state machine + locking + session binding | `readme_refresh_run.py` (`start`…`abandon`) | **IW** | 116 tests; 7 real runs; transition table verified in code |
| CAP-02 | Factpack generation (`plan`) | `plan_run` + ~20 `_detect_*` | **IW** | Real factpacks on disk; tests |
| CAP-03 | Deterministic check battery (`ingest-candidate`/`recheck`) | `_run_deterministic_checks` (~101 keys) | **IW** | 640 tests; dozens of documented real-content fail-closed proofs |
| CAP-04 | Change isolation (`recheck --allowed-headings/--mermaid-only`) | `check_only_sections_changed` / `check_only_mermaid_block_changed` + rolling snapshot | **IW** | Wired TC-HARDEN-12 (2026-08-11); used in most later missions |
| CAP-05 | Example verification — Python | `verify-examples --python-runner` (opt-in) | **IL** | Real venv + pip + execution; proven live (email/python 14 blocks); opt-in only; no Fragment-preamble synthesis |
| CAP-06 | Example verification — Java/.NET/Go/Rust/C++/TS | `_default_verification_runner` | **ST** (honest, disclosed) | Every block `BLOCKED-WITH-REASON: TOOLCHAIN-UNAVAILABLE`; the only real compile/run pass was the manual 2026-08-03/04 sprint |
| CAP-07 | Push (dry-run) | `push --dry-run` → disposable clone, commit-tree, receipt | **IW** | TC-HARDEN-13 real proof (3d/typescript) |
| CAP-08 | Push (live) via CLI | `_do_push` live path | **IL** | Proven once live (note/python PR #5, 2026-08-15). `--draft` contradiction (F-01) fixed in-tree mid-audit (21:19); hardcoded `Co-Authored-By: Claude Sonnet 5` (F-02, now run.py:3504) still open |
| CAP-09 | Post-push `verify` | `verify` | **IU** | Code + tests exist; no recorded live use beyond PR-#5 flow |
| CAP-10 | Resume/recovery | `BLOCKED`→`recover`→resume_state | **IW** | Tested; exercised in MT041's plan-block proof |
| CAP-11 | Portfolio audit | `audit-portfolio` (+`published` field, `--candidate-tree` per MT056 design) | **IW** | Built TC-HARDEN-05; drop-in-equivalence proven vs scratch script; repeatedly used |
| CAP-12 | Old-README content-unit preservation | `extract_old_readme_content_units` + `content-dispositions.json` + 8-gate family (incl. excerpt-drift, self-citation, compound-token, mirrors-clause, redundant-claim) | **IW** (machinery) / **PI** (portfolio data) | Machinery heavily tested; **portfolio disposition files drifted in ~58/60 (MT048), only partially remediated** — see F-05 |
| CAP-13 | Structural-unit preservation (dir trees) | `extract_old_readme_structural_units` + gates + canonical box-drawing gate | **IW** | cells/go + cells/java + page/python real uses; coverage only 3 products in old tree / 24 in canonical |
| CAP-14 | Badge extraction/reconciliation + floor | `extract_badges`/`reconcile_badges` + `check_badge_row_meets_verified_floor` + `_detect_available_badges` | **IW** | 30/30 floor-clean at MT042; badge dispositions exist for ~19 canonical products |
| CAP-15 | Code-example preservation | `extract_old_readme_code_units` + `code-example-dispositions.json` + api-coverage-survives + CLI-category | **IW** (machinery) / **PI** (data: dispositions authored for only a handful of products) | 1,378 units extracted portfolio-wide; authoring deferred by design |
| CAP-16 | Diagram validation (current model) | `check_diagram_shape`, `column_balance`, `starting_points_presence`, `container_format_purity` ×2, `verified_format_claims`, `hybrid_reverification`, `matches_capability_dependencies`, `known_subgraph_ids`, `label_token_length` (adv.), `container_duplicates_capability` (adv.), `format_completeness_hint` (adv.) | **IW** | Extensive tests; hybrid freshness re-triggers daily **by design** |
| CAP-17 | Diagram label geometry (bulk clipping guard) | `check_diagram_label_geometry` (MT056) | **IW (landed mid-audit)** | Present in checks.py (21:08) and wired as a HARD gate in run.py:1995 (21:19); plan execution record still pending |
| CAP-18 | API-Reference grounding + table mirror + collapse | `parse_reference_api_index` (+class-heading fallback), table completeness (case-insensitive modules), no-duplicate-rows, detail-collapse gate, internal-only heuristic + exclusions file | **IW** | MT027/028/045/047/048 chains; internal-only heuristic never portfolio-run (perf) |
| CAP-19 | Enterprise link resolution + anchor semantics | `_detect_enterprise_link` (+canonical_overrides) + `_classify_enterprise_relationship` (platform/family/unresolved, `public_platform`) + anchor gate + `check_no_implementation_bridge_disclosure` | **IW** | MT044 final; both trees swept clean 2026-08-14 |
| CAP-20 | Dependencies system | `dependency_extract.py` + `## Dependencies` required section + Claims Policy + 12 validators + verification matrix | **IW** | 39+ tests; cells/rust pilot; **rollout gap**: 16/30 old-tree candidates lack the section (a driver of the tree decision) |
| CAP-21 | Published-state detection | `_readme_matches_published_upstream` + 25-key disclosed skip + `readme_already_published` | **IW** | pdf/cpp 158→1 live proof; words/net verified; **published-then-locally-edited state unsolved (5 products)** |
| CAP-22 | Narration/leak protection | `_PROCESS_NARRATION_PATTERNS` (hard), upstream-leak fingerprints (+install/quickstart companion), internal-label patterns, section-intro meta-narration, license fixed-template gate | **IW** | Multiple live catches; disclosed reactive-phrase-list limit |
| CAP-23 | SEO keywords | `_detect_seo_keywords` + relevance filter | **IL** | Works; `keywords/` data confirmed cross-platform contaminated (upstream-owned); filter drops wrong-platform phrases |
| CAP-24 | Prose-quality process | Tone exemplars (contamination-checked), rubric, Regeneration Comparison Protocol | **IW (process)** | In skill doc; exercised in MT034 reproof + regen-full comparison passes; not mechanically certifiable by design |
| CAP-25 | Canonical-store integrity | `data/readme_candidate_store.json` + `check_candidate_store_integrity` + change scopes + acceptance registry (MT056) | **PI → IW (landed mid-audit, unrecorded)** | Store file exists; declare-scope/accept-blocks/converge-verify + scope enforcement wired in run.py (21:19); plan execution record + tests-count confirmation pending from that session |
| CAP-26 | `/repo-presenter-metadata` skill | design only (state machine, `repo_metadata_run.py`, `repo_metadata_checks.py`, `data/repo_metadata_state.json`) | **NI** | TC-HARDEN-08 open (P3); needs explicit go-ahead |
| CAP-27 | Republication of stale published READMEs | TC-HARDEN-47/48 (3d/net, 3d/python) | **NI (action)** | Live clipping confirmed on GitHub 2026-08-14; cards LOST then RESTORED by MT056; `check_published_readme_current` tripwire designed |
| CAP-28 | Recurring/scheduled re-validation | (half of TC-HARDEN-05) | **NI (deliberate)** | On-demand `audit-portfolio` real; scheduling needs a user decision (`reports/` invisible to CI) |
| CAP-29 | Durability of `reports/repo-presenter*` deliverable | TC-HARDEN-17 | **NI (policy)** | Single-machine, gitignored; explicit user decision required |
| CAP-30 | Skill-registration plumbing | skills.md row, DAR rows, 4-tree mirrors, `scripts/pipeline/config/registry.yaml` entries | **IW** | One stale registry description ("21 deterministic checks" vs real ~98/101); `sync_providers.py` extraction bug affects 14 skills repo-wide (disclosed, unfixed, out of scope) |

---

## 8. Plan-to-system reconciliation matrix (material items)

Actual-status values per mission taxonomy. Counts summarized in §15.

| Item | Plan claim | Verified actual status | Discrepancy / disposition |
|---|---|---|---|
| REC-01 State machine + 12-verb CLI | Built, used | **CURRENT_AND_COMPLETE** | none |
| REC-02 Check battery (98 fns / ~101 keys) | Current | **CURRENT_AND_COMPLETE** | Registry.yaml description stale ("21 checks") — doc fix |
| REC-03 `verify-examples` all-languages | Contract says mandatory compile/run | **CURRENT_BUT_PARTIAL** | Python real (opt-in); 6 languages honest stubs (TC-HARDEN-01 remainder, P0-for-those-languages) |
| REC-04 Live CLI push | Plan (§12 closeout) said "live push remains open"; later note/python PR #5 executed | **CURRENT_BUT_PARTIAL** | One live push proven; **code carries `--draft` + hardcoded co-author contrary to plan rules** → CONTRADICTED_BY_IMPLEMENTATION on those two specifics (F-01/F-02) |
| REC-05 `dropped_claims.json` | Spec'd 2026-08-04 as a real gate | **SUPERSEDED** (never built) | Replaced by content-dispositions system (D-05) |
| REC-06 Old diagram standard + connectivity checker + capability-dependency visual edges | "CLOSED" (2026-08-06) | **SUPERSEDED** | MT024 flat model; stores repurposed; connectivity checker retired (D-02/D-12) |
| REC-07 27-product capability-dependency survey | "Deferred, separate pass" | **NO_LONGER_NEEDED** | The visual-edge model it fed was retired; ordering data now complete (30 entries) |
| REC-08 MT043 bridge anchor contract | Adopted 2026-08-14 | **REJECTED** (same day) | MT044 permanent inversion; disclosure regex now a prohibition |
| REC-09 Draft-PR retirement (MT032) | "PRs no longer open as drafts" | **CURRENT_AND_COMPLETE (fixed mid-audit)** | Was CONTRADICTED_BY_IMPLEMENTATION at 21:11 (`run.py:2864` passed `--draft`); resolved by the MT056 session's 21:19 edits (verified 21:25: flag absent). F-01 |
| REC-10 Co-author = real acting model, never hardcoded | Plan rule (MT032 item 4) | **CONTRADICTED_BY_IMPLEMENTATION** | `run.py:2836` hardcodes `Claude Sonnet 5`. F-02 |
| REC-11 Portfolio disposition-drift remediation | MT048 deferred item 1; MT055 TC-MICRO-02 | **ACCEPTED_PENDING (P0)** | Largest open body of work; re-scan needed first (numbers stale) |
| REC-12 Canonical tree decision | Open across 6 incidents | **CURRENT_AND_COMPLETE (decision)** / reconciliation **ACCEPTED_PENDING** | Decision made 2026-08-18 (regen-full default, verified in code); old-tree retirement + mechanical promotions + NEEDS_REVIEW triage remain (TC-M56-01) |
| REC-13 TC-HARDEN-47/48 republication (3d/net, 3d/python) | MT040 P0 cards | **ACCEPTED_PENDING (P0)** — were **LOST from the register**, restored by MT056 | Live clipping still on GitHub; F-04 |
| REC-14 Published-then-locally-edited products (cells/go, cells/java, cells/net, 3d/java, 3d/typescript) | Disclosed unsolved (MT053) | **BLOCKED (design)** | Needs its own design; falls through to drifted preservation tracking meanwhile |
| REC-15 `/repo-presenter-metadata` + `repo_metadata_state.json` + actions-ledger-in-`data/` | Full design in plan | **INTENTIONALLY_DEFERRED** (skill NI) | Note: actions ledger was built at `reports/repo_presenter_actions.jsonl` (not `data/` as first spec'd) — location supersession, works |
| REC-16 MT056 gates (store integrity, change scopes, acceptance registry, label geometry, published-staleness) | Cards READY; execution record still empty in plan | **PARTIALLY_IMPLEMENTED → substantially landed (21:19)** | Verified 21:25: `declare_scope`/`accept-blocks`/`converge-verify` + `_apply_scope_enforcement` wired into `recheck`; acceptance-registry paths/loaders present; `check_diagram_label_geometry` wired as a HARD gate (run.py:1995); `data/readme_candidate_store.json` exists; run.py grew ~3,085→~3,540+ lines. Plan's execution record lagging code — expect it to be appended by that session |
| REC-17 Internal-class-leak heuristic at portfolio scale | Deferred twice (perf) | **INTENTIONALLY_DEFERRED (P2)** | Needs patient/parallel run |
| REC-18 Scratch verify scripts retirement | TC-HARDEN-14 partially_done | **ACCEPTED_PENDING (P2)** | `audit-portfolio` replaced phase2_scan; equivalence proof for the 2 originals pending |
| REC-19 Recurring re-validation trigger | TC-HARDEN-05 half | **INTENTIONALLY_DEFERRED (needs user decision)** | On-demand real |
| REC-20 `reports/` durability | TC-HARDEN-17 | **BLOCKED (user policy decision)** | P1 exposure of the entire deliverable |
| REC-21 SKIP_SKILL_CONTEXT_CHECK=1 live env bypass | TC-HARDEN-02 blocker | **BLOCKED (external/user)** | Was live 2026-08-08; cannot be cleared by agents; re-check per session |
| REC-22 DAR gate unsatisfiable for bare-data-file rows (6 skills) | TC-HARDEN-03 | **ACCEPTED_PENDING (P2, governance-owned)** | Out of this skill's authority |
| REC-23 Mission registration in master-plan | TC-HARDEN-06 | **INTENTIONALLY_DEFERRED (P3)** | Root-slot + lock-contention reasons recorded |
| REC-24 `words/net` package_registry `published:false`; `email/net` casing | Real registry data bugs, disclosed | **BLOCKED (MT015-owned data)** | Skill is read-only consumer; heuristic downgrade absorbed the risk |
| REC-25 pdf/cpp 182 generic descriptions | TC-HARDEN-09 P4 | **INTENTIONALLY_DEFERRED** | Heuristic, editorial |
| REC-26 MT049 39-entry sweep / MT052 32-combo sweep / MT055 13-combo self-citation sweep findings | Report-only by design | **ACCEPTED_PENDING** (folded into TC-MICRO-02's W2 backlog) | |
| REC-27 font/python 3 image dispositions (old tree) | Honest editorial exclusions | **INTENTIONALLY_DEFERRED (P2)** | Later partially resolved in follow-up (repo-presenter images restored 2026-08-17); regen-full bookkeeping fixed |
| REC-28 Skill-doc claims (fn counts, dates) | Historically wrong repeatedly ("47", "83"…) | **CURRENT** as of 2026-08-18 (verified: 2026-08-18) but structurally drift-prone | Hand-maintained count vs live 98 — F-08 |
| REC-29 Manual SOP as push procedure | "the literal source for the eventual push subcommand" | **LEGACY_CONTEXT_ONLY** (procedure superseded by CLI + MT032/23rd-incident merge rules; still the fallback documentation) | |
| REC-30 Early "Immediate execution" output path `repo-presenter/` at repo root | Historical text | **LEGACY_CONTEXT_ONLY** | Actual path `reports/repo-presenter/` throughout |
| REC-31 Memory-file claim "push still opens draft PRs (2026-08-16)" | MT056 R-19 judged it "unsupported" | Memory claim was **CORRECT in substance** | The CLI code does pass `--draft`; MT056's refutation looked only at recorded PR states (mostly manual-SOP pushes). F-01 refines both records |
| REC-32 Fifteen/Seventeenth incident numbering | Incident ordinals jump (14th→18th→15th…; two "MT052 EXECUTION RESULTS" headings) | **LEGACY_CONTEXT_ONLY** | Narrative bookkeeping quirk; content complete; noted so future readers don't infer missing text |

---

## 9. Implemented and working (headline list)

State machine + CLI (12 verbs) · factpack with ~20 verified detectors · ~101-key check battery
(64 hard gates) · change-isolation gates · Python example runner (opt-in) · dry-run push ·
one proven live CLI push · portfolio audit tool (`audit-portfolio`, `published` field) ·
four-family old-README preservation system with drift/self-citation/compound-token/mirrors-clause
precision fixes · published-state bypass · diagram validation suite (flat model) ·
API-Reference grounding/mirror/collapse system · Enterprise-link resolution with platform-only
anchor semantics and bridge-disclosure prohibition · dependency extraction + Dependencies section +
Claims Policy · badge floor + reconciliation · narration/leak gate family · SEO keyword filter ·
prose-quality process · registration/mirrors/DAR plumbing · 795/795 scoped tests.

## 10. Partial, broken, pending, deferred, blocked (consolidated)

**Partial**: verify-examples (Python only) · live-push confidence (1 run; code contradictions
F-01/F-02) · MT056 gate suite (landing) · disposition data completeness (drift + unauthored
code/structure/badge files for most products) · TC-HARDEN-14 script retirement.

**Broken/contradicted (code vs plan)**: `--draft` in `_do_push` (F-01) · hardcoded co-author
(F-02) · stale registry.yaml check-count description (F-08, doc-level).

**Pending (accepted)**: TC-MICRO-02 portfolio drift remediation (P0, largest) · TC-HARDEN-47/48
republications (P0) · TC-M56-01..08 execution · MT052/MT049/MT055 sweep-finding triage ·
old-tree reconciliation/retirement · portfolio internal-class-leak run · code-example disposition
authoring (~29 products).

**Intentionally deferred**: `/repo-presenter-metadata` skill · recurring re-validation trigger ·
mission registration · pdf/cpp filler descriptions · security/ops repo settings (explicit
instruction) · forum.aspose.com / *.aspose.app links (standing policy block).

**Blocked (external)**: SKIP_SKILL_CONTEXT_CHECK env (user) · `reports/` durability (user policy) ·
DAR bare-data-file gate (governance tooling) · package_registry data bugs (MT015 owner) ·
`formats.md` / `keywords/` / reference-site data quality (upstream pipelines) ·
published-then-edited state (needs its own design).

## 11. Superseded / redundant / legacy (headline list)

Superseded: A/B/C templates · wired diagram model + connectivity checker + FromScratch subgraphs ·
hybrid-only Starting Points · formats.md-as-sole-authority · `dropped_claims.json` ·
draft-PR + human-click merge + "Found during verification" PR section · MT043 bridge contract ·
`check_api_reference_intro_names_classes` (folded) · `check_diagram_format_support_claims`
(deleted for verified-claims) · 2026-08-03 diagram-standard subsection (pointer left in place) ·
`repo-presenter` as default tree. Redundant/legacy-context: the 2026-08-02–04 manual sprint
procedures (verification lanes, toolchain drive layout), the pre-CLI SOP, per-incident execution
logs — all retained as history; none are current instructions.

---

## 12. Contradictions and plan-status inaccuracies (F-register)

| ID | Finding | Evidence | Impact | Correct source of truth | Disposition |
|---|---|---|---|---|---|
| F-01 | **CLI push still opened draft PRs** despite MT032 (2026-08-10) retiring drafts | `run.py:2864` (`"--draft"`), snapshot 21:11 2026-08-18; MT032 text; SOP updated but CLI never was. **RESOLVED in working tree during this audit**: re-verified 21:25 — the flag is gone (`gh pr create` now at run.py:3537, no `--draft`), removed by the parallel MT056 session's 21:19 edit wave | Was: next CLI live push would contradict the decided workflow; also, MT056 R-19 had wrongly cleared the related memory claim by checking PR states of manual pushes only | Plan MT032 = the decided rule; code now matches | **Fixed in tree (uncommitted)** — confirm a regression test exists when MT056's execution record lands |
| F-02 | **Hardcoded `Co-Authored-By: Claude Sonnet 5`** vs "read the real acting model fresh each time; never hardcode" | `run.py:2836` at 21:11; **still present at 21:25 (now run.py:3504)** after the MT056 edit wave; MT032 item 4 | Wrong attribution the moment a different model executes a push | Plan rule | **Open defect** |
| F-03 | Plan self-register drifted twice: 11 taskcards with CLOSED headers but stale Status fields; truncated SHA ×3 | MT035 finding set 1 (fixed in place) | Historical; fixed | — | Closed; illustrates register-maintenance fragility |
| F-04 | **TC-HARDEN-47/48 lost from the "exhaustive" MT055 register** while their P0 defect stayed live on GitHub | MT056 pattern-7 finding; MT040 record | Live user-visible clipping on 2 public repos since 2026-08-05 | MT056 restored cards + `check_published_readme_current` design | Open P0 |
| F-05 | "N/30 clean" certifications decay silently (MT024 clean → MT028 content re-dirtied it next day; MT048 drift 58/60) | Anti-overclaim rule 10; MT048 sweep | Any cached "clean" claim without a date is unreliable | Date-stamped claims + re-scan before reliance | Standing rule; TC-MICRO-02 re-scan first |
| F-06 | Early plan sections retain pre-supersession text (e.g., wired-diagram standard, bake-off) with in-place supersession notes of varying visibility | e.g., lines ~130–800 vs MT024+ | A reader sampling early sections can extract dead rules | This document §5 + the operational reference | Mitigated by companion doc |
| F-07 | Incident ordinals are non-monotonic; "MT052 — EXECUTION RESULTS" appears twice (two waves) | PC-152/PC-209/PC-211 | Confusion risk only | Coverage ledger maps it | Note only |
| F-08 | `scripts/pipeline/config/registry.yaml` describes checks.py as "21 deterministic checks" (real ≈98/101); skill-doc counts were wrong at multiple past moments ("47", "83") | Code-inventory agent; MT033/TC-HARDEN-16 history | Doc-trust erosion | Live `grep -c '^def check_'` | Doc fix pending |
| F-09 | Plan's early claim "reports/ pre-commit hard-block" went stale (downgraded to warn-only 2026-08-08) — corrected in place | TC-HARDEN-05 source note | Historical | — | Closed |
| F-10 | MT053's own investigation initially mis-diagnosed pdf/java+3d/net as an "external blocker" (uncommitted content) — actually stale git index; corrected next day | §13 item 6 correction | Historical; also a live ST-021 exemplar | — | Closed |
| F-11 | Attached-snapshot vs live-plan divergence (3 growth events in ~30 min) | §1 table | Any consumer of the "snapshot" must re-pin | Live file + hash | Documented here |
| F-12 | pdf/cpp disposition files hand-rewritten (no backup) just before the "let the system handle it" instruction | MT053 disclosure | Harmless post-MT053 (files never read again for published products) but original state unrecoverable | MT053 record | Accepted, disclosed |

---

## 13. Root causes of plan/system drift

1. **Execution outran the skill.** The 30-product corpus, verification sprint, and first pushes all
   predate a usable CLI; the registered skill sat unused beside a parallel manual process for ~8 days
   (MT033's core finding). Everything since has been paying that boundary back.
2. **"Correct once, never made durable."** Named explicitly ≥6 times in the plan (images, collapse
   convention, composition rules, Key-Capabilities structure, badge floor, C++ install correction):
   a fix applied by hand or one agent's judgment, without a skill-doc rule + mechanical gate, was
   reproduced as a defect by the next independent regeneration.
3. **Reconciliation ≠ composition floor.** Four independent instances (enterprise link, banner
   link, installation claims, badges) of building "did we lose X from the old README" without "what
   must a fresh candidate contain" — each retrofitted after a live miss.
4. **Position-based identifiers.** `u%04d` unit IDs with no content hash made every disposition
   file silently fragile to any upstream README structure change (MT038, MT048, MT053) until the
   excerpt-fingerprint gate landed.
5. **Trusted-but-unreliable structured inputs.** `formats.md`, `package_registry.json`,
   `keywords/`, reference-site `_index.md` all independently proven wrong in places → the recurring
   "2-of-3 corroboration / downgrade-to-heuristic" pattern.
6. **Fixed phrase lists are reactive by construction** — every narration category needed a live
   incident to teach it new vocabulary; structural-shape patterns and cross-file fingerprints were
   the durable answers.
7. **Two candidate trees without a canonicity rule** (from the 2026-08-13 "regen-full for this
   pass" directive until the 2026-08-18 decision) — divergence, double-fixing, and a push path
   reading the wrong tree.
8. **Concurrent sessions on one working tree/index** (ST-021): stale index snapshots, test-baseline
   nondeterminism, snapshot contamination, a git-stash near-miss — mitigated by plumbing-only
   commits, Read-based snapshots, and (this audit) snapshot-timestamped claims.
9. **Register/bookkeeping as prose** — status fields, counts, and cards can silently rot (F-03,
    F-04, F-08); the plan's own hardening passes and MT056's mechanical tripwires are the response.

## 14. Known regressions (content-level, currently live)

- **3d/net, 3d/python on GitHub**: old wired-model diagrams with real, visible label clipping
  (verified against GitHub's own renderer 2026-08-14) — awaiting TC-HARDEN-47/48 republication.
- **~5 published-then-locally-edited repos** (cells/go, cells/java, cells/net, 3d/java,
  3d/typescript): live content lags verified local candidates (e.g., missing `## Dependencies`);
  unpushed by policy pending decisions.
- **cells/python live repo**: Enterprise href still `python-java` (correct target `python-net`);
  local candidate fixed, push awaiting authorization.
- Disposition-file drift portfolio-wide (data, not reader-visible content) per MT048/MT055 sweeps.

## 15. Classification counts (over the 32 material REC rows + capability set)

CURRENT_AND_COMPLETE: 14 capability groups / REC rows · CURRENT_BUT_PARTIAL: 5 ·
CONTRADICTED_BY_IMPLEMENTATION: 1 open (F-02; F-01 fixed in-tree mid-audit) · ACCEPTED_PENDING: 7 · INTENTIONALLY_DEFERRED: 7 ·
BLOCKED: 6 · SUPERSEDED: 11 distinct decision chains · REJECTED: 6 designs ·
NO_LONGER_NEEDED: 1 (27-product edge survey) · LEGACY_CONTEXT_ONLY: 4 ·
UNVERIFIED: 2 (MT056 gate wiring at audit end; post-21:03 plan growth).

## 16. Current risks

1. Portfolio disposition drift (TC-MICRO-02) — every `ingest-candidate` on an unremediated product
   will fail hard gates until fixed or re-scanned.
2. F-02 push-path contradiction (hardcoded co-author) — wrong attribution on the next CLI live
   push executed by a different model; F-01 (`--draft`) fixed in-tree 21:19, uncommitted.
3. Deliverable durability (TC-HARDEN-17) — single-machine, gitignored.
4. Concurrency (ST-021) — live index staleness recurs; only plumbing commits are safe; scoped-test
   baselines have been observed nondeterministic under load (MT050).
5. Six languages of examples never verified by the skill itself.
6. Upstream data sources (`formats.md`, `keywords/`, registry, reference `_index.md`) remain
   imperfect; every consumer must keep its corroboration/heuristic posture.
7. The plan file is a live contested artifact — any consumer must re-pin hash/line-count before
   relying on it (this audit's own §1 demonstrates why).
8. `SKIP_SKILL_CONTEXT_CHECK` may reappear in a session environment; hooks are not a safety net.

## 17. Recommended next actions (priority order)

1. Fix F-02 (parameterize the hardcoded co-author trailer in `_do_push`, run.py:3504) + a
   regression test — the last hard plan-vs-code contradiction (F-01's `--draft` was fixed
   in-tree at 21:19 during this audit; confirm its regression test when MT056's record lands).
2. Let MT056 finish landing (TC-M56-01..08), then execute the mechanical tree promotions and freeze
   `repo-presenter` per the recorded decision.
3. TC-MICRO-02: re-scan (numbers are stale by design), triage by RC taxonomy, fix in family waves.
4. TC-HARDEN-47/48: republish 3d/net + 3d/python (needs explicit push authorization).
5. Decide TC-HARDEN-17 (durability) — user policy call; everything else compounds on it.
6. Then: remaining language runners (largest single engineering item), portfolio internal-class
   scan, sweep-finding triage, doc-count fixes (F-08).

## 18. Links

- Concise agent reference: [current-operational-reference.md](current-operational-reference.md)
- Original full plan (immutable/append-only historical source):
  `C:\Users\prora\.claude\plans\d-users-prora-onedrive-documents-github-humble-tome.md`
  (audited at sha256 `8f5fb4fe6e7c76bc521c85b38b6c7c044e5bf80307a5b46ffb0e9ba159cd09ea`, 20,903 lines)
- Skill contract: [skills/readme-refresh.md](../../skills/readme-refresh.md)
- State machine: [scripts/pipeline/commands/foss/readme_refresh_run.py](../../scripts/pipeline/commands/foss/readme_refresh_run.py)
- Checks: [scripts/pipeline/commands/foss/readme_refresh_checks.py](../../scripts/pipeline/commands/foss/readme_refresh_checks.py)

## 19. Maintenance contract

| Field | Value |
|---|---|
| Original plan path | `C:\Users\prora\.claude\plans\d-users-prora-onedrive-documents-github-humble-tome.md` |
| Plan identity audited | 20,903 lines · 1,718,828 bytes · sha256 `8f5fb4fe6e7c76bc521c85b38b6c7c044e5bf80307a5b46ffb0e9ba159cd09ea` (2026-08-18 21:03 local) |
| Attached-snapshot identity (mission input) | 20,581 lines · 1,694,099 bytes · sha256 `6ec5247d…29ca` |
| Repository revision | HEAD `80de6805f3` + dirty working tree (MT041–MT056 uncommitted); live implementation = working tree |
| Skill version | `skills/readme-refresh.md` frontmatter `verified: 2026-08-18`, S-120 |
| Reconciliation date | 2026-08-18 |
| Authoritative state reference | `reports/readme_refresh_runs/` + per-product `ACTIVE.json`; open work = the plan's own TC-MICRO/TC-M56/TC-HARDEN open cards |
| Document roles | Plan = append-only history · this file = reconciliation snapshot · operational reference = current orientation · state machine = execution status · taskcards = actionable work · code = implementation authority |
| Refresh triggers | Plan hash changes materially; any TC-M56 execution record lands; TC-MICRO-02 waves close; any new mission (MT057+); F-01/F-02 fixed; tree retirement executed |
| Ownership | Whoever executes the next readme-refresh mission updates the operational reference in the same pass; this forensic snapshot is superseded-by-reference (write a new dated snapshot rather than editing history here) |

A lightweight staleness self-check (no framework, copy-paste): see the operational reference's
"Consistency check" section — it verifies plan hash, entry-point existence, default-tree constant,
and open-item IDs against this pair of documents.

---

## Appendix A — Complete plan coverage ledger

The ledger below is the verbatim working record produced during the sequential read (chunk
boundaries = read batches; PC-IDs stable). Line ranges cover 1–20,903 with no unexplained gaps.

# Plan Coverage Index — live plan 20,634 lines, sha256 953fbfd159a2..13c4, read sequentially
# Snapshot delta: attached snapshot was 20,581 L / 1,694,099 B / 6ec5247d...; live = 20,634 L / 1,697,943 B / 953bfd... -> live primary.
# Format: PC-nn | lines | subject | type | classification notes

## Chunk 1: lines 1-800
PC-001 | 1-33 | Context: /readme-refresh mission; human-gated PRs to FOSS repos; scope beyond README (description/topics/homepage/community files/social preview); foss-java-publish (S-110) REJECTED as model; refresh_run.py (S-84) chosen as architectural model; template bake-off later superseded | Requirement + Design decision | CURRENT (architecture) / template bake-off SUPERSEDED
PC-002 | 34-78 | MT015 dependency: data/package_registry.json sole package-identity source (31 entries); read-only consumer; canonical-fallback-text rule for unconfirmed installs; MT015 governance gap documented not owned | Design decision / dependency | CURRENT
PC-003 | 79-129 | Existing assets inventory: data/products.json (31), registry_exclusions.json (cells/typescript excluded), clone cache RO, knowledge/merged, refresh chain S-34..., homepage target, refresh_run.py state machine detail, CLI conventions, repo-metadata greenfield, DAR format | Investigation | LEGACY_CONTEXT (baseline research)
PC-004 | 130-174 | Template FINALIZED: golden sample (note/python from foss-readme-optimizer POC) + exactly one new section '## Documentation & resources' after API reference; supersedes Templates A/B/C | Design decision | CURRENT; A/B/C SUPERSEDED
PC-005 | 176-182 | Additional-examples flagship rule (2026-08-03): one flagship shown open + rest in <details> | Design decision | CURRENT
PC-006 | 184-236 | Mermaid At-a-glance standard: traceability, no-orphans (check_diagram_connectivity blocking at ingest-candidate), caveat-or-omit, archetype-default subgraph titles (Outputs short-form revert 2026-08-05/06), node granularity, optionality labeling, 1-node smell (its original example SUPERSEDED by 2c), no classDef styling | Design decision | CURRENT (with internal supersessions noted)
PC-007 | 237-298 | 2026-08-06 archetype incident (barcode/python): single-archetype assumption was defect; 4 archetypes (transform ~26, generative 1, compile 1, hybrid 2); confirmed defect lists incl. selector-as-Input x7, internal-representation-as-Output; cells/java false-positive; font/python reclassified transform; pdf/cpp+pdf/go missing FromScratch | Incident + Root-cause | LEGACY_CONTEXT + rules CURRENT
PC-008 | 299-382 | Fix: hybrid test (3-part falsifiable); 4th FromScratch subgraph; archetype-keyed title vocabulary table; Inputs test exclusions 2a-2d + Rule 4 compile refinement; Outputs test with (a)(b)(c) exclusions + extraction exception | Design decision | CURRENT
PC-009 | 384-413 | data/diagram_archetypes.json durable store (exceptions-only, 4 rows, absence=transform, RO consumer, human-triggered reclassification) | Implementation directive | CURRENT (implemented — verify)
PC-010 | 415-443 | check_diagram_connectivity classify-by-subgraph-ID change + check_diagram_known_subgraph_ids non-blocking tripwire; backward-compat verified across 30 files | Implementation directive | CURRENT (verify in code)
PC-011 | 445-477 | Retroactive diagram fix scope: 9 products enumerated (barcode/python pilot, slides x4, words/net, font/python, tex/python, pdf/cpp, pdf/go; cells/java no-fix) | Execution plan | CLOSED per L479
PC-012 | 479-500 | Execution CLOSED 2026-08-06: commits b14e980070 (checker change), 178ae8f1e3 (archetypes file); 9 fixes; 30-file portfolio 100% PASS both gates | Execution result / Status claim | Verify commits exist
PC-013 | 501-552 | Mechanism-duplicate-output rule (2026-08-05; cells/cpp user review; cells/rust worse instance; both fixed same day; check_diagram_no_mechanism_duplicate_output spec'd; near-misses dismissed) | Incident + rule | Rule CURRENT; retroactive CLOSED
PC-014 | 554-800 | Capability-dependency-edges incident (2026-08-06/07, barcode/python post-archetype): star topology cannot express pipelines; root causes A-E; Rule 1 direct-edge test (1a shared-substrate, 1b pipeline, 1c bundled-split, Step-0/2e precondition); Rule 2 config-shape granularity; data/diagram_capability_dependencies.json (absence=never-traced, NOT clean); 3 new checks (matches_capability_dependencies BLOCKING; suspicious_direct_product_edge heuristic 1-of-5 recall stated; capability_unreachable_from_product heuristic); barcode redrawn (continues past 800) | Incident + Design + Implementation directive | Rules CURRENT; verify checks in code

## Chunk 2: lines 800-1600
PC-015 | 800-909 | barcode/python redrawn diagram (full mermaid); resolves 5 symptoms; migration honesty: barcode/tex/email fixed now, ~24 products UNCHECKED for capability-dependency defect class — deferred survey (explicitly a later pass); OCR/OMR forward-look (expectation not guarantee); validation controls: unit tests for new checks against 6-product ground-truth fixture set + commitment to write pytest suite for WHOLE checks module (was ad-hoc-validated debt); tradeoffs/risks (citation rot, 1-of-5 recall) | Design + Deferred work | DEFERRED: ~24-product dependency survey; VERIFY: checks-module pytest suite now exists
PC-016 | 911-954 | License fixed-template rule (2026-08-04): single MIT wording; license-file detection real check w/ case-sensitivity; file-absent variant; retroactive fixes 3d/typescript + words/python fabricated path; check_license_link_target spec'd for checks module | Design + Incident + Implementation directive | CURRENT; verify check exists
PC-017 | 956-1073 | Process-narration prohibition (2026-08-04): defect classes (hedging, verification narration, self-referential circular refs, "(per ...)" citations, meta-commentary 14/30, upstream-issues duplication, factual contradiction 3d/python COLLADA, undisclosed BLOCKING commands html/python+words/net w/ real resolutions incl. package_registry.json words/net published:false STALE); 6-agent + grep-sweep two-pass process model; retroactive CLOSED 2026-08-04 (~35 edits, gates 100% PASS); check_process_narration_smells heuristic + check_no_undisclosed_blocking_commands deterministic spec'd | Incident + rules | CURRENT rules; note: package_registry words/net stale entry NOT fixed (read-only consumer)
PC-018 | 1075-1158 | Named-member accuracy rule (2026-08-05, 3rd 3d/python incident): presence-checking != accuracy-checking; combined Load/Save bullet trap; check_named_member_accuracy spec'd (two-tier); retroactive CLOSED 2026-08-05: 21/30 products defective, 75 defects fixed, 9 clean | Incident + rule + Execution result | CURRENT; verify check implemented
PC-019 | 1160-1252 | API-reference intro must name hub classes (2026-08-05, 3d/net PR review): 9 weak files enumerated; check_api_reference_intro_names_classes spec'd (heuristic); pilot 3d/net + rollout 8 files CLOSED same day, idempotency proven; OPERATIONAL FINDING: concurrent-write hazard on gitignored reports/repo-presenter/ tree (5 agents saw email/net content in snapshots) — flagged, NOT investigated (ST-021-like) | Incident + rule + Execution result | CURRENT; hazard flagged open
PC-020 | 1254-1351 | Preserve-by-default rule (2026-08-04, 3d family PR prep): every old-README fact/link accounted for (carried-forward-verified OR dropped_claims.json with verified reason); verify-before-including both directions; dropped_claims.json must become real structured diff gate at plan/ingest-candidate; check_dropped_content heuristic spec'd; retroactive CLOSED 2026-08-04: 21/30 had drops (defect shapes catalogued: legal-notice pdf/go fonts, SECURITY.md x3, AGENTS.md x4, guides, examples, version floors, visual proofs); 9 clean | Incident + rule + Execution result | CURRENT
PC-021 | 1353-1429 | Immediate-execution batch generation directive (~2026-08-02): skip CLI/state-machine for NOW, generate 30 READMEs locally at reports/repo-presenter/{f}/{p}/readme.md; install-sourcing hierarchy (package_registry.json → per-registry live checks; C++ NuGet correction 2026-08-04); Documentation&resources links only if _index.md exists; Enterprise link via data/aspose_com_targets.json + backlink_targets.py + platform_canonical_overrides.yaml (slug divergence real) | Implementation directive / Execution | EXECUTED (30 files); note output path 'repo-presenter/' at first, later reports/repo-presenter/
PC-022 | 1430-1581 | Verification pass (compile+run all examples): Vector3.add incident origin; scope 241 code blocks measured; publish-state per language; block taxonomy (standalone/fragment/dep-coordinate/build-CLI); fixture policy (never fabricate binary formats; BLOCKED-WITH-REASON closed set + swap-in-alternative refinement); per-language procedure table; toolchain installs Rust+MinGW to F:; three-way status; push-ready gate (all clean or user-accepted-by-name); code-smoke S-63 pre-filter (zero Go coverage); parallelization lanes; execution order; surgical push boundary (only readme.md pushed) | Requirement + procedure | CURRENT (as skill contract, per PC-023)
PC-023 | 1583-1600+ | Skill contract update 2026-08-03: (1) compile/run verification mandatory every run; (2) upstream-issues.md alongside readme.md; (3) flagship example before fold | Design decision | CURRENT

## Chunk 3: lines 1600-2400
PC-024 | 1602-1638 | State-machine change: VERIFYING_EXAMPLES mandatory state between PLANNED and AWAITING_REVIEW; new CLI subcommand verify-examples (distinct from post-push verify); toolchain provisioning explicit (Maven/JDK17, dotnet, go, per-run venvs, Rust F:\toolchains\rust GNU, MinGW F:\toolchains\mingw64); scratch-isolation rule after real incident (agent cleanup deleted shared scratch root incl. toolchains) | Design decision + Incident | CURRENT — verify state exists in code
PC-025 | 1640-1674 | upstream-issues.md schema: per-product always-present (even when clean); scope rule = ONLY genuine upstream defects, never own-generation bugs; severity taxonomy BLOCKING/FUNCTIONAL-DEFECT/VERSION-DRIFT/INFORMATIONAL | Design decision | CURRENT
PC-026 | 1676-1712 | Flagship-example template change detail + retroactive execution of contract reqs 2&3 across 30 files (transcription of sprint findings; 14/30 products have real upstream issues); code-smoke integrity re-run | Execution result | CLOSED
PC-027 | 1714-1791 | At-a-glance reconciliation audit 2026-08-03: 7 defect classes (fabricated capabilities pdf/java, stale-after-correction, contradicts-own-Scope, orphaned nodes x5 products, completeness gaps x11, misrouted edges x3, style drift); ORIGINAL design-standard + checker subsections here SUPERSEDED — authoritative version moved to Template section; check_diagram_connectivity first built+committed cf6a7798 2026-08-03; retroactive 30-diagram reconciliation executed | Investigation + Supersession notice | SUPERSEDED in place (points to Template section)
PC-028 | 1792-1852 | C++ NuGet correction retroactive execution (2026-08-04): 4 cpp READMEs fixed; cells/cpp real .nupkg inspected (MSVC-only, CMake config; bundled-sample defect → upstream-issues INFORMATIONAL; TOOLCHAIN-UNAVAILABLE honest); email/pdf/slides reworded 'no NuGet yet'; Enterprise links re-verified; pdf/cpp missing from aspose_com_targets.json cache (left as-is, out of scope); pdf/cpp double-Enterprise-link fixed | Execution result | CLOSED; note open cache gap aspose_com_targets pdf/cpp
PC-029 | 1854-1898 | TWO separate skills decision (2026-08-04 revision): /readme-refresh (files) vs /repo-presenter-metadata (settings; API-applied, no PR); scope = presentation fields only, security settings EXPLICITLY DEFERRED by instruction; access verification: GH_TOKEN admin all 12 orgs; pre-flight permissions check required in INPUTS_PINNED; single-PAT SPOF documented unresolved | Design decision + Deferred | CURRENT design; /repo-presenter-metadata NOT BUILT (per memory)
PC-030 | 1899-1989 | Storage design: data/repo_metadata_state.json (org+platform nested; default_branch never assumed; community-file proposal narrow: security_md+contributing only) + data/repo_presenter_actions.jsonl (append-only external-action ledger, shared both skills); homepage constructed directly (no lookup file); description length 100-160 check_description_length in separate repo_metadata_checks.py; DAR rows needed (docs/governance/ is FORBIDDEN path → override token) | Implementation directive | VERIFY: do these data files exist? repo_metadata_checks.py likely NOT_IMPLEMENTED
PC-031 | 1990-2032 | PR mechanics: pre-flight; branch readme-refresh/{date}; NO --draft (revised 2026-08-10 MT032 17th incident, draft retired); duplicate check; only README.md + community files ride PR; actions ledger row; Co-authorship mandatory real acting model name (corrected 2026-08-04; sub-agent clarification 2026-08-10 MT032) | Design decision (revised) | CURRENT
PC-032 | 2034-2159 | Manual PR-push SOP field-tested 3d/java 2026-08-04 (pre-CLI procedure, 10 steps): products.json identity; real pre-flight (3d family default_branch diverges main/master); duplicate check; dropped-link audit; disposable clone; commit-tree plumbing workaround for check_commit_bash_hook (SKIP_ var unreachable by agent); push+PR no-draft; PR body 3 sections (Summary/What changed/Verification), NO upstream-defects section ever, upstream-issues.md never pushed (confirmed 2026-08-10 MT032); gh pr edit needs read:org → use gh api PATCH -F body=@file; force-push correction protocol; EXECUTION RECORD: 3d family 4 PRs opened 2026-08-04 (table w/ URLs + upstream defect counts); stopped for review per instruction | Execution result + procedure | HISTORICAL (SOP = source for eventual push subcommand); status of PRs to verify
PC-033 | 2161-2270 | /repo-presenter-metadata design: lighter state machine CREATED→INPUTS_PINNED→PROPOSED→AWAITING_REVIEW→APPROVED→APPLYING→APPLIED; icon/avatar org-level only, NO API exists (verified 3 ways) → handoff doc only; social-preview URL ephemeral (JWT 300s, verified) → never embed in README (decision reaffirmed w/ evidence); source art SVGs incomplete (no go/python/rust/ts variants); submenu.html hardcodes -for-net.svg (site bug, backlog-worthy); color from own SVGs not products.aspose.com (unverifiable); mandatory human visual review; pilot-first | Design decision | NOT_IMPLEMENTED (skill unbuilt)
PC-034 | 2272-2400 | Design section: skill doc thin refresh-product-style; readme_refresh_run.py mirrors refresh_run.py; full state machine (BLOCKED re-enterable, ABANDONED/PUSHED terminal); INPUTS_PINNED does staleness+access checks; factpack (facts/factpack.json): formats, features, verified snippet, limitations, license-file detection, homepage URL, community-file audit, install from package_registry.json w/ fallback, archetype field, old_readme_inventory (links+headings+format-matrix+version-pinned deps); check-versioning lesson (re-run on refinement — done 2026-08-04, 10/30 findings); banned domains forum.aspose.com + *.aspose.app → check_no_excluded_domain_links hard gate; agent composes prose from factpack (division of labor); dropped_claims.json dispositions | Design (core) | CURRENT — verify against code

## Chunk 4: lines 2400-3100
PC-035 | 2400-2454 | Design continued: ingest-candidate deterministic checks incl. check_diagram_connectivity + check_dropped_content as gates; dropped_claims.json a REAL GATE not passive log; VERIFYING_EXAMPLES verify-examples semantics (fixes into candidate; upstream defects into upstream-issues.md; carried-forward prose claims also verified); AWAITING_REVIEW hard stop (never self-approve); approve re-verifies input drift; PUSHING disposable clone, surgical diff, no-draft PR, idempotent resume; verify = post-push confirmation | Design (state machine detail) | CURRENT — verify code
PC-036 | 2455-2487 | CLI spec: 11 subcommands (start/plan/ingest-candidate/verify-examples/recheck/status/approve/push/verify/abandon/recover); 2 exit codes; ACTIVE.json+FileLock at reports/readme_refresh_runs/{f}/{p}/; evidence layout per-run (manifest, facts/factpack.json, candidate/*, community_files/, checks/, verification/, events.jsonl, push/receipt.json); no metadata/ subdir | Design | CURRENT — verify against actual CLI
PC-037 | 2488-2518 | repo_metadata_run.py CLI + evidence layout (family-scoped lock) | Design | NOT_IMPLEMENTED expected
PC-038 | 2519-2647 | Checks module full spec (~15 fns): compute_link_caps, count_aspose_links, check_enterprise_edition_naming, check_required_sections, surgical_diff_check, check_license_link_target, check_process_narration_smells (heuristic), check_no_undisclosed_blocking_commands (HARD), check_dropped_content (HARD), check_no_excluded_domain_links (HARD), check_named_member_accuracy (two-tier), check_api_reference_intro_names_classes (heuristic), check_diagram_no_mechanism_duplicate_output (heuristic), check_diagram_matches_capability_dependencies (HARD when entry exists), check_diagram_suspicious_direct_product_edge (heuristic), check_diagram_capability_unreachable_from_product (heuristic), check_diagram_connectivity (built 2026-08-03 cf6a7798; directed BFS; two real bugs found+fixed; pytest suite NOT YET WRITTEN at that time), check_diagram_known_subgraph_ids | Implementation directive | VERIFY each against current code (agent inventorying)
PC-039 | 2648-2659 | repo_metadata_checks.py separate module spec (check_description_length, check_community_files_scope; no shared code) | Design | NOT_IMPLEMENTED expected
PC-040 | 2661-2683 | Governance/registration checklist: 4-tree mirrors both skills; skills.md rows; DAR rows x4 min; parity checks; data file writes via /commit; append-only CI protection for actions ledger | Implementation directive | PARTIAL (readme-refresh registered; repo-presenter-metadata not)
PC-041 | 2684-2730 | Implementation Sequence Steps 0-6: 0 template done; 1 backing script+checks+tests; 2 registration; 3 dry run; 4 first live push; 5 metadata script; 6 metadata pilot | Plan | Steps 1-4 later executed (see MT021+); Steps 5-6 NOT STARTED
PC-042 | 2731-3029 | Verification checklist (long): unit tests per check; round-trip; registration exit-0; gates fire (fixture w/ deliberate defects); locking; verify-examples gating; upstream-issues always-present; flagship check; retroactive confirmations; archetype execution verification; capability-dependency verification incl. do-NOT-claim-24-survey-done; license; narration; content-preservation (26-of-30 sweep + 10-of-30 category/matrix re-check details; pdf/net 17 dropped classes; slides/java 3D category); THIRD dropped-content incident 3d/python property-level (accuracy vs presence distinction); named-member audit full record (21/30, 75 defects; defect-shape catalog; out-of-scope findings pdf/cpp PdfBookmarkEditor stub + cells/rust 'reorder'); PR-push status: 3d/java + 3d/typescript PRs MERGED by user, their later fixes NOT pushed (open decision); metadata design confirmations; API-ref intro pilot 3d/net (md5, 1 hunk) | Test/validation requirements + Execution results | Mixed CLOSED/OPEN; key OPEN: 3d/java+3d/ts unpushed fixes
PC-043 | 3030-3100 | Readiness audit 2026-08-06: VERDICT NOT READY; findings: only 2 of ~13 checks real (rest prose-only); NO /readme-refresh skill file existed; reports/repo-presenter/ outside git (pre-commit Step 0 blocks reports/) → filesystem-based evidence required; diagram_capability_dependencies.json absent; archetypes 4/30 and tex/python diagram never restructured; barcode contradiction still on disk; tex/python 12-edge mesh worse than plan said (C2 orphan question needs font_manager source read); email/python C6a/C6b Output wiring unverified; NO section-scoped-diff mechanism exists anywhere | Investigation (audit) | HISTORICAL snapshot — later resolved by hardening; verify current state

## Chunk 5: lines 3100-3800
PC-044 | 3100-3124 | Readiness audit cont'd: MISSION_AUTHORITY root slot occupied (concurrent-toasting-biscuit); no taskcard CLI (TaskcardStore lib only); no external authority needed for MT021 work | Investigation | HISTORICAL
PC-045 | 3125-3251 | MT021 hardened design (2026-08-06): scope = 3 evidenced products only; remaining 27 explicitly OPEN (Phase 2 named); mission MT021-2026-08-06-DIAGRAM-CAPABILITY-DEPENDENCY; taskcards TC-MT021-P0-CHECKS (+NEW check_only_mermaid_block_changed + CLI arg), P0-FIXTURES (pytest suite), P0-COMMIT, P1-BARCODE/TEX/EMAIL lanes (Read-tool snapshots vs contamination), P1-STORE, P1-EVIDENCE; filesystem rollback; out-of-scope list | Execution plan | EXECUTED later (see subsequent incidents)
PC-046 | 3246-3251 | Final single-go prompt kept OUT of plan file (anti-drift) | Note | LEGACY
PC-047 | 3252-3341 | Tenth incident / MT024 (2026-08-08): 7 visitor-facing quality rules; machinery findings: (1) SKIP_SKILL_CONTEXT_CHECK=1 LIVE in session env (unconditional bypass; origin unknown; standing risk — needs USER action); (2) DAR-prerequisite gate gap scoped to 6 skills incl. S-120's 2 bare-data-file rows; (3) verify_examples confirmed STUB (BLOCKED-WITH-REASON TOOLCHAIN-UNAVAILABLE for every block; no real compile anywhere) — named execution-readiness blocker; precedent audit table for 7 rules; live sample audit found casing + Enterprise-anchor drift violations | Incident + Investigation | Items 1&3 = standing OPEN risks; verify current env + code
PC-048 | 3343-3422 | Rule 2 resolution: DIAGRAM SIMPLIFICATION Option A (Product → Core Capabilities (columnar) → Outputs; per-node edges retired from visual; stores kept for column order); Starting-Points Option 3 approved (2-line container, hybrid only); 3 follow-up requirements → check_diagram_format_support_claims, hybrid fresh re-verification standing rule, generative zero Starting Points; archetype-to-container table | Design decision (SUPERSEDES per-node-edge visual model) | CURRENT
PC-049 | 3424-3448 | Cross-product citation defect (Aspose.Cells in pdf/email/slides cpp Installation) → check_no_cross_product_citation | Incident + rule | CURRENT
PC-050 | 3449-3469 | Examples-table collapse rule (table inside <details>) → check_examples_table_collapsed | Design decision | CURRENT
PC-051 | 3471-3492 | Check-function inventory table MT024: new (format_name_casing, diagram_format_support_claims, diagram_column_balance, diagram_hybrid_reverification, no_cross_product_citation, examples_table_collapsed, heading_title_case, section_job_distinctness); REWRITTEN (diagram_connectivity→check_diagram_shape, matches_capability_dependencies→column order); RETIRED (suspicious_direct_product_edge, capability_unreachable); process_narration ELEVATED to hard gate; enterprise naming extended | Implementation directive | CURRENT — verify code
PC-052 | 3493-3533 | MT024 taskcard plan Phase 0/1/2 | Plan | EXECUTED below
PC-053 | 3534-3566 | Execution readiness certification: READY WITH CONDITIONS; conditions: (1) verify_examples no-op (standing disclosed risk), (2) SKIP_SKILL_CONTEXT_CHECK live (standing), (3) pytest coverage Phase-0 gate | Status claim | conditions 1-2 still OPEN? verify
PC-054 | 3568-3654 | MT024 Phase 0 CLOSED 2026-08-08: 12 fns implemented (module now 21 fns), 95 pytest cases; parse_diagram nesting-aware; connectivity retired → check_diagram_shape + column_balance; 7 real bugs found via testing (chain-edge parsing, fenced-code regex desync PORTFOLIO-WIDE blind spot in check_no_undisclosed_blocking_commands, cmake fences, casing link-target FP, REQUIRED_SECTIONS title-case coherence, internal-label skip when no old README, fixture silent-no-op) | Execution result | CLOSED; bugs historical
PC-055 | 3656-3708 | MT024 Phase 1 CLOSED 2026-08-08 (commit 8c1d741ed6): 30 diagrams redrawn simplified + title-case; surgical fixes (citations, casing, examples collapse); hybrid re-verified; 7 MORE checks-module bugs found at scale (cross-product allowlist, acronym stoplist, badge-link regex x2, IGNORECASE regression x3 checks inert, glTF heading exception); archetypes+dependencies files updated (8 products re-keyed; email pairs merged pipeline_edges=[]) | Execution result | CLOSED
PC-056 | 3710-3747 | Enterprise normalization CLOSED 2026-08-08: 2 more checker bugs (window placement, word order); 19→11→10 real fixes; 109 tests passing | Execution result | CLOSED
PC-057 | 3749-3800 | Eleventh incident (2026-08-08, MT025): simplified diagram LOST real Inputs (9/9 non-hybrid samples) and let non-format content into Outputs (6/10); check suite mechanically blind + hybrid_reverification actively FORBIDS Inputs container on non-hybrid; format_support_claims only checks recognized tokens | Incident + root cause | Leads to MT025 redesign (next chunk)

## Chunk 6: lines 3800-4500
PC-058 | 3800-3916 | Eleventh incident cont'd: formats.md unreliability disclosed (tex/python export flags wrong; 3d/net 10-vs-0 gap); symptoms; root causes (rule-authoring defect not execution; Outputs test unrevised for simplified model; no canonical source bound composing agents); structural weaknesses (rules as prose; shape-vs-semantics; no aggregate rollup in parallel batches; formats.md unverified); consistency analysis (systematic bias + variance); preserved list; redesign list | Root-cause analysis | LEGACY_CONTEXT + rules feed MT025
PC-059 | 3917-3999 | MT025 fix design: revised archetype→StartingPoints table (transform/compile REQUIRED, generative FORBIDDEN, hybrid exactly-2); format-purity tokenizer rule (core/qualifier split; connector allowlist disclosed-incomplete); new checks: check_diagram_starting_points_presence (hard), check_diagram_container_format_purity (hard x2), check_diagram_format_completeness_hint (heuristic — formats.md unreliable); hybrid_reverification narrowed; wiring; PROCESS FIX design item E: mandatory cross-product consistency rollup after any multi-agent batch | Design decision | CURRENT
PC-060 | 4000-4092 | MT025 validation plan + taskcards + tradeoffs (second full-portfolio redraw cost; allowlist first-iteration; formats.md inherited risk; denser diagrams for format-rich products; purity≠accuracy≠completeness) | Plan | EXECUTED
PC-061 | 4093-4170 | MT025 Phase 0 CLOSED 2026-08-08: 3 new + 1 narrowed fn; 22 new tests; 126/126; sanity pass on 30 real files (27 presence-fail as predicted; purity node-for-node); REAL GAP: data/format_descriptions.json missing many portfolio formats → _DIAGRAM_SUPPLEMENTARY_FORMAT_NAMES supplement; plural-tolerant matching fix; 19 purity-fail products incl. new 3d-family instances; cells/java 'Cell values' node: disclosed TIGHTENING vs 2026-08-05 exception (user's newer rule wins); commit 9301bc03b0; full suite 8665 passed/1 unrelated fail | Execution result | CLOSED
PC-062 | 4171-4250 | MT025 Phase 1 pilot CLOSED 2026-08-08 (5 products: cells/cpp, 3d/net, pdf/cpp, barcode/python, html/python): SP containers added; non-format Outputs removed; 3d/net conservative (9 formats.md-only formats NOT added; PLY prose-over-formats.md); pre-existing formats.md gaps disclosed (pdf/cpp no PDF/PNG row; html/python no HTML row + BLOB/START junk); allowlist additions; pilot rollup table 5/5 clean; 126/126; AWAITING human review before Phase 2 | Execution result | CLOSED (pilot); Phase 2 pending at that point
PC-063 | 4252-4479 | Twelfth incident (2026-08-09, MT025 Phase 0c): formats.md cannot be sole authority — user directive verify-and-discard; findings: check_diagram_format_support_claims direction-blind (line 681 presence-only regex); formats.md traces to real AST extraction w/ functional-override mechanism (upstream owns fix); api_surface.json reliable corroboration source (verified 5 products); FIX: 2-of-3 multi-signal direction-aware check_diagram_verified_format_claims (formats.md directional flag + prose w/ negation override + api_surface suffix evidence); implementation spec; validation; tradeoffs (negation recall gap; suffix seeds 3-langs; 2-of-3 conservative) | Incident + Design decision | CURRENT
PC-064 | 4480-4500 | MT025 Phase 0c CLOSED 2026-08-09: implemented as designed; format_support_claims DELETED; _product_api_surface + _compute_candidate_format_evidence (factpack hint provisional); 26 new tests | Execution result | CLOSED (continues next chunk)

## Chunk 7: lines 4500-5200
PC-065 | 4500-4529 | MT025 Phase 0c cont'd: 142/142 tests; validated vs real content (tex/python stale-flag override confirmed live); real defect in own pilot edit found (3d/net glTF/GLB → glTF); out-of-scope disclosed (formats.md upstream; Go/Rust/Java/TS suffixes) | Execution result | CLOSED
PC-066 | 4530-4620 | MT025 Phase 2 CLOSED 2026-08-09: 25 products via 6 parallel agents; zero shared-file edits; consolidation found 6 MORE bugs (digit-leading token 3MF; formats-table cell tolerance; 3MF alias map _FORMAT_NAME_ALIASES; negation misattribution pdf/net + ALL-CAPS heuristic; re.search first-match-only PLY double-mention; semicolon window boundary); supplementary formats added (TTF/OTF/CFF/TYPE1/EOT/ONE); pdf/go hybrid re-verified (flow.go direct read), decided_at bumped (date-based freshness BY DESIGN); disclosed limitations NOT fixed: email EML unverifiable by source signal (methods not classes), page/python PS below 3-char floor — diagram claims REMOVED; final rollup 30/30 CLEAN; 149 tests | Execution result | CLOSED
PC-067 | 4621-4744 | MT026 banner rule (2026-08-09) CLOSED: banner-readme.png verified live 30/30 (curl 200 image/png); unlinked image after badge row; check_banner_present hard gate (family/platform match = anti-contamination); banner_url factpack field; applied to 30 files via deterministic script; 155 tests; risks: no live-reachability check by design | Design + Execution result | CLOSED; CURRENT rule
PC-068 | 4745-4908 | MT027 (2026-08-09): ground API Reference in reference.aspose.org graded content; verified 5 real _index.md files; two-tier structure (index tables + partial-class pages); TeXOptions r-triple-quote leak found in grade-A content (verify-even-graded-sources lesson); no existing pipeline reads this content; design: _load_reference_api_index, _load_reference_class_page, factpack reference_api_index; check_api_reference_classes_exist_in_reference_site (hard, replaces intro_names_classes role), check_named_member_accuracy gains reference-page-first tier, check_no_leaked_docstring_artifacts (heuristic) | Design decision | CURRENT
PC-069 | 4909-4981 | MT027 CLOSED 2026-08-09: single continuous pass (pilot 0 defects → justified skipping review checkpoint); 6 more design bugs fixed (intro prose scanning ambiguous → scope to bullet convention only; fully-qualified fallback; package-grouping PascalCase gate; TS/Rust/Go enum keywords; member-level 2-source corroboration — email/cpp reference-page getter asymmetry; ...); 1 genuine content defect (3d/python Transform/GlobalTransform split); 1 accepted heuristic gap (cells/go LoadWithPassword cross-file); final 30/30 CLEAN; 176 tests | Execution result | CLOSED
PC-070 | 4983-5199 | Thirteenth incident (2026-08-09, MT028): MT027 verified content but not PRESENTATION; user wants reference-site table structure adapted; root cause = request-interpretation gap; structural lesson: review full factpack field shape vs original request; AskUserQuestion → Option 3 (add exhaustive module-grouped table above divider, keep curated bullets unchanged); design: table exhaustive not curated, descriptions rewritable (filler pattern), trailer sentence removed; check_api_reference_table_completeness (hard), check_no_generic_class_description (heuristic); phased execution + validation | Incident + Design decision | CURRENT

## Chunk 8: lines 5200-5900
PC-071 | 5200-5237 | MT028 tradeoffs + Phase 0 CLOSED 2026-08-09 (commits 583ec6d547, e227258c82): 2 new checks wired; _index.md presence confirmed 30/30; zero-row-module (See Also) checker bug fixed | Execution result | CLOSED
PC-072 | 5238-5319 | MT028 Phase 1 pilot CLOSED (5 products, tables added, curated content unchanged): 3 more checker-relevant defects (generic-desc broadened to struct/API filler; check_no_truncated_class_description new heuristic 'e.g.' truncation; check_no_stripped_example_in_description new heuristic — html/python 81 rows restored from clone docstrings); pdf/cpp 123 generic-desc findings DISCLOSED DEFERRED; rollup table; 197 tests; unrelated concurrent-session test failures noted; awaiting review before Phase 2 | Execution result | CLOSED (pilot)
PC-073 | 5321-5641 | Fourteenth incident (2026-08-09, MT029): five directives + idempotency; findings: 7/30 products leak upstream forensic detail (Form A blockquote, Form B prose); root cause = phrase-blocklist structurally reactive, never cross-references paired upstream-issues.md; fix = check_no_upstream_issue_leaked_into_readme (2-token fingerprint, hard); Key Capabilities SEO rules + check_key_capabilities_quality + check_capability_scope_contradiction (3d/net Watermark fabricated-capability found+fixed); Scope&Limitations list format (pdf/net model) + check_scope_limitations_format (hard); Enterprise para elaborated template; Dev&Testing artifact linking _detect_dev_test_artifacts + check_dev_test_artifacts_linked (hard) + check_development_testing_collapse; IDEMPOTENCY: check_only_sections_changed (hard, general section-isolation) + honest statement that byte-identical LLM re-composition NOT promised, only structural properties | Incident + Design decision | CURRENT
PC-074 | 5642-5753 | MT029 Phase 0 CLOSED (commit 134914df73; 7 fns; 44 tests) + Phase 1 CLOSED (commit f8a99835f4; 11 products; 6 checker bugs fixed incl. INFORMATIONAL exclusion, generic exception names, section exclusions, bullet-by-bullet scan, artifacts casing/cache fixes, fragmentation first-word); 7 leaks fixed; 3d/net Watermark fixed; 243 tests; awaiting review | Execution result | CLOSED
PC-075 | 5755-5887 | MT028+MT029 Phase 2 full rollout CLOSED 2026-08-09 (commit 398d04a623): 24 products via 6 batches (bin-packed by class count); 3d/typescript excluded from MT028 disclosed; 3d/java _index.md stale for 11 classes (transcribed faithfully per mirror mandate, disclosed); 6 suspected checker bugs triaged (4 fixed w/ tests, 1 left unfixed disclosed TextObject truncation, 1 not reproducible); 248 tests; full suite 9050/3 pre-existing unrelated; final rollup 30/30 clean (29 + 1 disclosed exception); heuristic findings surfaced more filler (pdf/cpp 123→182 deferred) | Execution result | CLOSED
PC-076 | 5889-5900+ | Eighteenth incident (2026-08-11): 3d/typescript MT028 exclusion was a fixable parser gap, not impossibility (continues) | Incident | next chunk

## Chunk 9: lines 5900-6600
PC-077 | 5900-5983 | Eighteenth incident (2026-08-11) resolution: _parse_class_heading_module fallback parser (### ClassName convention, unique to 3d/typescript); case-insensitive module-name matching in table completeness (GLTF/glTF collision general fix); 3d/typescript table regenerated locally; 306 tests; git stash near-miss (ST-021 sixth occurrence — NEVER git stash); fix NOT pushed (PR #2 merged; needs fresh follow-up PR, user go-ahead required) | Incident + Execution result | CLOSED locally; UNPUSHED fix — open item
PC-078 | 5984-6325 | Fifteenth incident (2026-08-09, MT030 CONTENT-UNIT-VERIFIED-MERGE): old-README prose silently lost/genericized; findings: _old_readme_inventory only links+headings; dropped_claims.json NEVER BUILT (2 prose mentions only); no merge logic (agent-authored by design); 5-product survey 4/5 genericized/dropped (3 patterns: narrative/CTA, mechanism explanations, branding); user decision: preserve patterns 2+3, pattern 1 out of scope; fix: extract_old_readme_content_units + content-dispositions.json (agent-authored, absence-strict) + 4 hard gates + 2 heuristics (coverage, evidence_resolves, merged_into_target_section, no_exact_duplicate; classification_plausibility, probable_duplicate); placement rules table; honest limits (faithfulness not mechanically checkable) | Incident + Design decision | CURRENT — content-dispositions.json replaces never-built dropped_claims.json
PC-079 | 6326-6448 | MT030 Phase 0 CLOSED (commits 4001b015ff, d451ee0441; 43 tests; skill doc fn count 21→46) + Phase 1 CLOSED 2026-08-10 (5 products; unit counts table; 3 checker gaps fixed (emoji-heading normalize _normalize_for_drop_match; redundant_with_existing never verified; leading-20-char fallback → ≥50% word overlap); 9 surgical disposition corrections; DISCLOSED out-of-scope: check_dropped_content has no disposition-awareness (flagged for future pass); 291 tests; awaiting review | Execution result | CLOSED; disposition-awareness gap OPEN (later fixed? verify) 
PC-080 | 6450-6600 | Sixteenth incident (2026-08-10, MT031 HISTORY-AND-EMBEDDED-FACT): category-1 too coarse — words/net mixed units (u0021 hedge+real issue-request fact; u0024 real DOC-format history) excluded wholesale; 30-product survey: words/net unique (history+CTA 1/30, not-included section 2/30, CTA anywhere 1/30); root causes: single-verdict-per-unit schema, category boundary never pressure-tested vs mixed units, no template slot for history; extraction has NO section provenance (preserved, not redesigned); fix: NEW optional ### Project History H3 section in preamble (H3 level LOAD-BEARING — H2 would break __preamble__/Intro dispositions) | Incident + Design decision | CURRENT (continues)

## Chunk 10: lines 6600-7020
PC-081 | 6600-6783 | MT031 fix details: _CONTENT_UNIT_TARGET_SECTIONS + Project History; 4_verifiable_history classification + verified_by_corroboration status (honest weaker standard; Full2Foss zero corroboration → u0025 stays excluded); mixed-unit handling = reclassify whole unit + drop hedge at reframe; check_content_unit_embedded_actionable_fact heuristic (validated: fires 1x on u0021 only); words/net retroactive fix spec; ../../issues literal-match won't resolve (corrected planning expectation) | Design + Execution spec | CURRENT
PC-082 | 6784-6890 | MT031 Phase 0 CLOSED (13 tests; fn count 46→47; sync_providers clean) + Phase 1 CLOSED 2026-08-10 (words/net Project History section added; u0021→2_mechanism AGENTS.md line-46 corroboration stronger than expected; u0024→4_verifiable_history; dropped_content still 9 findings unchanged — disclosed; commit 9917b40f50; ST-021 live instance: real .git/index held stale 953-line snapshot of checks.py vs HEAD 3621) | Execution result | MT031 CLOSED
PC-083 | 6892-6940 | Plan File Hardening Pass 2026-08-10 (post-MT031): converts distributed prose disclosures into taskcard register; Change Log table records: 2026-08-11 TC-HARDEN-12..18 added from MT033 audit; TC-HARDEN-18 (stale staged index) closed; TC-HARDEN-12 (wire only_mermaid/only_sections into recheck, commit 46aff7a361) closed; TC-HARDEN-13 (first-ever full e2e chain vs 3d/typescript, run rr-20260811T165236Z; TC-HARDEN-04 closed via Option B per-product downgrade) closed; 2026-08-12: TC-HARDEN-01 Python verification runner REAL (opt-in --python-runner; email/python 14 blocks 9 clean; other 6 langs stubs); MT034 (TC-HARDEN-19..24: dead Enterprise-link regression 404, license-detection bug, duplicate table row, Prose Quality & Regeneration Comparison Protocol); TC-HARDEN-26/27 closed (license template check + banner homepage link; commit 5965261a82); MT034 Phase 2: 27 banners fixed, 15/30→clean; MT035 (TC-HARDEN-30..37) forensics: 11 stale Status fields fixed, 39-char SHA fixed, check_api_reference_classes self-disabling gap (TC-31), CLI crash risk (TC-30), onboarding docs (TC-35); TC-30/31/35 closed; TC-28 closed (format casing API-ref exclusion; WordML key collision found); TC-36 closed (hybrid re-verified); TC-29 closed in stages (5 products + pdf/net 166-finding agent + pdf/java 497 + 3d/net 108 after index-staleness rediagnosis); audit-portfolio CLI subcommand built (TC-HARDEN-05 partially_done — recurring-trigger half deferred); TC-34 (4 new languages) + TC-32 (installation-vs-registry check; downgraded to heuristic after finding 2 REAL package_registry.json data bugs: words/net published:false stale, email/net casing wrong) closed; 2026-08-13: TC-33/37/15/16 closed (family gate, reference dirty heuristic, actions ledger REAL at reports/repo_presenter_actions.jsonl, mirror placeholders hand-fixed + REAL sync_providers.py extraction bug affecting 14 skills/42 mirrors DISCLOSED NOT FIXED); TC-29 full closure; 30-product regen-full comparison pass (6 wrong-class-count instances, 4 new BLOCKING upstream defects, cells/python ChartCollection.add false claim confirmed, TC-HARDEN-38 leak-scan-unit bullet-collapse bug fixed); upstream-issues.md audit (4 gaps fixed, 2 files severity-vocabulary standardized) | Execution results / register | CURRENT hardening record
PC-084 | 6941-7020 | §2 Audit Findings sources (self-disclosures + MT033 independent audit + MT034 empirical); §3 Resolved/Preserved list incl. CORRECTED S-120 bullet (45 fns not 47 at ccc8736f49; skill infrastructure real but NEVER was the mechanism producing the real work until TC-HARDEN-13); MT030 Phase 2 closed 30/30 w/ mid-phase checker bug; 4 external 3d PRs (java+typescript MERGED by user; net/python open at that time); §4 register begins | Status claims / register | Key input for reconciliation

## Chunk 11: lines 7020-7440
PC-085 | 7020-7057 | §4 Unresolved Work Register index (TC-HARDEN-01..38): OPEN at register time: TC-02 (SKIP_SKILL_CONTEXT_CHECK, external blocker P0), TC-03 (DAR gate, P2, governance-owned), TC-05 partially_done (recurring trigger deferred), TC-06 (missions never registered, P3 deliberate), TC-08 (/repo-presenter-metadata not built P3), TC-09 partially_done (pdf/cpp 182 filler descriptions P4), TC-10 partially_done (live push via CLI still open P1), TC-11 follow_up (formats.md upstream P4), TC-14 partially_done (verify_content_units/verify_api_table not retired), TC-17 not_attempted (repo-presenter durability policy P1). CLOSED: 01(Python only), 04, 07, 12, 13, 15, 16, 18-38 mostly | Register (authoritative open/closed at 2026-08-13) | Verify each open item vs current tree
PC-086 | 7059-7104 | TC-MT030-P2-ROLLOUT taskcard (spec preserved; closed 2026-08-10 with full record elsewhere) | Taskcard | CLOSED
PC-087 | 7107-7192 | TC-HARDEN-01 full card: Python runner real (opt-in), email/python live proof (commit 212c724213); 6 languages honest stubs REMAIN OPEN (P0 for live pushes in those languages); Fragment taxonomy not attempted (disclosed v1 limitation) | Taskcard | PARTIAL — Python done, 6 langs open
PC-088 | 7195-7236 | TC-HARDEN-02 (SKIP_SKILL_CONTEXT_CHECK live; external; cannot be closed by skill execution) + TC-HARDEN-03 (DAR bare-data-file rows; 6 skills; governance-owned) | Taskcards | OPEN external
PC-089 | 7239-7292 | TC-HARDEN-04 full card CLOSED (Option B conditional downgrade; commit 3a5d2fe357; index went stale again immediately — recurring TC-18 pattern) | Taskcard | CLOSED
PC-090 | 7295-7363 | TC-HARDEN-05 full card: audit-portfolio built (commit 721c49b6cb; drop-in replacement proven 25/30 match); recurring-trigger half DELIBERATELY DEFERRED (needs user decision; reports/ gitignored → no GitHub CI possible); CORRECTED premise: pre-commit reports/ guard downgraded to warn-only 2026-08-08; simulate_pr_checks.sh still hard-blocks | Taskcard | PARTIAL |
PC-091 | 7366-7386 | TC-HARDEN-06: missions unregistered (deliberate every time); plan file + memory = only durable records; needs root slot + registration pass | Taskcard | OPEN P3
PC-092 | 7389-7424 | TC-HARDEN-07 CLOSED: 3d/java PR#2 merged by user via default merge button (no trailer visible tip; accepted); 3d/typescript PR#2 agent-squash-merged — DURABLE PATTERN: agent merges via gh pr merge --squash --delete-branch on user go-ahead | Taskcard | CLOSED; pattern CURRENT
PC-093 | 7427-7440+ | TC-HARDEN-08: /repo-presenter-metadata not built; needs explicit user go-ahead; Impl Seq Steps 5-6 | Taskcard | OPEN P3 (continues)

## Chunk 12: lines 7440-7860
PC-094 | 7445-7461 | TC-HARDEN-09 card: pdf/cpp 182 filler descriptions, partially_done, P4 (rewrite or accept decision) | Taskcard | OPEN P4
PC-095 | 7465-7517 | TC-HARDEN-10 card: push dry-run REAL (commit-tree 35e6be2367 vs 3d/typescript); LIVE non-dry-run push never exercised via CLI — remains open P1; requires fresh explicit authorization | Taskcard | PARTIAL (NOTE: later note/python PR #5 was a live CLI push 2026-08-15 per actions ledger — verify whether this closed) 
PC-096 | 7520-7533 | TC-HARDEN-11 card: formats.md upstream reliability, follow_up P4, owned by repo-scout lane | Taskcard | OPEN (external)
PC-097 | 7537-7596 | TC-HARDEN-12 card CLOSED: rolling snapshot checks/last_checked_candidate.md; recheck --allowed-headings/--mermaid-only; change_isolation_* results; commit 46aff7a361 | Taskcard | CLOSED
PC-098 | 7599-7693 | TC-HARDEN-13 card CLOSED: first-ever full e2e chain (3d/typescript rr-20260811T165236Z); CORRECTION: working-directory binding already existed (_candidate_readme_path shared helper) — chain was correctly wired, just never run; TC-04 surfaced+fixed during; evidence tree preserved | Taskcard | CLOSED
PC-099 | 7696-7748 | TC-HARDEN-14 card partially_done: phase2_scan.py replaced by audit-portfolio; verify_content_units.py + verify_api_table.py NOT retired (diagnostic-detail equivalence unproven); retire only after equivalence proof | Taskcard | OPEN P2
PC-100 | 7752-7779 | TC-HARDEN-15 card (ledger): CLOSED 2026-08-13 per §4 (earlier text says not_attempted — the card body here is the pre-close spec; §4 row + changelog record closure; ledger at reports/repo_presenter_actions.jsonl w/ no-fabricated-backfill rule) | Taskcard | CLOSED
PC-101 | 7783-7815 | TC-HARDEN-16 card: skill-doc self-consistency (47-fn claim wrong at introduction: 45 real; mirrors placeholder; stale verified date) — CLOSED 2026-08-13 per §4 (card body pre-close) | Taskcard | CLOSED
PC-102 | 7819-7858 | TC-HARDEN-17 card: repo-presenter durability policy decision (a/b/c options), P1, NEEDS USER DECISION, not_attempted; forbidden: wholesale git-tracking reports/ | Taskcard | OPEN P1 — user decision

## Chunk 13: lines 7860-8280
PC-103 | 7861-7930 | TC-HARDEN-18 card CLOSED: index re-staged; follow-up: identical staleness on run.py + test file; standing rule = ALWAYS git_plumb_commit.py, never plain git commit, regardless of CLOSED status | Taskcard | CLOSED; standing rule CURRENT
PC-104 | 7934-8016 | TC-HARDEN-19 card CLOSED: _detect_enterprise_link via backlink_targets.resolve_backlink (source_subdomain sentinel); factpack enterprise_link; check_enterprise_edition_link_resolves hard gate (target_mismatch / no_verified_target; staleness non-blocking); 16 tests; forbidden: build_enterprise_anchor_suffix anchor-text convention | Taskcard | CLOSED; mechanism CURRENT
PC-105 | 8020-8064 | TC-HARDEN-20 card CLOSED: _detect_license_file 200-char case-insensitive substring; 4 tests | Taskcard | CLOSED
PC-106 | 8068-8118 | TC-HARDEN-21 card CLOSED: check_api_reference_table_no_duplicate_rows (correction: no _extract_section_body helper exists — reused _FULL_API_REF_SECTION_RE + _parse_readme_api_tables); DiagnosticSeverity duplicate EXISTS in live reference _index.md source itself | Taskcard | CLOSED
PC-107 | 8122-8190 | TC-HARDEN-22 card CLOSED (mechanism): tone-exemplar reading requirement + prose rubric + Regeneration Comparison Protocol in skill doc; honest limit: prose certification stays human; forbidden: mechanical prose-quality score | Taskcard | CLOSED (mechanism); protocol CURRENT
PC-108 | 8194-8280 | TC-HARDEN-23 card CLOSED: 3-product reproof through REAL CLI (isolated reports_root driver — configure() has no CLI flag); all TC-19/20/21 fail-closed proofs fired on real content (3d/typescript 404 case caught exactly); API weekly limit interruption disclosed; cells/cpp: limitations.md stub-detection false-positive pattern (~90 entries, knowledge-pipeline territory), live _index.md defects, badge links to non-existent CMakeLists.txt (uncaught by gates); 3d/ts: FBX fall-through resolved definitively; existing candidate caught 3 real bugs fresh agent missed (two-sided comparison); TC-HARDEN-25 discovered (license first-link assumption) | Taskcard + findings | CLOSED; several disclosed adjacent gaps

## Chunk 14: lines 8280-8700
PC-109 | 8280-8327 | TC-HARDEN-23 card closing detail (evidence preserved; runs ABANDONED; boundaries respected) | Taskcard | CLOSED
PC-110 | 8329-8422 | TC-HARDEN-24 card CLOSED: cells/cpp false stub-only bullet (10 classes all real) removed; barcode/python GS1 claim removed (universal UnsupportedCapabilityError); verified via real CLI runs; xml→XML casing collateral fix; both local-only NOT pushed (needs go-ahead) | Taskcard | CLOSED (content local-only)
PC-111 | 8426-8478 | TC-HARDEN-25 card CLOSED: license-link anchor-text preference over position; commit 16d8562a06; TTY-credential push failure recurred 3rd time — documented manual token-push + retroactive record workaround | Taskcard | CLOSED
PC-112 | 8482-8560 | TC-HARDEN-26 card CLOSED: check_license_section_matches_template hard gate ('starts with' fixed template; pdf/go extra content OK); 4 narration phrases added; real-content re-verification (3d/ts reproof text caught verbatim); commit 5965261a82 | Taskcard | CLOSED
PC-113 | 8564-8652 | TC-HARDEN-27 card CLOSED: _detect_homepage_link (local _index.md existence = first-party guarantee; live-HTTP declined per stop condition); check_banner_links_to_homepage hard gate (verified→linked form required; unverified→must stay unlinked); factpack homepage now verified struct; 12 tests | Taskcard | CLOSED; banner now LINKED form CURRENT
PC-114 | 8656-8700 | MT034 Phase 2 rollout CLOSED 2026-08-12: scripted scan phase2_scan.py; 27/27 banners linked; 3 license-template fixes (pdf/cpp restored template+disclosure; slides/net+words/net absolute→relative LICENSE); enterprise_edition_link_resolves fired on 12 products all genuine target_mismatch (8 family-level fallbacks, 4 real bridge slugs e.g. cells/python-java, pdf/go-cpp) — slug non-1:1 finding still live | Execution result | CLOSED (continues)

## Chunk 15: lines 8700-9120
PC-115 | 8700-8761 | MT034 Phase 2 finale: collateral disposition-citation fix (3d/python u0052/u0063); final 15/30 clean; remaining 15 pre-existing (format_name_casing 12, api_reference_table_completeness 7, hybrid freshness 2 BY DESIGN not defect, html/python format claim pre-existing); not-done list | Execution result | CLOSED
PC-116 | 8764-9018 | Twenty-Second incident MT035 (2026-08-12) PLAN FORENSICS: Finding 1: register self-contradiction (11 taskcards CLOSED header vs stale Status field; 39-char SHA x3) — fixed in place; Finding 2: onboarding readiness (no onboarding docs anywhere; CLI crash risk; class-existence hard gate goes dark for new products — HIGHEST-PRIORITY; no installation check; 9-extension allowlist permanent language blind spot; families.json silent allowlist gap; confirmed-working list); Finding 3: TC-29 pdf/java+3d/net root cause = uncommitted working-tree edits to reference _index.md (+94.7%/+51.3% class growth) — concurrent-session moving target (LATER re-diagnosed as index staleness, resolved); Finding 4: TC-28 root cause 63% check false positives (headings, homonyms: Word field codes, PDF sc/SC operators, enum literals) / 37% genuine drift (MT028 tables added 1 day after certification); Finding 5: hybrids genuinely hold, freshness gate working as designed; preservation list re-tested; 15/30 count independently reproduced | Investigation (adversarial audit) | Findings fed TC-30..37; all since closed
PC-117 | 9020-9119 | TC-HARDEN-28 card CLOSED (commit 48bc00974a): two-map design (canonical branch full-doc; elif branch excludes API-ref section then headings); ordering bug found live; 24 recasings across 8 products; WordML/WORDML key collision (first-seen-wins canonical); 2 disclosed permanent residuals (DOT, ONE); 43→1 FP; 15/30→17/30 | Taskcard | CLOSED

## Chunk 16: lines 9120-9540
PC-118 | 9135-9276 | TC-HARDEN-29 card CLOSED (full detail): 5-product fixes (real dual-namespace verifications DiagnosticSeverity/CFBWriter/NotesSlidePart/Document/Table); pdf/net 166 via dedicated agent (59 migrated rows moved not deleted); pdf/java 497 + 3d/net 108 (misdiagnosis corrected via TC-37 tool; index staleness not moving target; 484+103 classes added; re-verified 0/0) | Taskcard | CLOSED
PC-119 | 9279-9345 | TC-HARDEN-30 card CLOSED (commit 4c3b7075be): _load_json_registry + _PRODUCT_REQUIRED_FIELDS; catch-all in main() explicitly DECLINED (recorded decision) | Taskcard | CLOSED
PC-120 | 9348-9421 | TC-HARDEN-31 card CLOSED: option (a) — both-sources-absent now emits named 'verification unavailable' finding per cited class; test rewritten from noop-asserting to flags-asserting; 15/30 unchanged on real content | Taskcard | CLOSED
PC-121 | 9424-9511 | TC-HARDEN-32 card CLOSED (commit 071bdc0ad4): check_installation_matches_package_registry as HEURISTIC (evidence-driven deviation from hard-gate spec); 2 check bugs fixed; 2 REAL package_registry.json data bugs found (email/net casing wrong — registry wrong README right; words/net published:false stale — verified live nuget) — registry read-only boundary held; final 1 real finding (words/net) | Taskcard | CLOSED; words/net registry staleness = OPEN MT015-owned data gap
PC-122 | 9514-9540 | TC-HARDEN-33 card (families.json allowlist gap): body reads not_attempted, options (a)/(b) — CLOSED 2026-08-13 per §4/changelog via option (b) _check_family_registered in start_run | Taskcard | CLOSED

## Chunk 17: lines 9540-9960
PC-123 | 9552-9599 | TC-HARDEN-34 card CLOSED: _CLASS_SOURCE_EXTENSIONS widened to 15 (php/kt/kts/rb/swift); no keyword change needed; 6 tests | Taskcard | CLOSED
PC-124 | 9603-9677 | TC-HARDEN-35 card CLOSED: onboarding section in skill doc (prerequisite chain, data-files table, expected first-run experience, honest disclosed-gaps subsection); synced mirrors | Taskcard | CLOSED; onboarding doc CURRENT
PC-125 | 9681-9724 | TC-HARDEN-36 card CLOSED: decided_at bump w/ real re-verification (Forms::Form file:line); forbidden: blind date bumps elsewhere | Taskcard | CLOSED; note daily hybrid freshness re-trigger is BY DESIGN recurring
PC-126 | 9728-9763 | TC-HARDEN-37 card (reference_index_source_dirty heuristic) — body pre-close; CLOSED 2026-08-13 per §4 | Taskcard | CLOSED
PC-127 | 9765-9777 | §6 Lane Ownership table (9 lanes incl. new Prose-quality, Onboarding-documentation, Durability/policy, Operator/environment) | Governance structure | CURRENT
PC-128 | 9779-9818 | §7 Gate Contract rules 1-6: two tiers only; prove fail-closed; prove against real content; canonical exercising tools; rule 5 call-site wiring (MT033); rule 6 wording≠target (MT034) | Rules | CURRENT
PC-129 | 9820-9861 | §8 Evidence Contract rules 1-7: content-dispositions authoritative; verification.status confidence gradient; upstream-issues authoritative; presence-not-proof ceiling; commit messages carry verification numbers; evidence trees checked on disk not assumed (rule 6); aspose_com_targets is cached-not-live (rule 7) | Rules | CURRENT
PC-130 | 9863-9888 | §9 Verification Matrix (per-mission verification method/status/confidence; verify_examples 6-langs LOW confidence; live push unconfirmed at that time; MT033/034/035 audit rows) | Status register | Key reconciliation input
PC-131 | 9890-9913 | §10 Repair Loop (6-step protocol: build w/ real fixtures, prove fail-closed, run against real content, fix+regression-test, portfolio rollup, record honestly) | Rules | CURRENT
PC-132 | 9915-9959+ | §11 Anti-Overclaim rules 1-9+ (heuristic≠fact; gate proves narrow claim; verified-against-source vs by-corroboration; rollup required; absence≠correctness w/ known blind spot; closure names NOT-done; registered≠used (7); prose naming infra ≠ code consumes it (8); mechanically-checkable ≠ prose quality (9)...) | Rules | CURRENT (continues)

## Chunk 18: lines 9960-10380
PC-133 | 9960-9984 | Anti-Overclaim rules 10-11: certification decays with later missions (date-stamp claims); fail-open/closed must be verified for ABSENT-data case separately | Rules | CURRENT
PC-134 | 9985-10043 | §12 Closeout criteria: hardening passes 1-4 closed; S-120 "production-complete" bar = 4 conditions: MT030 30/30 (met), TC-01 per-language verify (Python met, 6 langs open), TC-10 LIVE push (dry-run met, live open at that time), TC-12 wired (met), TC-13 e2e (met) — "real, heavily-hardened, human-gated tool in active iterative use — not a finished, closed system" | Status claims | KEY VERDICT LANGUAGE
PC-135 | 10044-10093 | §13 Remaining True Blockers: TC-02 SKIP var (open, external); TC-07 closed; TC-01/TC-10 not hard blockers for local work but real for live-push trust; TC-17 durability decision (open); TC-18 closed; TC-29 blocker re-diagnosed RESOLVED | Register | OPEN: TC-02, TC-17
PC-136 | 10095-10180 | TC-MT030-P2-ROLLOUT CLOSED 2026-08-10: 25 products 6 batches; noise-filter checker bug fixed mid-rollout (commit c86b90bd36); 139-unit coverage gap honestly reopened across 21 products incl. 3 'closed' pilots → 5 more batches closed all; unit_id position-instability handled via bijection verification; whole-portfolio re-verification run twice; remaining non-zero gates: dropped_content 24/30 (TC-04 gap) + 3d/typescript api-table 8 (both later fixed) | Execution result | CLOSED
PC-137 | 10182-10379 | Seventeenth incident MT032 (2026-08-10): PR/merge workflow redesign; verified findings (real merges intact; squash settings COMMIT_OR_PR_TITLE/COMMIT_MESSAGES; no branch protection anywhere); fix: (1) no draft mode; (2) always squash-merge — SUPERSEDED 2026-08-11: agent executes merge via gh pr merge --squash --delete-branch after explicit per-PR user go-ahead (3d/java merge-button mistake); CORRECTED 2026-08-13 (Twenty-Third incident): must pass explicit --body with exactly one Co-authored-by trailer (real model), never bare (GitHub auto-appends human as co-author — present in 3d/ts + cells/cpp merges); (3) PR body 3 sections, upstream-defects section retired; (4) co-author = executing agent identity; branch cleanup via --delete-branch; execution record 3d/java PR#2 opened 2026-08-11 | Incident + Design revisions | CURRENT PR/merge procedure

## Chunk 19: lines 10380-10800
PC-138 | 10380-10444 | MT032 execution outcomes: 3d/java PR#2 merged via WRONG default button (left as-is; rule moved merge into agent automation); 3d/typescript PR#2 agent-squash-merged clean (7b959706) — first proof of revised rule; Twenty-Third incident correction 2026-08-13: gh default squash message auto-appends redundant human Co-authored-by trailer → always pass explicit --subject/--body w/ exactly one model trailer; documented in skill doc | Execution + correction | CURRENT merge procedure
PC-139 | 10445-10470 | MT032 validation + tradeoffs (squash flattens multi-commit PRs; no dry-run for merges; visual review of first real PR) | Risks | LEGACY
PC-140 | 10472-10800 | Nineteenth incident MT033 (2026-08-11) deep production audit: TRIGGER 'has plan actually been converted to skill?'; live staged-index regression found first; assessment scope (run.py 1486 lines then, checks 3789 lines/45 check_* then, tests 14+292); CORE FINDING: real flow never used the CLI — agents edited reports/repo-presenter directly, verified via gitignored scratch scripts, pushed via manual SOP; reports/readme_refresh_runs ABSENT on disk; zero FileLock acquisitions; 43/45 checks wired but 2 idempotency checks orphaned; 'sound design, never used'; root causes 1-3 (parallel system, verify_examples stub, no evidence/attribution — 14/19 commits trailered S-99 not S-120); structural weaknesses (dual verification surfaces, orphaned idempotency gates, no input pinning → nothing invalidates stale content, reports/ undifferentiated bucket, doc staleness, index hazard); preserve list; redesign list (binding layer, verify runner, live push, wire orphans, actions ledger, doc self-consistency, durability); target design: --working-dir binding (later found already correct via _candidate_readme_path — TC-13 correction) | Investigation (pivotal audit) | HISTORICAL — largely addressed by TC-HARDEN-12/13/01/15/16; remaining: durability TC-17, live push (later note/python PR#5?), 6-language runners

## Chunk 20: lines 10800-11220
PC-141 | 10800-10950 | MT033 target design + implementation direction (8 steps) + verification strategy + tradeoffs + FINAL ASSESSMENT: STRUCTURAL_REDESIGN_REQUIRED (boundary integration, not rebuild) | Investigation conclusion | HISTORICAL — steps 1-7 since executed (per TC-12/13/14/15/16/01); step 8 durability STILL OPEN (TC-17)
PC-142 | 10951-11046 | Twentieth incident MT034 (2026-08-12): pilot regeneration findings 1-5 (dead Enterprise link 404; _detect_license_file prefix bug x2 independent; duplicate table row; 2 live content defects incl. under-claim inverse defect; 3d/ts FBX genuinely-unresolved → later resolved by TC-23 reproof: FBX unreachable via Scene.save dispatch); root cause = infra named in prose never wired into code (corrects user's own belief plan was fixed) | Incident + findings | LEGACY_CONTEXT; fixes CURRENT via TC-19..21
PC-143 | 11047-11126 | MT034 fix design: resolve_backlink reuse (sentinel source_subdomain); _detect_enterprise_link code spec; check_enterprise_edition_link_resolves hard gate; _detect_license_file 200-char fix; duplicate-rows check | Design | CURRENT (implemented)
PC-144 | 11127-11193 | Prose quality section: user verbatim brief; honest limit (naturalness ≠ regex); 3 mechanisms: (1) mandatory tone-exemplar reading (2-3 sibling candidates, register diversity), (2) positive prose rubric (cells/cpp exemplar sentence; agent self-check not gate), (3) Regeneration Comparison Protocol (structural/factual/wording-tone classification; report written per-product; regenerated candidate NEVER silently replaces existing; human go-ahead required) | Design decision | CURRENT
PC-145 | 11194-11220 | MT034 execution order Phase 0/1/2 (code → re-prove same 3 artifacts → portfolio gated on fresh go-ahead) | Plan | EXECUTED (TC-19..27 + Phase 2)

## Chunk 21: lines 11220-11660
PC-146 | 11223-11347 | Twenty-First incident (2026-08-12): License free-form prose SAME defect as 2026-08-04 (rule prose-only, never mechanical) → TC-HARDEN-26; new banner-homepage-link requirement (distinct from MT026 image-URL decision) → TC-HARDEN-27; 'must never be broken' via local content/ existence (first-party guarantee), live-HTTP declined disclosed | Incident + design | CURRENT (implemented)
PC-147 | 11349-11481 | Twenty-Third incident (2026-08-13): cells/cpp cited upstream-issues.md in Dev&Testing; PUBLIC-SOURCE ALLOWLIST POLICY (user): limitation only if stated in approved public source of target product; fix commit 3a49bfc969: _INTERNAL_LABEL_PATTERNS blocks internal artifact names (upstream-issues.md, content-dispositions.json, .clone_cache, knowledge/merged, reports/*); narration pattern added; check_scope_limitations_format zero-bullet+invented_filler; skill doc public-source allowlist (source code stays allowed — disclosed interpretation); 18 tests (428); isolation proof (SHA-256 1-of-30 changed); FIRST REAL LIVE PR MERGE through full sequence: cells/cpp PR#2 merged squash (9f852d0ff1); clone cache fast-forwarded; redundant co-author trailer defect found → merge procedure corrected; format_name_casing fence-tag false positive DISCLOSED NOT FIXED (portfolio-wide gap flagged) | Incident + Execution result | CLOSED; policy CURRENT; fence-tag FP verify current
PC-148 | 11482-11660 | Twenty-Fourth mission (2026-08-13, cells/go): Project Structure section lost (fenced-tree stripped by extractor → structurally invisible; TC-04 downgrade theory false for never-captured units); badges greenfield (no mechanism); second upstream-issues leak already caught by 23rd fix (generalization proof); design: structure-dispositions.json + badge-dispositions.json (unit_id reuse of evidence gate); extract_old_readme_structural_units (zero-prose + ≥60% fenced shape test); badge extract/classify/verify (tier 0/1/2)/reconcile (category+target pairing; deterministic priority; dedup_ambiguous) | Mission design | CURRENT (implemented per code inventory: extract_old_readme_structural_units + badges real)

## Chunk 22: lines 11660-12080
PC-149 | 11660-11730 | Twenty-Fourth mission design cont'd: open design questions disclosed (60% threshold single-product-validated; H2 target default; badge precision; Tier-2 live verifier out of scope); 7-stage execution mapping; critical files; verification | Design | CURRENT
PC-150 | 11730-11785 | Twenty-Fourth mission CLOSED 2026-08-13: mechanisms landed (11 badge/structural checks; 51 tests); 2 machinery gaps found live (heading field required; Additional Examples missing from target-sections allowlist); commits 4542d2cc51 + f652453f31 (TTY-push-hang recovered via object-store salvage); cells/go PR#1 squash-merged 9f0a4033b5 — USER DIRECTIVE: use ONLY reports/repo-presenter-regen-full/ candidates for target repos for this pass; redundant co-author trailer defect found again → skill doc documents explicit --subject/--body rule | Execution result | CLOSED; regen-full = publication source directive
PC-151 | 11786-12080 | Twenty-Sixth incident MT036 (2026-08-13, cells/java): (1) LIVE upstream package rename com→org.aspose.cells_foss (clone cache stale 2 commits; 20 imports broken); fix-the-skill directive → check_code_example_imports_match_source hard gate (Java only, 7 tests, 13 real findings→0); (2) coverage audit: 66 units 0 gaps BUT 28 stale evidence_ref paths (disposition-staleness defect class — recurring risk DISCLOSED unsolved); upstream's own README has stale Project Layout path (not copied verbatim); Project Structure missing (same cells/go class); Project Structure added to target-sections allowlist; internal-label leak fixed (vaguer phrasing to avoid fingerprint trip); (3) two PRE-EXISTING diagram hard-gate failures — checks worked, gap was composition contract: skill doc MISSING Inputs-test rules 2a-2e + STALE Starting-Points rule (hybrid-only vs real archetype-general); NEW rule 2e (embedded/attached auxiliary material, both-conditions test, PictureCollection sniff verified, 9-sibling zero-counterexample base); resolution guidance (delete duplicate node, don't strengthen evidence); NEW heuristic check_diagram_container_duplicates_capability; NEW hard gate check_project_structure_canonical_tree_format (box-drawing); cells/java fixed (i2/o2 deleted); 491 tests; NOT pushed | Incident + Design + Execution | CLOSED (local); rules CURRENT

## Chunk 23: lines 12080-12500
PC-152 | 12084-12325 | Twenty-Seventh incident MT037 (2026-08-13, cells/java): Key Capabilities dry/SEO; findings: 8/10 identifier-first monotony; keywords/{family}.json REAL data source NEVER connected + CONFIRMED cross-platform contaminated (cells/java entry all .NET/C# phrases; same for python/rust across 3 subdomains); 2 heuristic findings investigated (u0032 tone FP confirmed working-as-designed; 7 dropped headings = legitimate rename pattern); design: _detect_seo_keywords + filter_relevant_seo_keywords (platform token map + verified-fact overlap + ≤6 cap); composition guidance (placement not markup — no backticks/bold for keywords); check_key_capabilities_structural_variety (70% identifier-first threshold heuristic); check_key_capabilities_formatting (backtick parity, punctuation, case); TC-HARDEN-39..42 | Incident + Design | CURRENT
PC-153 | 12326-12399 | Twenty-Seventh EXECUTION CLOSED 2026-08-13: implemented; 24 tests (515 scoped); real proof (9/11 82% fired); filter dropped ALL 10 contaminated phrases (honest empty result; no keywords forced); 11 bullets rewritten (27% identifier-first); 1 real regression found via battery (word-overlap evidence trail broken by phrasing change — 1-word fix 'Validate data'; standing warning in skill doc); fn count 59→64; no commit per user constraint | Execution result | CLOSED
PC-154 | 12401-12449 | cells/java PR push+merge CLOSED 2026-08-13: pre-existing PR#1 from OLD readme-agent system found → user chose close-then-replace; PR#2 merged squash WITH explicit --subject/--body (779c9640ee) — NO redundant human trailer (fix holds live); clone cache fast-forwarded; old PR#1 stale branch left untouched | Execution result | CLOSED
PC-155 | 12451-12500 | Twenty-Eighth incident MT038 (2026-08-14, cells/net): clone 2 commits stale (26.6→26.7 version, Product Links section; zero public API change verified); version pin defect; STRUCTURAL: content-dispositions ID-drift class REAL — +2 shift misattached 31/38 dispositions (coverage check blind; 2 heuristics leaked symptoms); bijection re-verification before fixing (continues) | Incident | continues

## Chunk 24: lines 12500-12920
PC-156 | 12500-12570 | MT038 cont'd (cells/net): fix through real CLI via mirror reports_root (CLI path hardcoded to repo-presenter tree); full chain start→approve; ingest failed closed once on real disposition targeting mistake (fixed evidence_ref); INGEST OK 0/67; recheck byte-identical idempotency; verify_examples honest C# stubs; promoted to regen-full + third independent verification; abandoned to release lock; NOT DONE: no code change, no PR, stale knowledge/ facts disclosed, NO portfolio-wide ID-drift detector (disclosed recurring risk, second live instance) | Execution result | CLOSED; ID-drift detector = open gap (later TC-MICRO-02?)
PC-157 | 12572-12865 | Twenty-Ninth incident MT039 (2026-08-14): 'mirrors reference.aspose.org's own class index' — FIFTH narration category: generation-mechanism/design-rationale narration; 10 instances across 9 products (4 paraphrased, no literal domain); slides/net near-miss (word-locked pattern synonym evasion); legitimate mirror-usages positive-controlled; root causes: no skill-doc guidance for API-ref intro phrasing; no check; TONE-EXEMPLAR CONTAMINATION FEEDBACK LOOP (imitation propagation — structural risk class); fixed phrase lists reactive; fix design: 2 structural-shape patterns + widened upstream-repository pattern + skill-doc BAD/GOOD rule + exemplar contamination guard (check exemplar clean first) + retroactive 10-instance fix + audit-portfolio sweep; TC-HARDEN-43/44/45 | Incident + Design | Implemented? (verify) — patterns/guards CURRENT
PC-158 | 12866-12920 | Thirtieth incident MT040 (2026-08-14): Mermaid node-text clipping — REPRODUCED LIVE against GitHub's real renderer (viewscreen.githubusercontent.com sandboxed iframe — previously undocumented architectural fact; puppeteer-core + system Chrome technique built; mermaid.ink proxy validated); definitive 9-published-README inventory: clipping ONLY on 3d/net + 3d/python (still on OLD per-node wired diagrams from 2026-08-05 PR#1, never migrated); all new-model diagrams clean (continues) | Incident + Investigation | continues

## Chunk 25: lines 12920-13340
PC-159 | 12920-13030 | MT040 cont'd: 7/9 published clean; only 3d/net + 3d/python clip (OLD wired model; converging edges → mermaid dagre white-space:nowrap inconsistency); upstream mermaid-js#6424 long-word bug tested and ruled out (21-char corpus tokens safe); classification: no active machinery defect (check_diagram_shape already blocks old model); publication-state gap (2 of 4 3d repos never got simplified-diagram follow-up PR) | Root cause | HISTORICAL
PC-160 | 13030-13130 | MT040 fix: republish 3d/net + 3d/python re-expressing LIVE labels in flat model (NOT local candidates — local trees diverged, out of scope); diagram contract formalized (28-char token ceiling heuristic check_diagram_label_token_length); implementation + validation (live re-render REQUIRED post-push); honest limits (28 not font-metric-derived; light theme unverified; local-tree divergence unresolved; no hybrid product published — coverage gap) | Design | TC-HARDEN-46/47/48 (P0 republishes — verify executed?)
PC-161 | 13169-13191 | TC-HARDEN-46/47/48 cards (label-token-length check; republish 3d/net; republish 3d/python; closeout = live re-render post-merge) | Taskcards | verify status
PC-162 | 13192-13340 | Thirty-First incident MT041 (2026-08-14, cells/rust dependencies): Installation 'no external runtime needed' contradicts Intro's own 7-crate list; pattern structural (pdf/cpp prose 'none' unverified; 4 genuinely zero-dep products unverified); claims.json has 7 scout-verified dependency claims consumed by NOTHING; tomllib available; per-platform manifest facts verified; precedent mapping (2-of-3 model, TC-32 heuristic downgrade lesson, sibling-JSON pattern, only_sections_changed reuse); fix: NEW MODULE dependency_extract.py (TypedDicts; DependencyEntry schema: ecosystem/source_type/category/dev_only/activating_feature/platform_condition/role/purpose-never-invented/is_direct) | Incident + Design | CURRENT (module real: 975 lines, 39 tests)

## Chunk 26: lines 13340-13760
PC-163 | 13340-13470 | MT041 dependency model detail: DependencySnapshot schema (applicable=False earned C++ fact; parse_errors raise-or-empty invariant); 7 per-ecosystem extractors (tomllib Cargo/pyproject; setup.py NEVER exec'd; csproj shortest-path; pom.xml namespace-strip + dependencyManagement excluded; go.mod // indirect excluded; npm peer→optional; C++ manifest-probe); data/dependency_overrides.json human override escape hatch | Design | CURRENT (implemented)
PC-164 | 13472-13530 | MT041: fail-closed plan_run wiring (_block + recover re-entry); claims.json corroboration confirmed NOT independent (lossy projection of older parse; same_revision logic); _detect_dependency_claims + cross_reference_dependency_claims | Design | CURRENT
PC-165 | 13533-13596 | MT041: ## Dependencies REQUIRED section after Installation (fixed sentence 'No required third-party package dependencies.' for verified zero); sub-headings omission rules; pdf/cpp Requirements line superseded via Corrected disposition; Claims Policy _UNQUALIFIED_DEPENDENCY_CLAIM_PATTERNS (bare 'runtime' never accepted qualifier); 12 validators table (hard/heuristic per reliability lesson) | Design | CURRENT
PC-166 | 13597-13645 | MT041 item 8: extend content-dispositions enums (5_dependency_claim, corrected, verified_against_manifest, Dependencies target) NOT a new sibling file (reversal of first-draft; structural-blindness rationale); HONEST CORRECTION: cells/rust false sentence was composition-time hallucination, NOT mis-reconciliation (upstream README was correct) | Design + correction | CURRENT
PC-167 | 13647-13759 | MT041: dependency-verification-matrix.json (reviewer-facing, non-gating); idempotency via only_sections_changed; skill-doc terminology subsection; 17 regression tests; execution plan Phase 0 + Phase 1 (cells/rust pilot, NO push); risks (claims.json non-authoritative; purpose omitted; setup.py/Gradle forward gaps; 1-product scope — 30 others may carry defect class, out of scope) | Design + plan | Phase 1 executed? (verify; MT041 per memory: cells/typescript generated via real CLI...) 

## Chunk 27: lines 13760-14180
PC-168 | 13760-13860 | MT041 taskcards TC-HARDEN-49..56 (module, plan_run hookup, required section, claims policy, 10 validators, disposition enums, matrix+skill-doc, cells/rust pilot) | Taskcards | CLOSED
PC-169 | 13861-14041 | MT041 CLOSED 2026-08-14: all 8 taskcards executed; 4 extractor bugs found live (cargo param mis-type; CMake size heuristic FP → construct-based; cells/cpp actually HAS a CMakeLists one level down — corrected earlier plan assumption; override consulted for unregistered platform too); 3 Claims-Policy regex bugs (bare 'library' rescue; requires-no anchoring; compound-claim clause splitting); scope_claim_matches_evidence downgraded hard→heuristic (no proprietary_runtime verifier exists — TC-32 lesson recurring); _bulleted_dependency_names first-token-only bug; version digit-collision bug; TC-56 pilot: cells/rust fixed (real defect sentence still present — earlier grep missed via line wrap), ## Dependencies added, 0/80 hard gates, idempotent, matrix 7/7 3-of-3; NOT pushed; 583/583 tests; NOT done: 30-product unscoped-claim sweep, proprietary_runtime verifier | Execution result | CLOSED; open: portfolio sweep for unscoped claims, proprietary_runtime verifier
PC-170 | 14042-14180 | Thirty-Second incident MT042 (2026-08-14, cells/typescript 1-badge candidate): full 30-product survey (2-5 badges everywhere; License 30/30; Contributors 24/30; package-version iff published; CI iff workflow exists — zero-exception correlations); existing badge mechanism reconciliation-ONLY (vacuous pass on zero old badges); FOURTH instance of 'reconciliation exists but composition floor/spec missing' structural shape (TC-19 enterprise, TC-27 banner, TC-32 install, badges); category availability all derivable from already-computed data | Incident + Investigation | Design follows (next chunk)

## Chunk 28: lines 14180-14600
PC-171 | 14180-14355 | MT042 fix design: _detect_available_badges (5 categories, zero new extraction; _BADGE_LANGUAGE_VERSION_TEMPLATES seed table); check_badge_row_meets_verified_floor HARD (License + ≥1 more when available; contributor_count always-available safety net → safe to hard-gate); check_badge_available_fact_not_shown heuristic; extend installation registry check to badge row; skill-doc discipline principle (detector + verifying check for every new template element); TC-HARDEN-57..60 | Design | CURRENT
PC-172 | 14356-14441 | MT042 CLOSED 2026-08-14: all 4 taskcards; 2 design corrections (language_version only Go reachable; go package_version = language_package_reference not package_version); 1 real classifier bug (C++ toolchain badge pattern missing cpp) fixed at source; 0 findings 30/30; 587 scoped tests; NOTE: work UNCOMMITTED (no commit go-ahead); audit-portfolio 0/30 clean attributable to MT041's deliberate Dependencies-section rollout gap (only cells/rust has section — 30 products fail required_sections) — DISCLOSED | Execution result | CLOSED; NOTE: portfolio 0/30 vs required_sections = expected transitional state pending Dependencies rollout
PC-173 | 14443-14511 | cells/typescript PR push CLOSED 2026-08-14: registry exclusion honored (not edited; user auth for this action); pre-push 0/~80 gates; pre-existing PR#1 (owner's own May PR, CONFLICTING, stale premise) surfaced → user chose close-then-open; PR#2 merged squash with explicit --subject/--body-file (single trailer verified); clone cache fast-forwarded | Execution result | CLOSED
PC-174 | 14513-14600 | Thirty-Third incident MT043 (2026-08-14): Enterprise anchor text 'for .NET' vs family URL; Stage 1 verified cells/typescript = standalone TS (no native/JVM artifacts); Stage 2 three candidate destinations live-fetched (nodejs-java/nodejs-cpp = different implementation models, rejected; family page + family-neutral anchor correct); root cause: type field computed but NEVER read downstream to constrain anchor wording (Gate Contract rule 6 third dimension: semantic accuracy); SECOND root cause: _detect_enterprise_link never passes canonical_overrides — platform_canonical_overrides.yaml policy (python-net for 4 families) CONFLICTS with aspose_com_targets.json manual-correction entry (cells/python → python-java) | Incident + root cause | continues

## Chunk 29: lines 14600-15020
PC-175 | 14600-14760 | MT043 continued: full 30-product Enterprise anchor audit — Class A (platform anchor on family URL) 11 products; Class B (bridge URL, anchor drops qualifier) 7 products; 13 clean; Stage 3 anchor-text contract v1 (exact/family/bridge/unresolved with 'via X' bridge wording + disclosure sentence); Stage 6 _classify_enterprise_relationship + canonical_overrides fix; Stage 7/8 check_enterprise_edition_anchor_matches_relationship; TC-HARDEN-61..66 | Design (v1 — bridge wording later REVOKED) | SUPERSEDED by MT044
PC-176 | 14761-14832 | TC-HARDEN-61..66 cards with MT044 corrections annotated in place (bridge split → platform/family/unresolved; disclosure regex INVERTED to prohibition; TC-63 clean rewrite never landed old scope; TC-64/65 rescoped by two-tree grep audit; TC-66: none of 5 live repos carry bridge wording) | Taskcards (corrected) | see MT044
PC-177 | 14835-15020 | Thirty-Fourth incident MT044 (2026-08-14): MT043's bridge contract itself was the policy defect ('you have made a mess') — USER'S PERMANENT RULES: (1) NEVER expose implementation bridges anywhere ('via Java/C++/.NET', wrapper/binding/backed-by); (2) compound slug → leading public platform name only (python-net→'Python', nodejs-java→'Node.js'); (3) family link = final fallback only when no platform page exists; Stage 1: code faithfully implemented wrong spec; skill doc NEVER updated (blast radius narrowed); URL resolution stays correct; 4 stale Class-A regen-full files predate check; Stage 2 exhaustive two-tree matrix (9 bridge-wording in repo-presenter; regen-full: 4 Class A incl. trigger, 1 bridge, 1 missing name, cosmetics); 2 disposition files cite bridge URLs internally (consistency pass); TWO-TREE CANONICITY = disclosed open question; Stage 3 corrected policy reuses PLATFORM_ALIASES + _PLATFORM_DISPLAY_NAMES | Incident + policy | PERMANENT RULES CURRENT

## Chunk 30: lines 15020-15440
PC-178 | 15020-15064 | MT044 Stage 3/4: canonical selection reuses resolve_backlink order (override→platform→family; 'multiple live candidates' unreachable by construction); CORRECTED anchor contract: platform destinations (exact OR compound slug) → [Aspose.{Family} for {Public Platform} — Enterprise Edition]; family → no platform name; invariants (never expose implementation suffix ANYWHERE in document) | Policy (corrected, CURRENT) | CURRENT
PC-179 | 15065-15132 | MT044 Stage 5/6: critical self-review; _classify_enterprise_relationship rewritten (platform/family/unresolved + public_platform; _BRIDGE_LANGUAGE_NAMES deleted); TWO-TREE canonicity disclosed open question (repo-presenter vs regen-full — 'which tree wins going forward' NOT resolved) | Design | CURRENT; OPEN: canonical tree question
PC-180 | 15133-15196 | MT044 Stage 7/8: anchor check rewritten (unified platform branch; bridge finding reasons deleted); NEW hard gate check_no_implementation_bridge_disclosure (portfolio-wide, 6 patterns, fenced-code-stripped; disclosed fixed-list limitation); tests incl. C++ regex-boundary bug ((?!\w) vs \b after +) | Implementation | CURRENT
PC-181 | 15250-15440 | MT044 Stage 9/10 EXECUTED CLOSED 2026-08-14: live re-scan replaced grep estimate; 12 unique products fixed (17 file edits + 2 disposition files); href stalenesses corrected (3d/python + email/python family→python-net; cells/python python-java→python-net); 0 findings both trees re-run twice; family fallbacks verified genuine; Edit-tool exact-match isolation; 5 published repos re-checked live: zero bridge wording; one open href-staleness on live cells/python repo (candidate ready, needs push authorization); 617 scoped tests; full suite 9756/3 (2 pre-existing + test_registration_check root-caused, continues) | Execution result | CLOSED; OPEN: cells/python live href push

## Chunk 31: lines 15440-15860
PC-182 | 15440-15445 | MT044 full-suite closure: 3rd failure root-caused = dependency_extract.py missing registry entry (pre-existing MT041 gap, do-not-commit constraint) | Status | resolved when committed (registry.yaml entry now exists per code inventory)
PC-183 | 15446-15749 | Thirty-Fifth incident MT045 (2026-08-15, barcode/python): 2 independent defects: (1) API Reference detail never collapsed (convention lived only via imitation; NO validator; 3 products affected incl. 3d/net + 3d/typescript regen-full — clean-room breaks imitation chain — 3rd confirmation of hazard class); (2) Enterprise link inside a limitation bullet — check_scope_limitations_format REAL BUG (blank-lines stripped before classification; wrapped continuation misclassified as prose); root-cause table; contracts (collapse deterministic size-independent — tex/python 11-class proof; Enterprise para separate); fixes: check_api_reference_detail_collapsed (hard) + _API_REF_SECTION_RE 3-way alternation re-bound + scope_limitations fix via _iter_leak_scan_units reuse + skill-doc BAD/GOOD pairs; TC-HARDEN-67..70 | Incident + Design | CLOSED
PC-184 | 15750-15815 | MT045 CLOSED 2026-08-15: all 4 taskcards; real correction mid-implementation (3-way alternation to avoid breaking existing test); barcode/python corrected surgically; isolation proven; 624 scoped tests; NO COMMIT (awaiting go-ahead); 3d/net + 3d/typescript regen-full collapse defects DISCLOSED NOT FIXED (follow-on work) | Execution result | CLOSED; open: 3d/net + 3d/ts regen-full collapse fixes
PC-185 | 15816-15860 | Thirty-Sixth incident MT046 (2026-08-15, font/python): Key Capabilities lead-in narrates editorial organization + leaks internal source-file fact (instancing.py largest module); confirmed freshly composed (not from dispositions); no existing check caught it (continues) | Incident | continues

## Chunk 32: lines 15860-16280
PC-186 | 15860-16178 | MT046 investigation cont'd: TWO compounding gaps (fixed-phrase-list limit; Key Capabilities intro text NEVER inspected by any consumer — structural blind spot); established legitimate convention (email/slides framing sentences = real architecture facts); plausible causal mechanism: TONE-EXEMPLAR FORM-WITHOUT-SUBSTANCE imitation (third exemplar risk class); Additional Examples scanned clean but shares structural gap; fix: _extract_section_intro_prose + check_section_intro_no_meta_narration (3 precision-first sub-patterns pre-verified against real controls); generalized skill-doc principle ('would this sentence be true if README rewritten from scratch?' test); safe fallback = OMIT framing sentence; TC-HARDEN-71..73 | Incident + Design | CURRENT
PC-187 | 16179-16232 | MT046 CLOSED 2026-08-15: all 3 taskcards; 15+1 tests; font/python sentence removed; 0/86 hard gates; 635 scoped tests; NO COMMIT; not-done: no portfolio sweep beyond negative controls | Execution result | CLOSED
PC-188 | 16234-16280 | Thirty-Seventh incident MT047 (2026-08-15, design-only): independent verification of font/python preservation audit artifact; pinned identities re-confirmed; Finding 1 (3 internal reporting.py classes leaked into public API table via reference-site index)... (continues) | Incident | continues

## Chunk 33: lines 16280-16700
PC-189 | 16280-16340 | MT047 Stage 1: Finding 1 re-derived (reporting.py zero internal fan-in — precise discriminating signal validated vs 5 control pairs; __init__ absence alone unusable); Finding 2 (35 real CLI subcommands, 3 survive); Finding 3 SHARPENED root cause: structural extractor's 'prose-found → skip' gate makes mixed code+prose sections invisible to BOTH extractors; Finding 4 (4 free-text 'candidate independently states' dispositions never revalidated; u0028 stale) | Investigation | feeds MT047 design
PC-190 | 16341-16436 | MT047 Stage 2/3: audit-to-control matrix (generation + validator defect classes); portfolio exposure: defect A no second instance found but 'undetected, not clean' (honest); B/C applicable by construction, portfolio scans deferred; Stage 4 self-review (machinery not hand-rewrite) | Analysis | honest exposure register
PC-191 | 16437-16654 | MT047 Stage 6-12 design: extract_old_readme_code_units (UNCONDITIONAL, c-namespace, sub-unit splitting); code-example-dispositions.json; 3 trio hard gates + check_code_example_api_coverage_survives (hard; fingerprint half-survival) + check_cli_category_representation (heuristic) + _module_internal_fan_in + check_api_reference_class_internal_only (heuristic) + data/api_reference_class_exclusions.json (font 3 entries) + free-text evidence revalidation extension; Stage 8 ten regression fixtures; Stage 9 SURGICAL regen scope (not full-file); Stage 10/11 idempotency honestly split (deterministic machinery vs LLM prose); Stage 12 portfolio dry-run (deterministic layer only); deferred remediation inventory (internal-class scan ~28 products; code/CLI coverage re-audit; disposition staleness scan) | Design | CURRENT (implemented per code inventory)
PC-192 | 16655-16700 | TC-HARDEN-74..80 cards (extractor+trio, coverage-survives, fan-in detector, exclusions file, free-text extension, font regen, idempotency proof) | Taskcards | verify closure next chunk

## Chunk 34: lines 16700-17120
PC-193 | 16700-16742 | TC-HARDEN-81/82 cards + MT047 risks (fan-in detector 1-product-validated; code-example fix largest change w/ first-iteration surfaces; portfolio idempotency ≠ LLM prose reproducibility; 5 non-standard-layout Python products zero coverage; 'portfolio not claimed clean') | Taskcards + risks | honest limits register
PC-194 | 16743-16921 | MT047 CLOSED 2026-08-15 (TC-74..82): extractor real (40 units font; c0017a-r previously-invisible block); coverage-survives + cli-category checks; fan-in detector real; exclusions file created (3 entries); free-text evidence extension (real precision work — quoted-phrase primary signal after 2 live false positives); font regen surgical (3 rows removed, 6 subsections restored, all source-verified); isolation + idempotency proofs w/ real hashes; portfolio dry run 60/60 combos idempotent, 1,378 code units extracted, 58 no-dispositions findings deferred-vacuous; adversarial review found 2 real defects (title-case With/From; u0006/u0028 disposition corrections); 664 scoped tests; NOT DONE (7 items): internal-only check not portfolio-run (perf), 29 products' code dispositions unauthored, font default-tree still defective, 10 heuristic findings uninvestigated, 18 units excluded, skill doc stale (83 vs 92), fan-in Python-first | Execution result | CLOSED; several deferred items
PC-195 | 16922-17120 | Thirty-Eighth incident MT048 (2026-08-15, note/python, executed): 4 prior-turn findings re-verified + 3 self-discovered (namespace-glob bug in _find_top_level_init_exports — 2-level PEP420 layouts; finding message promised non-existent suppression param; exclusions-file binary semantic conflict — tried, broke, REVERTED honestly); Finding 3 → unit_id position-drift closed for good via NEW HARD GATE check_content_unit_excerpt_matches_extraction; STAGE 3 HEADLINE: portfolio dry run BOTH trees — only 2 of 30 products clean; note/python default tree 107/148 drifted; ~28 products real nonzero drift = SINGLE LARGEST DEFERRED-REMEDIATION ITEM | Incident + Execution | KEY OPEN ITEM: portfolio-wide disposition drift (TC-MICRO-02 per state agent)

## Chunk 35: lines 17120-17540
PC-196 | 17120-17456 | MT048 Stages 5-13 + closure: 4 machinery fixes implemented (_class_has_exported_subclass_in_same_file, _find_top_level_init_exports 2-level glob union, check_content_unit_excerpt_matches_extraction NEW HARD GATE — reuses stored excerpt as fingerprint, no schema migration; exclusions param wired); NOT done: note/python 2 internal classes NOT added to exclusions (binary semantic conflict, reverted — deferred schema design: disposition remove|keep_disclosed); 13 tests (677); Stage 9 verification-only (0 bytes changed, 0/93 gates); idempotency real hashes; Stage 12 dry run 60/60 idempotent, 58/60 combos REAL findings; Stage 13 adversarial (3 findings resolved incl. revert-as-repair-loop); Deferred inventory 1-5 (portfolio drift = largest open body of work; tree canonicity; exclusions schema; internal-only not portfolio-run; 2 classes unsuppressed by design); TC-HARDEN-83..90 all closed | Execution result | CLOSED; carries LARGEST open item: portfolio disposition-drift remediation
PC-197 | 17457-17540 | Thirty-Ninth incident MT049 (2026-08-15, executed): compound multi-sentence excerpt silently drops bundled facts past merged_into_target_section (u0020 3-fact bundle; u0024 wrongly excluded); root cause 'any token anywhere' test; fix: _split_excerpt_into_sentence_groups + per-group token ownership (design iteration 1 REJECTED via live sweep — 3 real false positives from unconditional newline split; iteration 2 terminal-punctuation rule shipped) | Incident + fix | continues

## Chunk 36: lines 17540-17960
PC-198 | 17540-17678 | MT049 completion: e.g./i.e./etc. lookbehind guard (3rd false-positive class); 4 real-data regression tests; 681 tests; sibling code-path audit; portfolio sweep 60 pairs → 39 flagged entries across 8 products (pdf/go 23 = DIFFERENT shape, needs triage — dense single-feature bullets vs multi-fact bundles; honest confidence tiers); deferred: 39 entries unfixed (detection-only), pdf/go triage, word-overlap fallback untouched, tree ambiguity; TC-HARDEN-91..94 closed | Execution result | CLOSED; open: 39-entry triage/fix esp. pdf/go
PC-199 | 17679-17920 | Fortieth incident MT050 (2026-08-16, executed): html/python Installation regressed to forensic narration (exact broken/correct build-backend strings) — Installation/Quick Start EXCLUDED from leak check by design + narration check advisory-only → ZERO hard-gate protection; fix: check_no_upstream_issue_leaked_into_install_or_quickstart (2 concurring fingerprints AND narrow narration-signal list; 'at any source' deliberately not matched); REAL shared-code bug found: fingerprint extraction desyncs on nested fenced code in upstream-issues.md (fixed by stripping fences); 9 tests; SCOPED SUITE BASELINE NON-DETERMINISTIC pre-fix (177 vs 37 failures across 2 runs of same code — ST-021 hazard documented); post-change 690/690 twice; git stash process deviation DISCLOSED; portfolio sweep 63 pairs 0 fires + manual grep 1 cleared false alarm; TC-HARDEN-95..98 closed | Incident + Execution | CLOSED
PC-200 | 17921-17960 | Forty-First incident MT051 (2026-08-16, design-only Plan Mode, page/python): (1) 3 Example Results screenshots silently re-dropped in later regen behind fabricated 'no image-gallery section' excuse; (2) real create-from-scratch claim verified true but undiagrammed (product never run through hybrid-archetype evaluation); 2 parallel Explore agents | Incident | continues

## Chunk 37: lines 17960-18380
PC-201 | 17960-18220 | MT051 findings: (1) images regression CONFIRMED — regen-full re-dropped 3 restored screenshots w/ fabricated identical excluded_reason ('no image-gallery section') contradicted by 2 live counter-examples; repo-presenter tree correct; pdf/go parallel regression found (Feature Showcase demoted); (2) from-scratch claim TRUE (source-verified create()/PsCanvas round trip); diagram gap = missing archetype evaluation (page/python never run through hybrid test; absence silently defaults transform); root causes: 6th recurrence of 'correct once, never durable'; no mechanism validates excluded_reason factual claims; archetype table one-time hand-reviewed; fixes 1-4 (restore images; skill-doc rule; check_image_content_unit_excluded_reason_verified heuristic; formal archetype evaluation) | Incident + Design | CURRENT
PC-202 | 18220-18280 | TC-HARDEN-99..104; TC-HARDEN-102 CLOSED 2026-08-17 (pdf/go Feature Showcase restored w/ real bundled-fact recovery caught by MT049's own check; Feature Showcase added to target sections; 752 tests) | Taskcards | CLOSED
PC-203 | 18281-18350 | Same-session follow-up 2026-08-17: font/python 3 images restored in repo-presenter tree (wrong return-type claim caught+corrected); repo-presenter font/python missing Dependencies fixed by verbatim reuse; regen-full images already present — only bookkeeping stale; page/python leak pointer reworded (2 iterations vs real check); 2 MORE machinery bugs: _bulleted_dependency_names false-positives on version tokens (3 products), .NET extractor never scanned test-project csproj for dev deps (all 6 .NET products silently empty development bucket); 757/757 tests; NOT committed | Execution result | CLOSED (2026-08-17 follow-up)
PC-204 | 18351-18380 | TC-HARDEN-103/104 cards + MT051 CLOSED 2026-08-16 all 6 taskcards | Closure | CLOSED

## Chunk 38: lines 18380-18800
PC-205 | 18380-18494 | MT051 execution detail: TC-101 heuristic (698 tests); TC-99 restoration (mischaracterized structural-disposition gap corrected — absence is correct by design); TC-100 skill doc fn count 91; TC-103 hybrid evaluation page/python (evidence-cited entry, diagram redrawn 2-line SP + from-scratch capability node; real regression caught: bare 'PS' token 1-of-3 corroboration — reverted to parenthetical convention; 10 diagram checks 0 findings); TC-104 sweep 60 pairs: 1 additional finding font/python u0022/24/26 — HONEST disclosed editorial exclusions (different from fabricated shape) but images genuinely missing — deferred; pre-existing no_upstream_issue_leaked hard-gate finding on page/python disclosed out-of-scope | Execution result | CLOSED
PC-206 | 18495-18536 | MT051 follow-up: live-execution proof of from-scratch claims (mt051_prove_from_scratch.py; 23 checks 23 PASS; PS/EPS/XPS round trips + to_pdf conversions; showpage discrepancy investigated = correct product behavior, test assertion corrected; pypdf cross-verify deliberately not done) | Execution proof | CLOSED
PC-207 | 18537-18800 | Forty-Third incident MT052 (2026-08-18, design Plan Mode): pdf/go 'nearly complete' REJECTED by user; 3 blind agents + direct re-verification; 6 CONFIRMED content gaps (JavaScript() methods, SetOpenAction family, RTL/Bidi/Arabic, DeletePages, AddBlankPage/InsertBlankPage — excluded_reasons independently confirmed FALSE, MarkdownToDocument Starting Point); confirmed false positives catalog; section_job_distinctness real (intro duplicates 652/652 + AI-copilot list vs 13-sibling norm); ROOT CAUSE: 2 defects in check_content_unit_merged_into_target_section: (A) group match accepts weakest token (bare 'JavaScript'/'TextStyle' matching unrelated text; semicolon-joined compounds never split), (B) empty-salient_tokens word-overlap fallback has no genericness floor (silently passes identifier-free bullets); fix design: semicolon+backtick split extension, compound-token preference rule, check_content_unit_redundant_claim_verifiable heuristic, retroactive pdf/go fix (6 gaps), portfolio sweep | Incident + Design | continues

## Chunk 39: lines 18800-19220
PC-208 | 18800-18880 | MT052 validation controls + TC-HARDEN-105..110 cards | Design | —
PC-209 | 18879-19020 | MT052 EXECUTION 2026-08-18 (first pass): TC-105/106/107 CLOSED (semicolon split; compound-token preference w/ 2 real refinements — numeric-dotted exclusion + trailing-segment promotion rule + paren-suffix tolerance; redundant-claim heuristic +'blank' stopword); 732 scoped tests; TC-108 PARTIAL: 3 original gaps + Delete/Blank pages fixed; Markdown Starting Point ATTEMPTED-REVERTED (2-node hybrid rule + fixed literal purity exemption — needs separate design pass); corrected gate surfaced 32/60 combos w/ 119+54 findings portfolio-wide; pdf/go itself 33 findings remain (3 shapes: paren-formatting closed; possibly-wrong-signature dispositions; genuinely unwritten); TC-109 NOT DONE; TC-110 sweep run report-only | Execution result | PARTIAL at this point
PC-210 | 19021-19212 | MT052 Phase 2 (2026-08-18): user rejected partial closure; MISDIAGNOSIS RETRACTED (u0096 etc. tokens live in 'Mirrors Aspose.PDF for .NET's X' clauses — accurate about .NET SDK; mirrors-clause exemption is the fix); Gap 1 RESOLVED AS NO-CHANGE (Markdown = from-scratch path already covered by i2 semantics; 3 alternatives evaluated and rejected with evidence); Gap 2 RESOLVED: full 59-heading audit (3 real gaps: Image-to-PDF, Replace/Remove Images, Linearizing — all excluded_reasons false; 2 thin items); Gap 3: 24/33 units investigated — Category A token fixes (4), Category B content additions (19+2 new units, drafted source-verified text), Category C false self-referential claims (u0049/51/59/128); execution plan 1-7 (closing bar = genuinely 0 findings); TC-HARDEN-111..114 | Investigation + Design | Phase 2 register

## Chunk 40: lines 19220-19640
PC-211 | 19220-19368 | MT052 final execution (2026-08-18): TC-105 mirrors-clause exemption CLOSED (33→25 findings); TC-106 trailing-segment paren fix CLOSED (25→23); TC-107 CLOSED (no new code needed); TC-108 FULL closure (all 23 remaining findings fixed w/ source-verified content across Key Capabilities/Feature Showcase/API-ref intro/table rows/Detailed Member Ref/Scope/License; malformed mega-tokens removed; Category C false self-referential claims corrected); TC-109 CLOSED (3 heading gaps closed; c0053/c0054 code-unit false excluded_reasons corrected — hand-authored u0133/u0134 attempt correctly rejected by coverage gate and reverted); TC-110 portfolio sweep DEFERRED disclosed; final verification: 0 findings both checks (was 33); 0 hard-gate failures full battery; idempotent; isolation via Edit-tool + post-hoc heading scan (no pre-edit snapshot — disclosed process gap); TC-111..114 CLOSED folded; 738 scoped tests | Execution result | MT052 CLOSED; TC-110 sweep deferred
PC-212 | 19369-19404 | MT052 follow-up pdf/net + pdf/java recheck (2026-08-18): pdf/net 2 disposition-only fixes (compound token unmatchable; self-referential pointer scoped); pdf/java 0 failures first run; manual reads confirmed coverage | Execution result | CLOSED
PC-213 | 19406-19638 | Forty-Fourth incident MT053 (2026-08-18, design): pdf/cpp 158 false hard-gate failures — candidate ALREADY PUSHED+MERGED upstream → old README == candidate (byte-identical); preservation machinery compares candidate against itself + Navigation TOC shifted all unit_ids; portfolio scan: exactly 2 products in this state (pdf/cpp, words/net); interrupted hand-rewrite of disposition files DISCLOSED (no backup; harmless once mechanism lands but procedurally regrettable); fix: _readme_matches_published_upstream (strict whitespace-only normalization; false-negative-safe), 25 preservation keys → uniform disclosed skip {skipped:True}, readme_already_published result key, audit-portfolio published field, disposition files become inert historical record; honest limits: published-then-locally-edited state (cells/go, cells/java, cells/net, 3d/java, 3d/typescript — later local work moved past live) NOT solved — deferred harder problem; freshness = existing source-verification checks, no new check needed; words/net not yet individually verified | Incident + Design | CURRENT (implemented per code inventory); OPEN: published-then-edited design, words/net verification

## Chunk 41: lines 19640-20060
PC-214 | 19640-19726 | MT053 CLOSED 2026-08-18 (TC-HARDEN-115..118): _readme_matches_published_upstream implemented; real UnboundLocalError bug found+fixed on first exercise (dependency_disposition_reconciliation reads outside block); 9 tests (747); LIVE PROOF: pdf/cpp 158→1 (remaining = by-design hybrid freshness), words/net published:True 0 failures; audit-portfolio published field + CLI summary; skill-doc note synced; NOT DONE: published-then-edited state (5 products) unsolved; pdf/cpp disposition files left in rewritten state; no 3rd-product sweep | Execution result | CLOSED
PC-215 | 19728-19822 | MT055 Micro-Taskcard Hardening Pass (2026-08-18): mode-boundary reconciliation (46-file template folded into plan single-authority; scratch evidence at reports/_scratch/mt055_* on execution); 118 closed taskcards NOT re-taskcardized (preservation rule); §1 authority verdict (main 4 ahead of origin; 6 files staged-uncommitted from MT041-053; sole plan authority confirmed); §2 COMPLETE OPEN-ITEM REGISTER (W1-W6): W1 path machinery (RC-H hardcoded repo-presenter — TC-MICRO-01; CH-10 canonical tree — TC-MICRO-03; durability TC-17 backlog), W2 disposition drift (~58/60 MT048 + 32/60 MT052 — TC-MICRO-02; font 3 images P2; pdf/cpp files P3), W3 validator gaps (CH-03 self-citation — TC-MICRO-04; CH-05 merged_verbatim lint; internal_only portfolio run), W4 verify runners (6 langs) + live CLI push (TC-10), W5 published-then-edited 5 products, W6 pdf/cpp 182 filler + scratch-script retirement | Register (FINAL OPEN BACKLOG) | AUTHORITATIVE open-items list as of 2026-08-18
PC-216 | 19824-20060 | TC-MICRO-01 full Parent+Child decomposition (fix 6 hardcoded path fns; design→implement→regression-verify; audit-portfolio no-mirror baseline match required) | Taskcards (open; NOTE: state agent reports TC-MICRO-01 already implemented in uncommitted working tree) | READY/IN PROGRESS

## Chunk 42 (FINAL): lines 20060-20903 (EOF)
PC-217 | 20064-20239 | TC-MICRO-02 full decomposition (drift remediation: re-scan → triage RC-A..H → family waves → final re-verification; one product per micro-step group; 0-findings closeout bar) | Taskcards | OPEN P0 — largest open body of work
PC-218 | 20243-20334 | TC-MICRO-03 decomposition (canonical tree; human gate; 03-03 blocked until decision) | Taskcards | see PC-221 — executed later same day
PC-219 | 20338-20448 | TC-MICRO-04 decomposition (self-citation rejection; report-only sweep folded into W2) | Taskcards | CLOSED same day (PC-220)
PC-220 | 20452-20707 | MT055 §4-11: state-model mapping; DAG; validation matrix; evidence contract; quality scoring; reconciliation self-audit; execution handoff; EXECUTION RECORD: TC-MICRO-01 CLOSED 2026-08-18 (candidate_tree_name config param — sharper design than either original option; 751 tests; real-content no-mirror proof matches baselines); TC-MICRO-04 CLOSED (self-citation check + reject_self_citation flag after 21-failure regression — structural/code-example call sites legitimately self-cite; 756 tests; sweep: 13 combos, pdf/net regen-full 58 units; folded into W2); TC-MICRO-03-01/02 CLOSED (16/30 one-directional Dependencies evidence; USER DECISION: promote repo-presenter-regen-full to DEFAULT; retire repo-presenter deferred), 03-03 IN PROGRESS (default flipped in code; 2 test-fixture regressions fixed; 757 tests; audit-portfolio confirmation pending) | Execution record | TC-MICRO-01/04 CLOSED; 03 mostly done; 02 OPEN
PC-221 | 20711-20903 | Fifty-Sixth incident MT056 (2026-08-18, SECOND PARALLEL SESSION, design + concurrency disclosure): scoped convergent idempotency mission; forensics: TC-HARDEN-47/48 (republish 3d/net + 3d/python — live clipping STILL LIVE on GitHub) were LOST from register — RESTORED as open P0; label-geometry gap (267 labels >40 chars); split-brain store quantified (22 dirs, 97 copies; push would ship tree 1 content); canonical decision SUPERSEDED IN-FLIGHT — adopted MT055's code-first regen-full default; mechanical promotions + NEEDS_REVIEW flags; design: data/readme_candidate_store.json + check_candidate_store_integrity + declare-scope/change-scopes + acceptance-registry (block content hashes; CONVERGED/FROZEN states) + check_diagram_label_geometry (hard) + check_published_readme_current (staleness tripwire) + non-regression fixtures; TC-M56-01..08 ALL READY (NOT YET EXECUTED — execution record EMPTY at EOF); R-19: memory claim 'push still opens draft PRs' UNSUPPORTED by plan record | Incident + Design (open) | OPEN: TC-M56-01..08; TC-HARDEN-47/48 restored open P0

# COVERAGE COMPLETE: lines 1-20903 read sequentially, zero unexplained gaps. Live file GREW during audit: 20,634 L (sha 953fbfd1..., 20:34) → 20,903 L (sha 8f5fb4fe..., 21:03) — growth = MT056 section, fully read.

## Chunk 43 (post-audit re-pin): lines ~20690–20757 of the 20,953-line version (+50-line growth event 4)
PC-222 | ~20690-20757 | MT055 addendum (appended after this audit's 21:03 pin): TC-MICRO-03-03 completion — first bare-configure() audit-portfolio run on the new default tree: 7/30 ALL HARD GATES CLEAR, 14 products detected published, per-product findings cross-checked against known baselines (pdf/net's 58 = TC-MICRO-04's own disclosed self-citation findings, not a regression); baseline captured at reports/_scratch/mt055_audit_portfolio_baseline_20260818.txt explicitly as TC-MICRO-02-01's required re-scan; words/net transient 1-finding anomaly investigated, not reproducible, disclosed unresolved; TC-MICRO-02 deliberately NOT started during the live concurrency window; final integrity re-check: run.py diff grew 530→912 lines from a concurrent agent (the MT056 code-landing wave, incl. the F-01 --draft removal), ast.parse clean, session markers intact, 757 scoped tests green — no corruption | Execution record (MT055) | CURRENT; TC-MICRO-02 re-scan artifact now exists

# RE-PIN COMPLETE: lines 1–20,953 covered (sha256 09290ac0ef23237642e6cc9ffb013e34266f78eec48b3fd6a2fad7dda1051e3e). MT056 §6 execution record still empty in the plan at this pin, while its code verifiably landed at 21:19 — the one known doc-lags-code gap at close of audit.
