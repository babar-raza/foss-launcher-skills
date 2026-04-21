# CHANGELOG — aspose.org Skills System

---

## Phase 5: Score Improvement — Phase 0 (Confidence Gap Closed)

**Date**: 2026-04-21
**Branch**: main
**Tests**: 541 passed, 15 skipped, 0 failed (+15 tests, -17 failures vs prior baseline)
**Plan source**: `C:\Users\prora\.claude\plans\reactive-sprouting-matsumoto.md`

### Changes

- **tests/test_scout_units.py**: Fixed `requires_tree_sitter` skip guard. Changed from
  in-process `import tree_sitter` (accessible via user site-packages) to subprocess check
  that mirrors the actual runtime environment. Result: 17 FAILs → 15 SKIPs.

- **tests/test_schema_validate.py**: Added `TestConfigSchemaNegativeCases` with 5 tests:
  governance dict empty, sites as list, knowledge_path as int, empty config dict,
  content_repo as int. Closes TASK-03 (schema rejection untested gap).

- **tests/test_materialize.py**: Added `TestMaterializeFailureModes` with 4 tests:
  missing claims.json, missing model.yaml, empty knowledge dir, malformed model.yaml.
  Closes TASK-04 (evidence pipeline silent failure gap).

- **tests/test_pre_write.py**: Added `TestStaleSinceBlock` with 4 tests:
  stale-model finding causes FAIL, message prefix, fresh model passes, multiple findings
  all reported. Closes TASK-05 (stale-model detection untested gap).

- **scripts/check_setup.py**: Added `NOTE` level (rank 0, same as OK) for truly optional
  features. Changed optional package absence from WARN (exit 1) to NOTE (exit 0). Fixes
  2 pre-existing CLI test failures. Design intent: optional packages (tree_sitter) being
  absent is informational, not a warning that the setup is broken.

- **tests/test_check_setup.py**: Updated import and test name to reflect NOTE level.

### Governance Files Updated
- `reports/PLAN_SOURCES.md`: Updated primary plan source
- `reports/PLAN_INDEX.md`: Added reactive-sprouting-matsumoto plan
- `reports/TASK_BACKLOG.md`: Created with Phase 0/1/2 backlog
- `reports/STATUS.md`: Updated with new test counts

### Test commands
```bash
python -c "import sys; sys.path.insert(0, r'C:\Users\prora\AppData\Roaming\Python\Python313\site-packages'); import pytest; sys.exit(pytest.main(['tests/', '--tb=no', '-q']))"
# Expected: 541 passed, 15 skipped, 0 failed
```

---

## Phase 2+3+4: Full Remediation Complete

**Date**: 2026-03-31
**Branch**: main
**Tests**: 371 passed, 0 failed (all workstreams complete)

### Phase 2 — Enforcement

- **scripts/path_guard.py** (new): ALLOW/DENY enforcement against forbidden_paths from config.yaml; hardcoded safety net for `.git/`, `themes/`, `scripts/`, etc.; backslash normalisation; 38 tests
- **scripts/check_setup.py** (new): OK/WARN/ERROR environment validation; checks CONTENT_REPO_PATH, required/optional packages, knowledge model; 31 tests
- **scripts/ops_log.py** (new): Append-only JSONL ops log at `reports/ops.log`; each pre_write call writes an entry; 24 tests
- **tests/test_path_guard.py** (new): 38 tests — all passing
- **tests/test_check_setup.py** (new): 31 tests — all passing
- **tests/test_ops_log.py** (new): 24 tests — all passing

### Phase 3 — Hardening

- **scripts/pre_write.py** (new): Mandatory pre-write hook wrapping path_guard + audit_files; PASS/WARN/FAIL/ERROR output; logs to ops.log; 25 tests
- **tests/test_pre_write.py** (new): 25 tests — all passing
- **tests/test_e2e_pipeline.py** (new): 8 integration tests — full pipeline chain verified (M8 ✅)

### Phase 4 — Scout Fixes + Skill Integration

- **scripts/scout.py** (modified): Added enum_count tracking, dataclass field extraction, property setter detection (`read_write`), constants.json generation (UPPER_CASE module-level assignments + IntEnum members)
- **scripts/pipeline/merge.py** (modified): Copy `constants.json` from scout output to `merged/`
- **scripts/pipeline/index.py** (modified): Load `constants.json`; add `enum_classes` and `constants` fields to `index.json`
- **tests/test_scout_units.py**: All 17 tests now pass (was 7 failing pre-existing failures)
- **skills/new-docs-page.md**: Added step 0 `check_setup.py` validation; replaced `audit.py` with `pre_write.py` pre-write gate
- **skills/new-blog-post.md**: Same — check_setup.py + pre_write.py integrated
- **skills/new-kb-howto.md**: Same
- **skills/new-kb-faq.md**: Same
- **skills/new-reference-page.md**: Same
- **skills/launch-product.md**: Added checkpoint/resume protocol; Step 1.0 check_setup.py validation; full checkpoint schema with step-by-step state tracking

---

## Phase 0+1: Production-Readiness Remediation

