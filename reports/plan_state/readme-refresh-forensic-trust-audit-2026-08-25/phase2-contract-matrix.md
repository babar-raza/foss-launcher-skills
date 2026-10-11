# Phase 2 — Implementation & Dependency-Closure Map / Intended-vs-Implemented Contract Matrix

Mission: `readme-refresh-forensic-trust-audit-2026-08-25`. Read-only investigation;
no files under `scripts/pipeline/commands/foss/` or any target repo were modified while
producing this document. Two load-bearing facts below were independently re-verified
live on 2026-08-25 (state machine `NEXT_STATES`/`TERMINAL_STATES` at
`readme_refresh_run.py:80-98`; `check_*` function count via
`grep -c "^def check_" readme_refresh_checks.py` = 103). The remainder is carried
forward from the Phase-1 research pass, which read every file cited below directly.

## 1. Skill surface

| File | Role |
|---|---|
| `.claude/commands/readme-refresh.md` (1301 lines) | Canonical skill doc |
| `skills/readme-refresh.md` (1298 lines) | Registered copy (`skills/registry.json` `canonical_path`), byte-identical except a boilerplate cross-skill-reference note |
| `.agents/skills/readme-refresh/SKILL.md`, `.kilocode/skills/readme-refresh/SKILL.md` | Tool-specific mirrors |
| `skills/registry.json:811-818` | `id: S-120`, `slug: readme-refresh`, `description: "Skill description pending"` (stale placeholder — AUD-P1-SKILL-DESCRIPTION-PLACEHOLDER) |
| `docs/registries/skills.md:102` | One-line portfolio index row |
| `docs/readme-refresh/current-operational-reference.md` | Independently-maintained "current truth" doc, dated snapshot 2026-08-20 — now known-stale on its headline claim (see Phase 1 baseline) |
| `docs/readme-refresh/plan-system-forensic-reconciliation.md` | Forensic reconciliation of the out-of-repo plan file vs. code, dated 2026-08-18 |
| `<local-plan-cache>/d-users-prora-onedrive-documents-github-humble-tome.md` | The actual design-rationale source (~22,036 lines) — **outside git**, no repo copy (AUD-P1-TEMPLATE-OUTSIDE-GIT) |

**There is no separate prompt-template file anywhere in the pipeline.** The "prompt" for
candidate composition *is* the skill doc itself, read directly by the composing agent,
plus the deterministic `facts/factpack.json`. `docs/readme-refresh/current-operational-reference.md:61`
states this explicitly: "There is no template engine: the agent writes the prose; the
gates enforce the contract." Candidate composition therefore has **no CLI verb** — it is
fully agentic, sitting between `plan` and `ingest-candidate` in the pipeline.

## 2. State machine (verified live, `readme_refresh_run.py:80-98`)

```
CREATED → INPUTS_PINNED → PLANNED → VERIFYING_EXAMPLES → AWAITING_REVIEW → APPROVED → PUSHING → PUSHED
AWAITING_REVIEW → PLANNED   (drift-forced replan)
APPROVED → PLANNED          (drift-forced replan)
PUSHING → APPROVED          (dry-run rehearsal return — exercises the same disposable-clone/
                              branch/commit mechanics as a real push without actually pushing)
BLOCKED re-enterable from: INPUTS_PINNED, PLANNED, VERIFYING_EXAMPLES, PUSHING
Terminal: PUSHED, ABANDONED
```

Every transition goes through `_transition()` (line 794) or `_transition_abandoned()`
(806) — both validate against `NEXT_STATES`, write `manifest.json`, and append a
`STATE_TRANSITION` row to `events.jsonl`.

## 3. Stage-by-stage table

