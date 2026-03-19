# Current State Audit — foss-launcher-skills

> Date: 2026-03-19
> Scope: Full codebase analysis from code, not assumptions

## What This Repo Is In Practice

`foss-launcher-skills` is a **semi-embedded FOSS content pipeline masquerading as a skills library**.

It is not a thin human-facing wrapper around launcher capabilities. It contains 36 skill definitions, 17 Python scripts forming a complete knowledge-to-content pipeline, 7 JSON schemas, a golden corpus, and multiple runtime data directories — all co-located in a single repo with no package boundary.

The product boundary is unclear: the repo simultaneously acts as a skill distribution system, an evidence pipeline engine, a knowledge extraction toolchain, and a golden corpus manager.

---

## Subsystem Inventory

| Subsystem | Files | Approx Lines | Role |
|-----------|-------|-------------|------|
| Skills | 36 `.md` files in `skills/` | ~4,000 | Agent instructions with YAML frontmatter |
| Evidence pipeline | 5 scripts (materialize, mental_model, verify, decide, differ) | 1,513 | **NEW**: does not exist in launcher |
| Knowledge pipeline | 4 scripts (scout, discover, merge, index) | 3,034 | Overlaps with launcher core |
| Golden corpus handling | 3 scripts + `golden/` dir (golden_index, golden_conformance, refresh_golden) | 978 | Ported from launcher |
| Content profiling | 2 scripts (corpus_scan, embed) | 834 | Partially unique |
| Utilities | 3 scripts (config_loader, schema_validate, readme_sync) | 410 | Product-specific glue |
| Distribution | 1 script (tools/distribute.py) | 122 | Agent-specific output generation |
| Schemas | 5 JSON schemas in `configs/schemas/` | — | Evidence artifact contracts (PEF, mental_model, verification, decision, diff) |
| Config | 3 YAML files (config.yaml, families.yaml, intake_config.yaml) | — | Site paths, taxonomy, intake orgs |
| Governance | AGENTS.md | ~179 | 4 roles, autonomy tiers, hard stops, skill chains |
| Tests | 18 files, 227 test cases | — | 15 failures (all scout/tree-sitter related) |
| Runtime data | knowledge/, evidence/, output/, reports/, plans/, golden/ | — | Co-located with source in repo tree |

---

## Current Execution Model

Skills instruct agents to invoke Python scripts via commands like:
```
python scripts/scout.py {family} {platform} {repo-path} {output-dir}
python scripts/materialize.py {family} {platform}
```

The orchestration skill (S-38: launch-product) chains ~10 skills into a 4-phase pipeline:
1. Knowledge extraction: scout → merge → index → embed → corpus_scan
2. Evidence materialization: materialize → mental_model → decide
3. Page generation: per-page skill chains with ground-check gates
4. Cross-platform consistency check

Scripts read/write to `knowledge/`, `evidence/`, `output/`, `reports/` directories relative to the repo root. Path resolution uses `config_loader.py` for some scripts, but evidence pipeline scripts hardcode `Path("evidence")` and `Path("knowledge")` at module level.

---

## Observed Coupling to FOSS Launcher

### Explicitly Ported/Adapted Scripts

| Script | Lines | Source | Comment in Code |
|--------|-------|--------|-----------------|
| `discover.py` | 574 | `foss-launcher/src/launcher/intake/org_scanner.py` | "Adapted from foss-launcher/src/launcher/intake/org_scanner.py. Self-contained" |
| `golden_index.py` | 410 | `foss-launcher/golden_loader.py` | "Ported from foss-launcher's golden_loader.py" |
| `golden_conformance.py` | 438 | `foss-launcher/evaluate/checks/golden_conformance.py` | "Ported from foss-launcher's evaluate/checks/golden_conformance.py" |
| `refresh_golden.py` | 133 | N/A (sync utility) | Copies golden corpus from launcher filesystem path |

### Implicitly Parallel Scripts

| Script | Lines | Launcher Equivalent | Overlap |
|--------|-------|-------------------|---------|
| `scout.py` | 1,755 | `launcher.intake.scout` | Tree-sitter extraction across 6 languages. Same purpose, heavily self-contained implementation. |
| `merge.py` | 510 | `launcher.knowledge.merge` (if exists) | Semantic claim matching and consolidation. Thin enough to be boundary glue. |

### Total Duplicated/Parallel Code: ~3,275 lines

No script imports from `foss-launcher` as a Python package. All dependencies are fully embedded — copies, not imports.

---

## Current Strengths

