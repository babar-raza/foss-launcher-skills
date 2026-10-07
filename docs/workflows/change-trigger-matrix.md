# Change-Trigger Matrix

> Status: Current — successor to the archived
> `docs/_archive/pre-refactor/workflows/change-trigger-matrix.md` (retired 2026-05-30).
> Referenced by: `AGENTS.md` §9b ("Regeneration After Extraction Script Changes") and §9c
> ("Change-Trigger Matrix"). Written 2026-07-29/30 during the `MT014-2026-07-29-PDF-GO-REDO`
> mission, after `AGENTS.md`'s own pointer to this path was found dead (the old file had been
> archived with no successor ever written).

## Purpose

This document answers one question: **when something in this pipeline changes, which
already-generated knowledge and content needs to be reconsidered?** It distinguishes two
independent drift axes, because they require different detection mechanisms and land in
different backlog shapes:

| Axis | Question | Detection | Backlog shape |
|------|----------|-----------|----------------|
| **Upstream drift** | Did the FOSS repo itself change? | `change-sweep` (S-94) — batch SHA comparison across all launched products | `{FAMILY}-{PLATFORM}-REFRESH-NNN` |
| **Mechanism drift** | Did *our own* extraction/enrichment/snippet/format code get smarter, independent of any upstream change? | `mechanism-sweep` (S-117) — diff-only re-run of the fixed step against each already-launched product sharing that language/mechanism | product-specific row citing the sweep report (e.g. `PDFGO-STALE-001`) |

The original 2026-05-30 archived version of this document only described the first axis in
manual, unautomated prose (a table of "if X changed, re-run Y by hand for all products").
That guidance produced real, recurring gaps — a Go interface/embedding extraction fix left
pdf/go's own already-re-scouted knowledge stale relative to its published content for weeks
before anyone noticed (`PDFGO-STALE-001`); an LLM-credential fix silently improved
cells/rust's enrichment with no regeneration follow-up (`RUST-ENRICH-001`); a directory-
matching fix elsewhere retroactively corrected cells/cpp's snippet count with nobody
watching for it (`PDFCPP-SNIPPET-PREMISE-001`). This document's job now is to route each
kind of change to the right *automated* sweep, not to describe manual re-run commands.

## Trigger table

