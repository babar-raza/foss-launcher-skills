# `/readme-refresh` — Current Operational Reference

> **Role**: current-truth orientation for people and LLM agents. This file describes what the
> system supports **today** and how to work with it safely. It is **not** a state machine and
> holds no execution status — live status is in `reports/readme_refresh_runs/` and per-product
> `ACTIVE.json`; actionable work is in the plan's own open taskcards. History, evidence, and every
> superseded decision live in
> [plan-system-forensic-reconciliation.md](plan-system-forensic-reconciliation.md) (the forensic
> report) and the original plan file it audits.
>
> **Snapshot date: 2026-08-18 ~21:25 local** (working tree; MT041–MT056 changes uncommitted;
> MT056's code substantially landed at 21:19 — scope enforcement, acceptance registry,
> label-geometry hard gate, draft-flag removal — while its plan execution record was still empty).
> Re-run the [Consistency check](#consistency-check) before trusting this file in a later session.

---

## 1. Purpose and scope

`/readme-refresh` (skill **S-120**) generates, verifies, and — on explicit human approval — pushes
a production-grade `README.md` refresh for **one Aspose FOSS product repository at a time**, via a
registered, run-bound state machine. It owns the README plus community-health *files* that ride in
the same PR (SECURITY.md/CONTRIBUTING.md proposals).

It does **not**: edit repo *settings* (description/topics/homepage/org profile/icon — that is the
never-built `/repo-presenter-metadata` design), touch this repo's `content/` sites, run on a
schedule, merge without a per-PR human go-ahead, or write to any knowledge/`data` registry it
consumes (all read-only, exceptions listed in §4).

## 2. Current architecture (active execution path)

```
data/products.json ──► start (preflight: registry, exclusions, family registered, gh permissions,
                              clone-cache HEAD pinned)
                └──► plan  (factpack: ~20 verified _detect_* fields + old-README inventories:
                            content/structural/code/badge units)
Agent composes candidate ──► reports/repo-presenter-regen-full/{family}/{platform}/readme.md
        + sibling dispositions (content / structure / badge / code-example) + upstream-issues.md
                └──► ingest-candidate  (~101 deterministic result keys; ~64 hard gates block)
                └──► recheck           (re-run after edits; --allowed-headings / --mermaid-only
                                        change-isolation gates vs rolling snapshot)
                └──► verify-examples   (real Python runner via --python-runner; other languages
                                        honest BLOCKED-WITH-REASON stubs)
                └──► AWAITING_REVIEW → approve --note (human gate; input drift forces re-plan)
                └──► push [--dry-run]  (disposable clone → surgical README-only diff →
                                        commit-tree plumbing → token push → gh pr create)
                └──► human reviews PR → agent merges on explicit go-ahead:
                     gh pr merge N --squash --delete-branch --subject … --body …
                     (body = real commit message + exactly ONE Co-authored-by: <acting model>)
                └──► verify (post-push) · clone cache fast-forwarded after merge
```

States: `CREATED → INPUTS_PINNED → PLANNED → VERIFYING_EXAMPLES → AWAITING_REVIEW → APPROVED →
PUSHING → PUSHED`; rework `AWAITING_REVIEW/APPROVED → PLANNED`; `PUSHING → APPROVED` (dry-run
return); `BLOCKED` re-enterable from INPUTS_PINNED/PLANNED/VERIFYING_EXAMPLES/PUSHING; terminals
`PUSHED`, `ABANDONED`. There is **no template engine**: the agent writes the prose; the gates
enforce the contract.

## 3. Canonical entry points

| Action | Command |
|---|---|
| Skill gate | `skill_context.py begin --skill S-120` then follow `skills/readme-refresh.md` |
| CLI | `PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/commands/foss/readme_refresh_run.py <verb> …` |
| Verbs | `start FAMILY PLATFORM [--skip-preflight]` · `plan` · `ingest-candidate` · `recheck [--allowed-headings …] [--mermaid-only]` · `verify-examples [--python-runner]` · `status [--json]` · `approve --note …` · `push [--dry-run]` · `verify` · `abandon --reason …` · `recover --reason …` — all `--run-id` bound; plus `audit-portfolio [--family F --platform P] [--json]` (read-only, portfolio-wide, per-product `published` flag) |
| Scoped tests (never the full suite) | `pytest scripts/pipeline/tests/test_readme_refresh_checks.py scripts/pipeline/tests/test_readme_refresh_run.py scripts/pipeline/tests/test_dependency_extract.py -q` (795 tests, ~2.5 min) |
| Commits in this repo | **only** `scripts/pipeline/commands/ops/git_plumb_commit.py` (isolated temp index) — never plain `git commit`; never `git reset`/`git stash` (ST-021) |

## 4. Authoritative data

- **Candidate store (canonical, decided 2026-08-18)**:
  `reports/repo-presenter-regen-full/{family}/{platform}/` — `readme.md`, `upstream-issues.md`
  (local-only, **never pushed**), `content-dispositions.json`, `structure-dispositions.json`,
  `badge-dispositions.json`, `code-example-dispositions.json`, (pilot) `acceptance-registry.json`.
  `reports/repo-presenter/` is the **frozen historical tree** (readable via
  `configure(candidate_tree_name="repo-presenter")`; retirement/reconciliation pending).
  Store record: `data/readme_candidate_store.json` (MT056).
- **Run evidence**: `reports/readme_refresh_runs/{f}/{p}/{run_id}/` (`manifest.json`,
  `events.jsonl`, `facts/factpack.json`, `checks/result.json`, `checks/last_checked_candidate.md`,
  `verification/result.json`, `push/receipt.json`); locks `reports/locks/readme_refresh/`.
- **External-action ledger**: `reports/repo_presenter_actions.jsonl` (one row per push; started
  2026-08-15, earlier manual pushes deliberately not backfilled).
- **Read-only inputs**: `data/products.json` (31) · `data/registry_exclusions.json` ·
  `data/package_registry.json` (known imperfect — heuristic posture) ·
  `data/aspose_com_targets.json` + `data/backlinks/platform_canonical_overrides.yaml` ·
  `data/format_descriptions.json` · `data/families.json` · `keywords/{family}.json` (known
  cross-platform-contaminated; filtered) · `knowledge/{f}/{p}/merged/*`
  (`formats.md` known imperfect → 2-of-3 corroboration) ·
  `content/reference.aspose.org/en/{f}/{p}/*` · clone cache `runs/.clone_cache/aspose_{f}_{p}/`
  (never written; fast-forwarded only after a real merge).
- **Written by this skill (narrow)**: `data/diagram_archetypes.json` (evidence-cited archetype
  rows; hybrid `decided_at` must be re-verified fresh, never blind-bumped),
  `data/api_reference_class_exclusions.json`, `data/dependency_overrides.json`,
  `data/readme_candidate_store.json`.

## 5. Current invariants (every regeneration must obey)

1. Every factual claim verified against real, current source **immediately before writing** — for
   inclusion *and* for dropping. "The old README said so" is never evidence. Fabricated API
   surface is the worst defect class.
2. Section isolation: an edit touches only its declared sections
   (`check_only_sections_changed` / `--mermaid-only`); deterministic machinery must be idempotent
   (same input → byte-identical output, proven by running twice). Free LLM prose is **not**
   promised byte-reproducible — only structural properties are.
3. Old-README accounting: every content/structural/badge/code unit gets an explicit disposition
   (merged/corrected/excluded-with-true-reason). Excuses must be factually true ("no template
   section exists" is never valid for screenshots). Published products
   (candidate == live upstream README) skip all 25 preservation keys with a disclosed
   `skipped: True` — never hand-edit dispositions to simulate this.
4. Diagram: flat `StartingPoints? → PRODUCT → Capabilities → Outputs`; no per-node edges; no
   custom styling; Starting Points required for transform/compile, forbidden for generative,
   exactly-2-line for hybrid (fresh source re-verification each time); containers format-pure;
   every format claim 2-of-3 corroborated; ≤28-char tokens (label-geometry hard gate landing).
5. Prose hygiene: no process/audit narration; no generation-mechanism narration ("the table below
   mirrors…"); no internal artifact names (`upstream-issues.md`, `content-dispositions.json`,
   `.clone_cache`, `reports/…`); upstream defects appear only as non-forensic pointer sentences
   and only when stated in an approved public source of the target product; License section =
   fixed MIT template (linked/unlinked); headings Title Case (glTF exception).
6. Links: Enterprise link exactly once, in Scope and Limitations' closing paragraph (separate
   paragraph, never inside a bullet), anchor = `Aspose.{Family} for {Public Platform} — Enterprise
   Edition` (family-neutral only when no platform page exists), URL from the resolved target map —
   **never expose implementation bridges anywhere** ("via Java/C++/.NET", wrapper/binding/backed-by).
   Never link `forum.aspose.com` or any `*.aspose.app`. Documentation & Resources links only when
   the local `content/...\_index.md` exists. Banner = linked form
   `[![alt](banner-readme.png)](verified homepage)`.
7. Badges: License badge + at least one more verified category when available; reconcile against
   old badges by category+target, never label text.
8. `## Dependencies` is a required section (after Installation): real manifest-extracted data;
   verified-zero renders the fixed "No required third-party package dependencies." sentence;
   unqualified "dependency-free / no external runtime" claims are hard-blocked.
9. Merge procedure: non-draft PR, 3-section body (Summary / What changed / Verification), agent
   squash-merges only on an explicit per-PR go-ahead **with explicit `--subject`/`--body`** carrying
   exactly one `Co-authored-by: <real acting model>` trailer.
10. Never claim beyond the gate: heuristic silence ≠ verified; a passing gate proves only its
    narrow claim; date-stamp any "N/30 clean" statement (certifications decay).

## 6. Candidate lifecycle (discovery → publication)

1. **Freshness**: `start` pins clone-cache HEAD; stale knowledge → run the
   `repo-scout → knowledge-enrich → truth-merge` chain first (hard prerequisite for new products —
   the 2-of-3 format gate arithmetically blocks without it).
2. **Facts**: `plan` writes the factpack (never recomputed by the agent by hand).
3. **Composition**: agent writes candidate + dispositions per skill-doc contract; reads 2–3
   contamination-checked sibling candidates for tone; omit a framing sentence rather than invent.
4. **Gating**: `ingest-candidate` (hard gates block) → fix → `recheck` (isolation gates).
5. **Verification**: `verify-examples` (Python real; others named stubs — BLOCKED-WITH-REASON
   must be listed by name to the reviewer, never silently shipped).
6. **Review**: human reviews the bundle; tweaks → `recheck`; the skill never self-approves.
7. **Publication**: `approve` → `push --dry-run` rehearsal → live `push` (fresh authorization) →
   human PR review → agent squash-merge per invariant 9 → `verify` → clone cache fast-forward →
   ledger row. For a regenerated candidate where one exists: the Regeneration Comparison Protocol
   (structural/factual/wording classes, every factual disagreement source-verified both ways) —
   never silent replacement.

## 7. Surgical improvement model

To improve one area only: `declare` the scope (MT056 change-scope machinery as it lands; today:
`recheck --allowed-headings "A,B"` / `--mermaid-only` against the rolling snapshot) → edit only
those blocks → prove isolation (zero diffs outside the allowed set) → re-run the battery →
idempotency (second run byte-identical). Accepted/converged blocks (acceptance registry, MT056)
may not change without a new authorizing scope; source-change invalidation reopens them explicitly.

## 8. Platform and product variation

- **Global**: everything in §5.
- **Archetype-driven** (`data/diagram_archetypes.json`; absence = `transform`): current overrides —
  `barcode/python` generative, `tex/python` compile, `pdf/cpp` + `pdf/go` + `page/python` hybrid.
- **Platform-specific**: install sourcing per registry (`package_registry.json` first, then live
  checks; C++ is NOT registry-less — cells/cpp ships NuGet); Go uses module path + `pkg.go.dev`
  badge (`language_package_reference`, not `package_version`); Python bridge slugs
  (`python-net`/`python-java`) normalize to public "Python" in anchors.
- **Product-specific overrides (all evidence-required)**: `registry_exclusions.json`
  (cells/typescript excluded from site-launch; its repo README was still refreshed under explicit
  user authorization), `api_reference_class_exclusions.json` (font/python ×3),
  `dependency_overrides.json`, `3d/typescript`'s class-heading reference convention (parser
  fallback handles it).