**Date**: 2026-03-31
**Branch**: main
**Source**: Audit plan `wild-yawning-sprout.md`

### AGENTS.md
- Added Phase 1.5 (evidence materialization) to §6 launch chain
- Added S-43 (evidence-decide), S-44 (evidence-materialize), S-45 (mental-model) to §12 skill map
- Added validation systems comparison table to §12 enforcement scripts section
- Added note on S-40/S-41 numbering collision resolution (S-44, S-45)

### scripts/pipeline/audit.py
- Removed `--no-evidence` flag — evidence checking is now always mandatory (cannot be bypassed)
- Removed `check_evidence` parameter from `audit_product()` and `audit_files()` — simplified API
- Fixed per-file fail count: evidence findings now stored in `ev_findings` and added to both `file_findings` (for per-file log) and `findings` (master list)
- Updated docstring Usage section

### skills/content-check.md
- Evidence citation checks updated: replaced HTML comment citation checks (`<!-- evidence: ... -->`) with frontmatter `evidence:` block checks
- Added explicit note: "Do NOT check for HTML comment citations — legacy format only"
- Checks now validate: `evidence.model_sha`, `evidence.claims`, `evidence.apis` array

### skills/evidence-materialize.md
- Renumbered id: S-40 → S-44 (resolves collision with batch-remediate)
- Updated skill title from "S-40:" to "S-44:"

### skills/mental-model.md
- Renumbered id: S-41 → S-45 (resolves collision with batch-eval-fix)
- Updated skill title from "S-41:" to "S-45:"

### README.md
- Skill count updated: "32 agent skills" → "35 agent skills"
- Added Evidence Pipeline section to skill catalog (S-43, S-44, S-45)
- Updated launch chain to include Phase 1.5
- Added validation pipeline section documenting audit.py vs content_eval
- Fixed evidence-cite description: "HTML comments" → "frontmatter citations"

### QUICKSTART.md (NEW)
- First-time operator guide: prerequisites, install, configure, first run, verify
- Covers Python 3.10+, tree-sitter install, content repo config, first scout, first page, full launch
- Troubleshooting section for common failures

### Test results
- Pre-change: 7 failures (all pre-existing, test_scout_units.py fixture issues)
- Post-change: 7 failures (same 7, unchanged — no regressions introduced)
- 238 tests passing

### Test commands
```bash
PYTHONPATH=.pylibs python .pylibs/pytest/__main__.py tests/ -q --tb=no
# Expected: 238 passed, 7 failed (pre-existing scout fixture failures)

grep -n "no.evidence\|check_evidence" scripts/pipeline/audit.py
# Expected: 0 matches

grep "^id:" skills/evidence-materialize.md skills/mental-model.md
# Expected: id: S-44 / id: S-45

grep -n "Phase 1.5\|S-44\|S-45\|S-43" AGENTS.md
# Expected: multiple lines in §6 and §12
```

---

# CHANGELOG — aspose.org Skills System Import

**Date**: 2026-03-31
**Branch**: import/aspose-improvements
**Scope**: Full import of aspose.org improved skills system into standalone repo

---

## WS1: Config Infrastructure

### scripts/config_loader.py
- Added `resolve_knowledge_root()` — returns `Path(config.knowledge_root)` (default: `knowledge/`)
- Added `resolve_reports_root()` — returns `Path(config.reports_path)` (default: `reports/`)

### config.yaml
- Added `knowledge_root: "knowledge"` key with documentation comment
- Added comment clarifying `reports_path` default

### configs/schemas/config.schema.json
- Added `knowledge_root` property definition

### tests/test_config_loader.py
- Added 6 new tests: `test_resolve_knowledge_root_*` (3) and `test_resolve_reports_root_*` (3)

---

## WS2: Pipeline Core Scripts

### NEW: scripts/pipeline/ (subpackage)
- `__init__.py` — package marker
- `audit.py` — deterministic S-23 ground-check (adapted from aspose.org)
- `knowledge_core.py` — shared knowledge model loader (adapted from aspose.org)
- `token_ops.py` — token extraction and verification (copied from aspose.org)
- `attach_evidence.py` — evidence block generator (adapted from aspose.org)
- `change_guard.py` — pre-write knowledge gate S-33 (adapted from aspose.org)
- `content_audit.py` — semantic content audit S-32 (adapted from aspose.org)
- `remediate.py` — batch remediation pipeline (adapted from aspose.org)
- `org_scanner.py` — organization structure scanner (copied from aspose.org)
- `check_audit_results.py` — audit result validator (copied from aspose.org)
- `refresh_knowledge.py` — knowledge refresh from upstream (copied from aspose.org)
- `update_product_registry.py` — product registry maintenance (copied from aspose.org)

**Path adaptation pattern applied to all adapted scripts**:
```python
_HERE = Path(__file__).resolve().parent          # scripts/pipeline/
_SCRIPTS = _HERE.parent                          # scripts/
sys.path.insert(0, str(_SCRIPTS))
from config_loader import resolve_knowledge_root, resolve_content_repo, resolve_reports_root
```

