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