## 9. Validation and evidence (what proves a candidate acceptable)

- `checks/result.json`: 0 hard-gate findings (~64 keys); advisory findings individually triaged,
  never bulk-dismissed.
- `verification/result.json`: every block `COMPILED+RAN CLEAN` / `FIXED-THEN-PASSED`, or
  `BLOCKED-WITH-REASON` explicitly accepted by the reviewer by name.
- Isolation + idempotency proofs (per §5.2) recorded in the run evidence.
- Dispositions complete and drift-clean (`content_unit_excerpt_matches_extraction` etc.).
- `dependency-verification-matrix.json` for reviewer inspection (non-gating).
- Scoped test suite green (795 as of 2026-08-18) before any code commit.
- `audit-portfolio` for portfolio claims — freshly run, date-stamped.

## 10. Resume and recovery

- `status --run-id … --json` = current state. One active run per product (`ACTIVE.json` + lock).
- `BLOCKED` → fix the named cause → `recover --reason …` re-enters `resume_state` → repeat the verb.
- Input drift at `approve` forces back to `PLANNED` (by design).
- Interrupted `PUSHING`: re-run `push` — steps are idempotent (existing branch/PR detected).
- Abandon (`abandon --reason …`) to release a product lock after a proof/verification run; keep
  the evidence tree.