| Stage / CLI verb | Owning code | Inputs | Outputs | Det./Agentic | Validators | Failure behavior |
|---|---|---|---|---|---|---|
| `start` (CREATED→INPUTS_PINNED) | `start_run` 954-1029; `_resolve_product` 880-901; `_preflight_access_check` 904-925; `_check_family_registered` 928-951 | `data/products.json`, `data/registry_exclusions.json`, `data/families.json`, live `gh api repos/{org}/{repo}`, clone-cache HEAD | `reports/readme_refresh_runs/{f}/{p}/{run_id}/{manifest.json, ACTIVE.json, events.jsonl}` | Deterministic | Product active + not excluded; family registered; real push/admin access; canonical-tree check (`_require_canonical_tree`, 293-309) | Raises before anything is written |
| `plan` (INPUTS_PINNED→PLANNED) | `plan_run` 1837-1941 + ~15 `_detect_*` helpers 1034-1834 | `data/diagram_archetypes.json`, `data/diagram_capability_dependencies.json`, `data/format_descriptions.json`, `data/package_registry.json`, `data/backlinks/platform_canonical_overrides.yaml`, `data/aspose_com_targets.json`, `keywords/{family}.json`, `knowledge/{f}/{p}/merged/*`, `content/reference.aspose.org/.../_index.md`, `content/products.aspose.org/.../_index.md`, clone cache, `dependency_extract.extract_dependencies` | `reports/readme_refresh_runs/{f}/{p}/{run_id}/facts/factpack.json` | Deterministic — **never writes prose** | Dependency extraction fail-closed (`DependencyExtractionError`) | Transitions to `BLOCKED` with a named reason, recoverable via `recover` |
| *Candidate composition* (no CLI verb) | Agent-authored | `factpack.json` + skill-doc prose rules | `reports/repo-presenter-regen-full/{f}/{p}/{readme.md, content-dispositions.json, structure-dispositions.json, badge-dispositions.json, code-example-dispositions.json, upstream-issues.md}` | **Fully agentic** — script never writes README prose (module docstring 25-28) | None at write time | N/A |
| `ingest-candidate` (PLANNED→VERIFYING_EXAMPLES) | `ingest_candidate` 1947-1993; `_run_deterministic_checks` 1995-2868 (876 lines); `_apply_scope_enforcement` 477-556 | `readme.md` + disposition JSON + clone cache | `checks/result.json`, `checks/last_checked_candidate.md`, `reports/repo-presenter-regen-full/{f}/{p}/last-verified.json` | Deterministic | 103 `check_*` functions (~65 hard-gate, ~43 advisory; conditional branching means not every check fires on every candidate) | Hard-gate failure raises before transition; `result.json` written first so failures are always inspectable |
| `recheck` (no transition) | `recheck` 3055-3093; `_apply_change_isolation_checks` 3014-3047 | Same battery + `--allowed-headings`/`--mermaid-only` diff | Overwrites `result.json` + snapshot | Deterministic | Same battery + change-isolation checks (hard, only when scope declared) | Never raises — human-in-the-loop, caller inspects JSON |
| `verify-examples` (VERIFYING_EXAMPLES→AWAITING_REVIEW) | `verify_examples` 3519-3556; default stub `_default_verification_runner` 3376-3391; real runner `python_verification_runner` 3474-3516 | Candidate + factpack | `verification/result.json`, `upstream-issues.md` | **Stub by default** for every language; opt-in `--python-runner` really builds a venv and executes Python-tagged blocks only | `all_named` must be true | Raises if any block has no named status |
| `approve` (AWAITING_REVIEW→APPROVED, human-gated) | `approve` 3562-3595 | Manifest, live clone-cache HEAD vs. pinned | `manifest.json.approval` | Deterministic mechanics; human-initiation is a doc convention, not code-enforced | Re-checks pinned-input drift | Forces back to `PLANNED` on drift, never silently approves stale content |
| `push` (APPROVED→PUSHING→PUSHED) | `push` 3601-3665; `_do_push` 3685-3752; `_record_publication` 3668-3682 | Approved candidate, `GH_TOKEN`, required `--acting-model` | Disposable clone under `reports/readme_refresh_runs/_scratch/`, real `git push` + `gh pr create`, `push/receipt.json`, `reports/repo_presenter_actions.jsonl` row, `data/readme_published_state.json` update | Deterministic mechanics | `_require_canonical_tree`, `surgical_diff_check` (declared file set = `["README.md"]` only) | Any failure → `BLOCKED` → `recover` resumes from `resume_state`; `GH_TOKEN` redacted from propagated errors |
| `verify` (post-push) | `verify` 3758-3780 | `push/receipt.json`, `gh pr view` | events.jsonl row | Deterministic | PR must exist with `pr_url` | Raises otherwise |
| `abandon` / `recover` | 3786-3813 | reason string / — | manifest update | Deterministic | `recover` requires `BLOCKED` + `resume_state` | Raises otherwise |
| `audit-portfolio` (no run) | `audit_portfolio` 2871-3002 | every active, non-excluded product | `last-verified.json` sidecar only | Deterministic, read-only | Same 103-check battery | Skips (never errors) a product with no candidate yet; **unscoped form hangs indefinitely — AUD-P1-UNSCOPED-AUDIT-HANG** |
| `declare-scope` / `accept-blocks` / `converge-verify` (MT056 surgical-scope workflow) | 3099-3370 | `split_into_scope_blocks`, `compute_block_fingerprints`, `check_scope_compliance`, `check_frozen_blocks_unchanged` (checks.py 5383-5556) | `scope/*`, `acceptance-registry.json` | Deterministic | `accept-blocks` refuses unless hard gates clean and candidate matches last-checked snapshot | `converge-verify` exits 2 on drift; **mechanism never actually exercised on any real product — AUD-P1-ACCEPTANCE-REGISTRY-UNUSED** |

