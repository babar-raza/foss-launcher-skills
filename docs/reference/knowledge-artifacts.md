# Knowledge Artifacts Reference

Status: Current
Audience: Operator, Contributor, Agent
Canonical reference: this page
Last code-backed audit: 2026-05-30

The knowledge layer is derived from source code and grounds generated content.

## Layers

| Layer | Path | Source | Purpose |
|---|---|---|---|
| Scout | `knowledge/{family}/{platform}/scout/` | Tree-sitter extraction from clone cache | Raw deterministic API, format, snippet, limitation, and claim artifacts. |
| Merged | `knowledge/{family}/{platform}/merged/` | Promotion from scout plus optional grounded enrichment | Canonical input for content generation and validation. |

## Core Files

| File | Contract |
|---|---|
| `model.yaml` | Product knowledge metadata including source revision and freshness fields. |
| `claims.json` | Semantic claims used for content grounding. |
| `api_surface.json` | Structured API surface extracted from source. |
| `api_surface.md` | Human-readable generated API surface. |
| `formats.json` | Format support facts. |
| `limitations.md` | Known limitations that override positive claims at same level. |
| `.pipeline_state.json` | Step completion manifest. |

## Workflow

1. Resolve clone cache path.
2. Run scout.
3. Promote scout artifacts into merged artifacts.
4. Generate or validate content against merged artifacts.

See [CLI reference](cli.md#scout) and [file contracts](file-contracts.md#knowledge-artifacts).

## Class-Count Statistics (MT067-2026-09-10)

Before this fix, `class_count` was independently computed by 4+ pipeline stages under different, undocumented definitions, producing artifacts that disagreed under the same field name — barcode/python read 26, 79, or 146 depending which file was opened; a portfolio scan found the same mechanism live on 15 of 32 launched products. `scripts/pipeline/lib/class_stats.py::compute_class_stats(api_surface)` is now the single source of truth every writer (`extraction/outputs.py`, `commands/knowledge/scout.py`, `commands/knowledge/promote.py`, `commands/knowledge/index.py`, `commands/launch/site_planner.py`) calls, returning three namespaced fields instead of one overloaded one:

| Field | Meaning | Formula |
|---|---|---|
| `total_declared` | Every class-kind entry extracted from source (`kind != "function"`). Includes private, internal, test-file, and duplicate-namespace entries. An extraction-completeness/QA metric. | `sum(1 for c in api_surface if c["kind"] != "function")` |
| `public_documented` | The name-deduplicated subset that is public, non-test, non-internal (or explicitly re-exported via package `__init__`, `exported_via_package_init`). The number relevant to content-generation sizing and documentation scope. | filtered via `is_public_api_entry()`, deduped by name |
| `raw_entries_including_non_class` | Every entry regardless of kind, functions included. Previously silently mislabeled "Classes" in `merge_report.md`/`api_surface.md`'s console output (a labeling bug, not a legitimate third definition). | `len(api_surface)` |

Each artifact's pre-existing `class_count` field is kept as a **deprecated alias** for backward compatibility, pinned to whichever of the three that specific file historically meant (`model.yaml`/`merge_report.md` → `total_declared`; `index.json` → `public_documented`) — never silently changed to a different meaning. New readers should use the namespaced `stats.classes.*` block instead.

**Why one shared function instead of a check that reconciles differing values**: `total_declared` and `public_documented` are both genuinely useful for different consumers; collapsing to a single number would just move the ambiguity, not remove it. `scripts/ci/checks/check_knowledge_stats_consistency.py` (WARN-only initially, wired into pre-commit Step 42 and CI) verifies every artifact's `stats.classes` block agrees with a live recomputation from `api_surface.json` — since every writer now shares one implementation, disagreement means real staleness (an artifact wasn't regenerated after `api_surface.json` changed) or a genuine regression, not a legitimate difference of definition. `scripts/ci/checks/check_no_inline_class_count.py` (also WARN-only) is a preventive heuristic lint flagging any new inline class-counting formula outside `class_stats.py`, closing the gap that let 4 independent reimplementations accumulate silently in the first place.

**A known, accepted risk**: consolidating into one function means a bug in `class_stats.py` now propagates uniformly to every artifact and every product, instead of being scattered and eventually noticed by cross-artifact disagreement (which is how this defect was originally found). `scripts/pipeline/tests/test_class_stats.py` guards against this with structural invariant tests (e.g. `raw_entries_including_non_class >= total_declared >= public_documented >= 0`), not just worked examples.

Full investigation, portfolio scan, and root-cause analysis: `C:/Users/prora/.claude/plans/vast-questing-spindle.md`.