- Do not trust the shared git index (ST-021): before any commit, diff working-tree-vs-HEAD and
  staged-vs-HEAD separately; commit only via `git_plumb_commit.py`.

## 11. Current pending and deferred work (genuine open items only)

Full detail: forensic report §8/§10 and the plan's MT055 §2 register + MT056 §5.

| ID | Item | Status |
|---|---|---|
| TC-MICRO-02 | Portfolio disposition-drift remediation (~58/60 combos at MT048). Fresh baseline re-scan (TC-MICRO-02-01) now exists: `reports/_scratch/mt055_audit_portfolio_baseline_20260818.txt` — 7/30 all-gates-clear, 14 published, rest with findings | **Open, P0 — largest item** (deliberately not started during the 2026-08-18 concurrency window) |
| TC-HARDEN-47 / 48 | Republish `3d/net` / `3d/python` (live diagram clipping on GitHub since 2026-08-05) | **Open, P0** (needs push authorization) |
| TC-M56-01…08 | Canonical-store gates, change scopes (`declare-scope`/`accept-blocks`/`converge-verify`), acceptance registry, label-geometry hard gate, published-staleness tripwire, pilot + fixtures + evidence | **Code landed 21:19 (uncommitted, unrecorded)** — plan §6 execution record still empty; pilot/fixtures/evidence bundle status unknown at snapshot |
| F-02 | `_do_push` hardcodes `Co-Authored-By: Claude Sonnet 5` (run.py:3504) — contradicts MT032's never-hardcode rule. (F-01, the `--draft` flag, was fixed in-tree at 21:19 during the reconciliation audit) | **Open defect** |
| TC-MICRO-03 tail | Old-tree (`repo-presenter`) mechanical promotions + NEEDS_REVIEW triage + retirement | Open |
| W5 (MT053) | Published-then-locally-edited state (cells/go, cells/java, cells/net, 3d/java, 3d/typescript) needs its own design | Open (blocked on design) |
| TC-HARDEN-01 tail | Real verify-examples runners for Java/.NET/Go/Rust/C++/TS | Open, P1 (per-language missions) |
| TC-HARDEN-17 | Durability of `reports/repo-presenter*` (single machine, gitignored) | **Blocked on user policy decision** |
| TC-HARDEN-02 | `SKIP_SKILL_CONTEXT_CHECK=1` session-env bypass | Blocked on user/environment |
| Sweep backlogs | MT049 (39 entries, pdf/go triage), MT052/TC-110 (32 combos), MT055 self-citation (13 combos incl. pdf/net regen-full ×58 units) | Open, folded into TC-MICRO-02 |
| Misc deferred | code-example dispositions for ~29 products · portfolio internal-class-leak run (perf) · scratch-script retirement (TC-HARDEN-14) · registry.yaml "21 checks" description fix · pdf/cpp 182 filler descriptions (P4) · `cells/python` live Enterprise-href push · TC-HARDEN-03 DAR gate (governance-owned) · mission registration (TC-HARDEN-06, P3) · `/repo-presenter-metadata` (needs go-ahead) | Open/deferred |