| Changed surface | Sweep to run | Notes |
|---|---|---|
| A product's stored `repo_sha` is behind the FOSS repo's current HEAD | `/change-sweep` (S-94) | Read-only; route HIGH/MEDIUM findings via `/discovery-triage` (S-95). Does not invoke `/refresh-product` itself. |
| `scripts/pipeline/extraction/*.py` (per-language extractors, `api_surface.py`, `tree_helpers.py`, `formats.py`, snippet extraction) changes in a way that captures previously-dropped or previously-mis-detected data | `/mechanism-sweep` (S-117) | Run against every other already-launched product sharing the same language/mechanism, **excluding** the product the triggering mission was already working on. Separates `modified_apis` (in-scope for the sweep) from incidentally-discovered `new_apis` (route to change-sweep/backlog instead — do not conflate the two). |
| An enrichment/scout step (`knowledge_enrich`, LLM credential/routing changes) changes what claims get generated | `/mechanism-sweep` (S-117) | Same mechanism-drift axis — the fix is in *our* code, not upstream. |
| A `content_eval` evaluator's logic changes (new FAIL/WARN conditions, or a false-positive fix) | Re-run `content_eval` for all products with the affected evaluator category; see §9a (Evaluator Change Checklist) | Not a knowledge-layer change — content re-grading, not re-scouting. |
| `site_planner.py` / delta logic changes | `/delta-site-plan` (S-82) per affected product | Determines actual page-level add/update/remove impact once knowledge is current. |
| A `scripts/{package}/` directory is deleted (e.g. `scripts/translator/`) | `check_root_docs_truth.py` (no `--staged`) against all seven root operator/governance docs, or `/root-docs-refresh` (S-121) | The commit-time gate (`--staged` mode, wired into pre-commit Step 9b) only catches this if the deleting commit *also* touches one of the seven files — it usually won't. This is a documentation-drift axis, added 2026-08-08 after a real incident: `scripts/translator/` was deleted 2026-07-02 and left seven dead references live in `OPERATOR_GUIDE.md`/`RUNBOOK.md` for five weeks, undetected. |
| `EVALUATOR_FREEZE_VERSION` bumps in `content_eval/__init__.py` (an evaluator graduates experimental → canonical) | `GRADE_CONTRACT.md` must update in the same PR — enforced by `check_grade_contract_sync` (part of `root_docs_checks.py`, S-121); run `/root-docs-refresh` if it wasn't updated inline | Same root cause as the row above: `evidence_depth` graduated 2026-07-14 but `GRADE_CONTRACT.md`'s changelog wasn't touched until 2026-08-08, three weeks later. |
| `refresh_knowledge.py::_compute_extractor_hash()` input set changes (which files it hashes, not just their content) | `/change-sweep` (S-94) or `/mechanism-sweep` (S-117) against every already-scouted product, once | One-time fleet event (2026-08-29, MT040-2026-08-28-PDF-TYPESCRIPT-LAUNCH TC-MT040-48, shared with MT039 TC-MT039-11): the hashed set widened from a hand-maintained 4-file allowlist (`formats.py`, `api_surface.py`, `scout.py`, `promote.py`) to every `.py` file under `scripts/pipeline/extraction/` (adds `tree_helpers.py`, `snippets.py`, `package_manifest.py`, `package_root.py`, `claims.py`, `validate_scout_output.py`, `outputs.py` as real inputs for the first time). Every already-scouted product's `extractor_hash` in `model.yaml` predates this widening, so the next `refresh_knowledge.py` run for each will correctly report `extractor_changed: true` even if none of the newly-watched files ever affected that product's own extraction in practice — this is the honest "we can now detect drift here too" signal, not a false positive, and does not by itself require re-enrichment (scout-only re-extraction suffices to re-baseline the hash; see `refresh_knowledge.py`'s own `--compulsory-enrich`/`--skip-enrich` flags). |

**MT074 rows (fleet-propagation machinery).** Same purpose as the table above, for the triggers added by
mission MT074 (the clone-free fleet drift detector, the capability ledger and its gate, the independent
review panel, and the deployed workflow templates).

| Changed surface | Sweep / check to run | Notes |
|---|---|---|
| `snippet_budget` in `scripts/pipeline/config/platform_capabilities.yaml`, or `scripts/pipeline/extraction/snippets.py` ordering/selection | `/mechanism-sweep` (S-117) for every product sharing the language; keep `check_platform_capabilities.py` in agreement; golden-output test for a product under the cap | A changed budget or ordering changes which snippets are harvested, so citable code for already-launched products may change. The extractor hash moves too (the row above). Never evict a currently cited snippet: the selection must be a stable superset. |
| `scripts/pipeline/config/language_api_paths.yaml` (per-language source extensions and public-API path globs) | Re-run `fleet_drift.py` (S-94 fleet step) for the products of the affected platforms, and the `fleet_drift` recorded-fixture tests | Changes how drift is tiered (`NON_SOURCE` / `SOURCE` / `API_TOUCHED` / `UNKNOWN`) and therefore which products get issues. A tier change is a behaviour change: record the before/after counts. |
| `scripts/pipeline/config/capability_placement.yaml` (thresholds for dedicated section / mention / none) | Boundary tests on **both sides of every changed threshold**, then a dry-run (no content) over at least three drifted products of different languages before applying | A threshold edit is never made in the same commit as a run that uses it. A changed threshold can re-place capability units in an in-flight ledger; re-plan through `/refresh-product`, do not hand-edit the ledger. |
| `scripts/pipeline/commands/knowledge/promote.py`, or `refresh_knowledge.py::_compute_extractor_hash()` | `/mechanism-sweep` (S-117) for the affected languages | The hash is LF-normalised and `promote.py` preserves it into `merged/model.yaml`. Any change to `promote.py` or a file under `extraction/` moves the hash for the whole fleet: a one-time event per change. Products with no stored hash are listed as `extractor_hash_missing` and are treated as unknown, not current. |
| `scripts/ci/deployed-workflows/*.yml` (templates deployed to `Aspose/aspose.org-workflows`) | `/workflow-harden` (S-115) template checklist, then deploy in order (code on `main`, workflows PR, dispatch and verify), then `check_workflow_drift.py --approve <name> --reason ...` | The deployed YAML runs scripts from a fresh checkout of `main`, so code must land first. Until `--approve` runs and the rewritten `data/workflow_deploy_baselines.json` is committed, `workflow-drift-watch` reports `DIVERGED` for the template. Only the YAML needs deploying; script changes need no redeploy. |
| `scripts/pipeline/config/discovery_criteria.yaml` (once frozen), `propagation_analyzer.py` ranking rules | Re-run `propagation_analyze.py analyze` + `rank` over the fleet and compare `candidates.json` | A criteria change is its own commit, never merged with a discovery run that depends on it; the ranking must stay deterministic (a re-run is byte-identical). |
| `scripts/pipeline/commands/ops/capability_surface_gate.py` checks, or `lib/availability.py` qualifier/coordinate rules | The gate's own tests, then `capability_surface_gate.py --dry-run` against each product already recorded `PROPAGATED_LOCAL`/`PROPAGATED` | Tightening a rule can make a recorded product fail on a re-run; that is information, not a regression. Never write `content_propagated_*` from anywhere else. |
| `docs/reference/production-page-rubric.md` | Re-calibrate `/independent-content-review` (S-127): the seeded-defect canaries must be fully caught again | Calibration is bound to the rubric's sha256; a changed rubric invalidates it. |

**On documentation drift as its own axis**: the two documentation-drift rows in the first table (dead paths, frozen-value mismatch) are deliberately narrow —
they only cover the specific drift *shapes* a real incident already exposed (dead paths,
frozen-value mismatch). This document's own history (see the "original 2026-05-30 archived
version" note above) is that a *finite, enumerated* trigger list always eventually misses
something new. Treat these two rows as the fast path for known shapes, not a complete
defense — `/root-docs-refresh` (S-121), run periodically or whenever a root doc "feels"
stale, is the backstop for drift shapes this table doesn't yet name.

## Relationship to `/refresh-product` (S-84)

Neither `change-sweep` nor `mechanism-sweep` regenerates content. Both are **detection**
skills that end in a backlog row (or an explicit `NONE`/clean-negative record). A human or
agent then decides whether and when to run `/refresh-product {family} {platform}` against
that backlog row — this separation exists so detection can run cheaply and often (e.g.
weekly) without every finding forcing an immediate, expensive regeneration cycle.

## Related

- [AGENTS.md §9b/§9c](../../AGENTS.md) — the governance rule this document is the successor
  target for.
- `skills/change-sweep.md` (S-94) — upstream-drift detection.
- `skills/mechanism-sweep.md` (S-117) — mechanism-drift detection.
- `docs/workflows/evaluator-changes.md` — §9a, the evaluator-logic-change checklist.
- `backlog/BACKLOG.md` — where both sweeps' findings land.