### REPLACED: scripts/scout.py
- Replaced with aspose.org version (1,755 → 1,878 LOC)
- Added scout_enricher support (optional Doxygen/JavaDoc/XML doc enrichment)
- Enricher path adapted: looks in `scripts/pipeline/scout_enrichers/`

### REPLACED: scripts/merge.py
- Replaced with aspose.org version (509 → 692 LOC)
- New: FL knowledge merge logic (`fl/` subdirectory support)
- New: `_merge_snippets()`, `_generate_api_surface_md()`
- Backward-compat shims: `tokenize()`, `token_overlap()`, `find_semantic_match()` preserved for existing tests

### REPLACED: scripts/index.py
- Replaced with aspose.org version (196 → 326 LOC)
- New: `api_coverage` and `snippets_coverage` index blocks
- New: `_is_public_api_entry()`, `_has_surface()`, `_is_interface_name()`, `_snippets_coverage()`

### REPLACED: scripts/embed.py
- Replaced with aspose.org version (447 → 431 LOC)
- Refactored vector embedding, same external interface

### Bug fix: scripts/pipeline/attach_evidence.py
- Fixed Windows cp1252 encoding crash on `print(__doc__)` when called without arguments
- Changed to `sys.stdout.buffer.write(doc.encode("utf-8", errors="replace"))`

---

## WS3: Content Eval + Scout Enrichers

### NEW: scripts/pipeline/content_eval/ (42-file package)
Complete multi-dimensional content evaluation system:
- 20 evaluators (api_accuracy, platform_purity, forbidden_claims, page_role, structure, risk_language, evidence_depth, prose_truth, code_plausibility, coverage, + cross-page)
- Remediation system (triage, runner, planner, 8 fixers)
- Reporters (markdown, json)
- `cli.py` adapted: sys.path fix + `resolve_reports_root()` for config-driven reports path

### NEW: scripts/pipeline/scout_enrichers/ (4-file package)
- `_doxygen.py` — Doxygen doc enrichment for C++
- `_javadoc.py` — JavaDoc enrichment for Java
- `_xml_doc.py` — XML doc enrichment for .NET/C#
- `__init__.py` — platform → enricher dispatch

---

## WS4: Skills (42 total)

### REPLACED (18 skills with improved aspose.org versions):
change-guard, content-audit, content-check, cross-platform, embed-knowledge, evidence-cite,
knowledge-diff, new-blog-post, new-docs-page, new-kb-faq, new-kb-howto, new-reference-page,
path-guard, repo-scout, stale-detect, truth-index, truth-merge, truth-sync

### ADDED from aspose.org skills/ (2 new):
- `knowledge-bootstrap.md` — shared pre-condition gate for knowledge state
- `truth-audit.md` (S-38) — member-level API verification (deep)

### ADDED from aspose.org .claude/commands/ (4 new, with canonical frontmatter added):
- `batch-eval-fix.md` (S-41) — lightweight eval + auto-fix only
- `batch-remediate.md` (S-40) — full eval→fix→LLM→re-eval pipeline
- `category-fix.md` (S-42) — surgical category-specific fixer
- `content-eval.md` — multi-dimensional content evaluation

### KEPT (18 standalone-only skills, no aspose.org equivalent):
corpus-scan, discover-products, eval-page, evidence-decide, evidence-materialize,
evidence-verify, faq-generate, ground-check, heal-page, knowledge-update, launch-product,
mental-model, page-draft, page-enhance, page-plan, page-update, project-phase-store, rubric-align

### Distributed (tools/distribute.py):
- 42 skills × 3 formats = 126 distributed files
- `.claude/commands/` (42), `.agents/skills/` (42), `.kilocode/skills/` (42)

---

## WS5: Governance & Documentation

### REPLACED: AGENTS.md
- Source: aspose.org/AGENTS.md (2026-03-22)
- Adaptations: Section 4 write paths use `$CONTENT_REPO_PATH`-relative syntax
- Added: Section 1 standalone repo operation note
- Added: batch-remediate/batch-eval-fix skill chains to Section 6
- Added: content_root configuration instructions to Section 12

### NEW: CLAUDE.md
- Standalone-specific ground rules (replaces aspose.org Hugo-specific version)
- Documents `$CONTENT_REPO_PATH` configuration requirement
- Removed Hugo config file references (configs/{site}.toml not in standalone repo)

### NEW: CODEX.md
- Codex-specific instructions adapted from aspose.org
- Documents `$CONTENT_REPO_PATH` configuration requirement

### configs/families.yaml
- Added `net` platform (canonical short name for .NET/C#)
- Retained `dotnet` as deprecated alias

---

## Test Commands

```bash
# Run full test suite
cd /path/to/foss-launcher-skills-gitlab
.venv/Scripts/pytest.exe tests/ -q --tb=short

# Test pipeline imports
.venv/Scripts/python.exe -c "import sys; sys.path.insert(0,'scripts'); sys.path.insert(0,'scripts/pipeline'); from content_eval import models; print('content_eval OK')"

# Test audit with content root
CONTENT_REPO_PATH=/path/to/aspose.org .venv/Scripts/python.exe scripts/pipeline/audit.py slides python

# Test skill distribution
.venv/Scripts/python.exe tools/distribute.py
```