## 12. Do-not-do rules

- Never plain `git commit` / `git reset` / `git stash` in this repo; plumbing commits only.
- Never write to the clone cache, `knowledge/`, or any read-only registry in §4; never hand-edit
  `data/package_registry.json`, `formats.md`, or `keywords/` to make a check pass.
- Never push/merge/open a PR, or `approve`, without a fresh, explicit, per-action user go-ahead;
  never merge with `gh pr merge` defaults (explicit `--subject`/`--body` always).
- Never push `upstream-issues.md` or any internal artifact; never name internal artifacts in
  README prose.
- Never expose implementation bridges ("via Java/C++/.NET", wrapper/binding); never link
  `forum.aspose.com` / `*.aspose.app`; never embed GitHub social-preview URLs (5-min expiry).
- Never hand-edit disposition files for a published product; never fabricate a disposition
  excuse; never blind-bump a hybrid `decided_at`.
- Never regenerate against the old wired diagram model (hard-blocked anyway); never weaken a hard
  gate to make a fixture or candidate pass — fix the content or prove the check wrong.
- Never treat heuristic silence, a stale "clean" certification, or an agent self-report as
  verification; never batch-edit multiple products in one uninspected pass.
- Never assume this file is current in a later session — run the consistency check.

## 13. Consistency check