1. **Evidence pipeline is genuinely new IP.** The 5 evidence scripts (materialize, mental_model, verify, decide, differ) implement a novel Product Evidence File (PEF) framework that does not exist in launcher. This is the product's core differentiator.

2. **Governance model is production-quality.** AGENTS.md defines 4 roles (scout, writer, reviewer, orchestrator), autonomy tiers (AUTO/WARN/BLOCK/HUMAN-ONLY), hard stops, skill chains, escalation rules, commit requirements, and session limits.

3. **JSON schemas enforce evidence contracts.** 5 schemas validate PEF, mental model, verification reports, decisions, and diffs. All evidence artifacts include `schema_version` for forward compatibility.

4. **Provenance tracking is thorough.** Every claim carries provenance (dual, dual_fuzzy, scout_only, external_only) and confidence scores. PEF materializations maintain a changelog. Diffs are timestamped.

5. **Skill definitions are well-structured.** 36 skills with clear argument formats, pre/post-conditions, error handling, and output specifications.

6. **Multi-agent distribution exists.** distribute.py generates outputs for Claude Code, Codex CLI, and Kilo Code from a single canonical source.

---

## Current Architectural Liabilities

### 1. Shadow Launcher (Critical)
3,275 lines of knowledge extraction code duplicate launcher functionality. These scripts will silently drift from their launcher originals, with no update mechanism, no version tracking, and no compatibility contract.

### 2. No Package Boundary (Critical)
The repo has no `pyproject.toml`, no `setup.py`, no installable structure. Scripts use `sys.path.insert(0, ...)` hacks to find each other. The product is not installable via `pip` and has no entry points.

### 3. Runtime State Mixed with Source (High)
`knowledge/`, `evidence/`, `output/`, `golden/`, `reports/`, `plans/` live in the repo tree alongside source code. This makes:
- Fresh clones noisy (runtime artifacts appear as untracked files)
- CI fragile (tests may depend on leftover state)
- `.gitignore` management brittle
- Clean installs impossible without manual cleanup

### 4. Missing Config Contract (High)
No `config.schema.json` exists. `config.yaml` contains an absolute path to a developer's machine (`/c/Users/prora/OneDrive/...`). Test suite shows 15 failures — all in scout tests due to tree-sitter subprocess import, not config issues. Non-scout tests (210/227) pass cleanly.

### 5. Multi-Agent Support Is Shallow (Medium)
distribute.py strips frontmatter for Claude and preserves it for Codex/Kilo Code. There is no:
- Capability awareness (which agent can execute which skill)
- Dependency chain validation
- Install manifest per agent
- Behavioral contract beyond markdown formatting
- Argument schemas for typed inputs

### 6. Hardcoded Paths Bypass Config (Medium)
Evidence scripts define module-level constants:
```python
EVIDENCE_ROOT = Path("evidence")
KNOWLEDGE_ROOT = Path("knowledge")
```
These bypass `config_loader.py` entirely, making the config system partially decorative.

### 7. No Versioning Contract with Launcher (Medium)
No mechanism to detect if locally ported scripts are compatible with current launcher. No golden corpus format version check. No compatibility range declaration.

### 8. scout.py Is a Maintenance Liability (Medium)
1,755 lines of tree-sitter extraction across 6 languages (Python, C#, Java, C++, TypeScript, JavaScript). Grammar updates, new language support, and AST parsing bugs must all be maintained independently from launcher.

---

## Where the Repo Acts Like a Copied Mini-Launcher

The repo is not a thin skills layer in these specific areas:

1. **Repository discovery** (`discover.py`): Full GitHub API integration with rate limiting, scan state persistence, and family/platform classification. This is launcher's intake pipeline.

2. **Code extraction** (`scout.py`): Full tree-sitter AST traversal with language-specific extractors, class/method/property detection, format detection, and limitation analysis. This is launcher's core extraction engine.

3. **Golden corpus management** (`golden_index.py`, `golden_conformance.py`, `refresh_golden.py`): Indexing, conformance scoring, and sync — all ported from launcher's evaluate subsystem.

4. **Knowledge consolidation** (`merge.py`): Dual-source verification with semantic matching, token overlap scoring, and provenance tagging. This is substantive pipeline logic, not a thin wrapper.

5. **Embedding** (`embed.py`): Dual-tier embedding with API and local fallback, chunking strategies, and vector storage. Independent but substantial.

In total, 6,891 lines of Python pipeline code live in this "skills" repo (verified via `wc -l`). Only 1,513 lines (the evidence pipeline) are genuinely new. The rest is shared concern with launcher or boundary-layer glue.