## 4. Dependency extraction (`dependency_extract.py`, 1114 lines)

7 ecosystem extractors: `cargo`, `pypi`, `nuget` (csproj + nuspec), `maven`, `go_modules`,
`npm`, `none`→C++ (CMake). `_load_overrides` reads `data/dependency_overrides.json`.
Raises `DependencyExtractionError` on an unresolvable ecosystem — consumed fail-closed by
`plan_run`. The `readme-refresh-seo-deps-headings-hardening-2026-08-19` mission found and
fixed a real gap here (native extraction working for only 1 of 7 ecosystems at the time);
see `AUD-P1-MISSION-HISTORY-GAP`.

## 5. Sibling tool: `upstream_issue_workflow.py` (2059 lines)

Separate, non-run-bound two-tier state machine (`FINDING_NEXT_STATES`/`BUNDLE_NEXT_STATES`),
11 CLI verbs. Evidence confirmed present on disk for `html/python`, `pdf/go`. Reads
`data/upstream_issue_false_positive_exclusions.json`, which does not currently exist —
designed to degrade gracefully, not a bug.

## 6. Registries/config actually read (all confirmed present unless noted)

`data/products.json`, `data/registry_exclusions.json`, `data/families.json`,
`data/diagram_archetypes.json`, `data/diagram_capability_dependencies.json`,
`data/format_descriptions.json`, `data/package_registry.json`,
`data/dependency_overrides.json`, `data/api_reference_class_exclusions.json`,
`data/aspose_com_targets.json`, `data/backlinks/platform_canonical_overrides.yaml`,
`data/readme_candidate_store.json`, `data/readme_published_state.json`,
`keywords/{family}.json`, `knowledge/{family}/{platform}/merged/*`,
`content/reference.aspose.org/.../_index.md`, `content/products.aspose.org/.../_index.md`,
`runs/.clone_cache/aspose_{family}_{platform}/`. Absent-by-design:
`data/upstream_issue_false_positive_exclusions.json`.

## 7. Output directories (verified on disk)

- **Canonical candidate tree**: `reports/repo-presenter-regen-full/{family}/{platform}/`
  (`data/readme_candidate_store.json` names this the canonical tree). Gitignored,
  single-machine, non-durable. 31 product directories present (all of `data/products.json`,
  including registry-excluded `cells/typescript` per explicit prior authorization).
- **Archived trees**: `reports/repo-presenter/`, `reports/repo-presenter-regen-test/`,
  `reports/repo-presenter-regen-reproof/`, each requiring an `_ARCHIVED.json` integrity
  marker (enforced by the `candidate_store_integrity` hard gate).
- **Per-run evidence**: `reports/readme_refresh_runs/{family}/{platform}/{run_id}/*`.
- **Cross-run ledgers**: `reports/repo_presenter_actions.jsonl` (2 real rows total: the
  `note/python` PR and a `cells/rust` dry-run), `reports/locks/readme_refresh/*.lock`.