Run these; any failure means this reference or its forensic companion is stale — re-audit before
relying on either:

```bash
# 1. Plan identity (must match forensic report §1 or trigger a refresh)
sha256sum ~/.claude/plans/d-users-prora-onedrive-documents-github-humble-tome.md
# audited: 8f5fb4fe6e7c76bc521c85b38b6c7c044e5bf80307a5b46ffb0e9ba159cd09ea (20,903 lines)

# 2. Entry points exist
ls scripts/pipeline/commands/foss/readme_refresh_run.py \
   scripts/pipeline/commands/foss/readme_refresh_checks.py \
   scripts/pipeline/commands/foss/dependency_extract.py skills/readme-refresh.md

# 3. Canonical tree constant (expected: repo-presenter-regen-full)
grep -n '_DEFAULT_CANDIDATE_TREE_NAME' scripts/pipeline/commands/foss/readme_refresh_run.py

# 4. Open-defect marker (F-02): expected present at snapshot; if absent, F-02 is fixed — update §11.
grep -n 'Co-Authored-By: Claude Sonnet 5' scripts/pipeline/commands/foss/readme_refresh_run.py
#    F-01 regression guard: this must stay EMPTY (the --draft flag was removed 2026-08-18 21:19):
grep -n '"--draft"' scripts/pipeline/commands/foss/readme_refresh_run.py

# 5. Check-function count vs doc claims (drifts upward as missions land)
grep -c '^def check_' scripts/pipeline/commands/foss/readme_refresh_checks.py   # ~98 at snapshot

# 6. Store record + canonical trees
cat data/readme_candidate_store.json 2>/dev/null
ls -d reports/repo-presenter reports/repo-presenter-regen-full
```

## 14. Historical context (one paragraph)

The system began (2026-08-02) as a manual, agent-driven 30-product README generation with a
compile-and-run verification sprint, and hardened through ~56 recorded incidents: every convention
here exists because a real defect shipped without it (fabricated API claims, dropped content,
narration leaks, dead links, diagram clipping, disposition drift, a revoked bridge-wording policy,
a skill that sat unused beside the manual process until 2026-08-11). The full evidence trail,
decision chains, supersessions, and contradiction register are in the
[forensic reconciliation](plan-system-forensic-reconciliation.md); the immutable source history is
the original plan file
(`C:\Users\prora\.claude\plans\d-users-prora-onedrive-documents-github-humble-tome.md`).