- **Publication target**: the product's own external GitHub org repo, never this monorepo
  — disposable clone → git-plumbing commit → surgical diff restricted to `README.md` →
  `git push` via `x-access-token` → `gh pr create` (no `--draft`, removed deliberately).

## 8. Locks / leases / caching / resume

Single-owner-per-product `FileLock` (`advisory_lock.py`) wrapping every mutating function,
10s timeout. `ACTIVE.json` per-product active-run pointer (refuses concurrent `start`).
Session-identity ownership check on every mutating call
(`session_identity.py`, rejects a mismatched caller). Input-drift pinning at `start`,
re-checked at `approve`. Change-isolation snapshot (`checks/last_checked_candidate.md`)
on every successful `ingest-candidate`/`recheck`. Cross-session staleness markers
(`last-verified.json`: `readme_sha256`, `verified_at`, `verified_by_run_id`,
`checks_module_version`) with advisory drift/currency findings. `BLOCKED` records
`resume_state` + `failure_reason`; `recover` validates and resumes.

## 9. Intended-vs-implemented contract matrix (declared requirement → actual status)

| Declared requirement (skill doc / mission spec) | Status |
|---|---|
| Deterministic fact extraction before any prose is written | **Fully implemented** — `plan_run` never writes prose; confirmed by module docstring and code path |
| 103 deterministic checks gate every candidate | **Implemented**, but doc-drifted in 2 places (registry.yaml "21", skill-doc mirrors "91" — AUD-P1-CHECK-COUNT-DRIFT) |
| Example code is verified, not just authored | **Partially implemented** — real only for Python behind an opt-in flag; every other of 7 target languages is permanently stubbed (AUD-P1-VERIFY-EXAMPLES-STUB) |
| Reviewer-facing dependency verification matrix | **Implemented but dead** — function exists, tested, never called, referenced in docs as if live (AUD-P1-DEAD-CODE-DEPMATRIX) |
| Surgical-scope convergence lock (accept-blocks/acceptance-registry) | **Implemented but never used in production** (AUD-P1-ACCEPTANCE-REGISTRY-UNUSED) |
| Push mechanics proven against a real external org | **True, but the code's own docstring says otherwise** — stale (AUD-P1-STALE-PUSH-DOCSTRING) |
| Portfolio health check via `audit-portfolio` | **Implemented for scoped (single-product) calls; unscoped form does not work** (AUD-P1-UNSCOPED-AUDIT-HANG) |
| Human-in-the-loop approval before push | **Code-supported, not code-enforced** — nothing prevents an agent from calling `approve` itself; the human gate is a documented convention |
| Republication-debt tripwire treated as a hard gate | **Implemented as advisory only** — `readme_refresh_run.py:2303` `hard_gate: False`, root cause of open `TC-REPUB-01` |
| Mission/taskcard governance binding for this mission line | **Historically never done** until this mission (AUD-P1-GOVERNANCE closes it for this mission only — the underlying repo-wide precedent gap, TC-HARDEN-06, remains open) |

## 10. Confirmed dead / drifted / never-exercised paths (consolidated)

All individually filed as `AUD-*` taskcards in Phase 1 (see
`reports/plan_state/readme-refresh-forensic-trust-audit-2026-08-25/taskcards.jsonl`):
`AUD-P1-DEAD-CODE-DEPMATRIX`, `AUD-P1-CHECK-COUNT-DRIFT`, `AUD-P1-ACTING-MODEL-UNDOCUMENTED`,
`AUD-P1-STALE-PUSH-DOCSTRING`, `AUD-P1-ACCEPTANCE-REGISTRY-UNUSED`,
`AUD-P1-MISSION-HISTORY-GAP`, `AUD-P1-SKILL-DESCRIPTION-PLACEHOLDER`,
`AUD-P1-VERIFY-EXAMPLES-STUB`, `AUD-P1-TEMPLATE-OUTSIDE-GIT`,
`AUD-P1-MISSION-NUMBER-COLLISION`, `AUD-P1-UNSCOPED-AUDIT-HANG`.

No `TODO`/`FIXME`/`NotImplemented` markers exist in either `readme_refresh_run.py` or
`readme_refresh_checks.py` — every gap found is a *behavioral* gap (stubbed, dead,
undocumented, or mis-wired), not an unfinished-code marker.
