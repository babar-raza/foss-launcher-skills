# Migration Plan — foss-launcher-skills

> Date: 2026-03-19
> Target: Model B (Semi-Embedded) architecture
> Phases: 7 (Phase 0–6), safe-first ordering

---

## Principles

1. **Tests green at every phase** — no phase that degrades test health
2. **Backward compatible** — `python scripts/X.py` keeps working throughout
3. **Independently reversible** — git tag at each phase boundary
4. **Launcher not required** — product works standalone at every phase
5. **No data loss** — existing runtime data is migrated, not destroyed

---

## Phase 0: Fix What Is Broken

**Goal**: Green test suite, no behavioral changes.
**Risk**: Zero. No logic changes.
**Duration estimate**: Not provided (per instructions).

### Steps

1. **Create `tests/conftest.py`** with shared fixtures:
   - `minimal_config(tmp_path)` — valid config.yaml dict with all required keys
   - `sample_pef()` — valid PEF dict
   - `knowledge_tree(tmp_path)` — creates knowledge/{family}/{platform}/merged/ with model.yaml, claims.json, api_surface.json, formats.json
   - `evidence_tree(tmp_path)` — creates evidence/{family}/{platform}/ with pef.json, mental_model.json

2. **Address 15 scout test failures** (all in `test_scout_units.py`):
   - Root cause: `tree_sitter_language_pack` not importable in test subprocess context
   - Fix: Add `@pytest.mark.slow` or `@pytest.mark.scout` marker and skip when tree-sitter unavailable
   - Document tree-sitter setup in test requirements / README
   - Non-scout tests (210/227) already pass — no config mocking needed

3. **Create `configs/schemas/config.schema.json`**:
   - Define all required keys: `content_repo`, `sites`, `knowledge_path`, `evidence_path`, `forbidden_paths`, `governance`
   - Define all optional keys: `data_root`, `golden_dir`, `golden_corpus`, `intake_config`, `families_config`
   - Enforce types and structure

4. **Fix `config.yaml` content_repo**:
   - Change absolute path to empty string with comment: "Override with $CONTENT_REPO_PATH"
   - This is a config value change, not a logic change

5. **Remove `skills.zip` from repo** — add to `.gitignore`

### Proof
- `pytest` passes with 0 failures
- All existing passing tests still pass
- No file moves, no import changes, no logic changes

### Rollback
- Revert conftest.py addition and test fixture changes

---

## Phase 1: Python Package Structure

**Goal**: Proper Python package without changing behavior.
**Risk**: Low. Import paths change but wrappers maintain backward compat.

### Steps

1. **Create package directory**:
   ```
   src/foss_launcher_skills/__init__.py
   src/foss_launcher_skills/evidence/__init__.py
   src/foss_launcher_skills/knowledge/__init__.py
   ```

2. **Move evidence scripts** into package:
   - `scripts/materialize.py` → `src/foss_launcher_skills/evidence/materialize.py`
   - `scripts/mental_model.py` → `src/foss_launcher_skills/evidence/mental_model.py`
   - `scripts/verify.py` → `src/foss_launcher_skills/evidence/verify.py`
   - `scripts/decide.py` → `src/foss_launcher_skills/evidence/decide.py`
   - `scripts/differ.py` → `src/foss_launcher_skills/evidence/differ.py`

3. **Move boundary layer scripts** into package:
   - `scripts/merge.py` → `src/foss_launcher_skills/knowledge/merge.py`
   - `scripts/index.py` → `src/foss_launcher_skills/knowledge/index.py`

4. **Move utilities** into package:
   - `scripts/config_loader.py` → `src/foss_launcher_skills/config.py`
   - `scripts/schema_validate.py` → `src/foss_launcher_skills/schema_validate.py`

5. **Create backward-compatible wrappers** in `scripts/`:
   ```python
   # scripts/materialize.py (wrapper)
   """Backward-compatible wrapper. Delegates to foss_launcher_skills.evidence.materialize."""
   import sys
   from pathlib import Path
   sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
   from foss_launcher_skills.evidence.materialize import main
   if __name__ == "__main__":
       main()
   ```

6. **Create `pyproject.toml`** with:
   - Package definition pointing to `src/`
   - Dependencies: pyyaml>=6.0
   - Optional dependencies: scout, golden, embed, dev
   - Entry points: fls-materialize, fls-mental-model, fls-verify, fls-decide, fls-differ, fls-merge, fls-index

7. **Update all test imports** to use package paths:
   ```python
   # Before:
   sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
   import materialize

   # After:
   from foss_launcher_skills.evidence import materialize
   ```

8. **Update internal imports** within moved scripts:
   ```python
   # Before (in materialize.py):
   from config_loader import resolve_evidence_path
   from schema_validate import validate

   # After:
   from foss_launcher_skills.config import resolve_evidence_path
   from foss_launcher_skills.schema_validate import validate
   ```

### Proof
- `pip install -e .` succeeds
- `pytest` green
- `fls-materialize --help` works
- `python scripts/materialize.py --help` works (via wrapper)

### Rollback
- Move files back to scripts/, remove src/ and pyproject.toml

---

## Phase 2: Config Consolidation

**Goal**: Single source of truth for all paths. No hardcoded bypasses.
**Risk**: Medium. Path resolution changes could affect behavior.

### Steps

1. **Add `data_root` key** to config.yaml:
   ```yaml
   data_root: ""  # empty = platform default. "." for development.
   ```

2. **Add `FLS_DATA_ROOT` env var support** in config.py:
   ```python
   def resolve_data_root(config: dict) -> Path:
       env = os.environ.get("FLS_DATA_ROOT")
       if env:
           return Path(env)
       cfg = config.get("data_root", "")
       if cfg:
           return Path(cfg)
       # Platform default
       if sys.platform == "win32":
           return Path.home() / ".foss-launcher-skills"
       return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share")) / "foss-launcher-skills"
   ```

3. **Replace hardcoded paths** in evidence scripts:
   ```python
   # Before:
   EVIDENCE_ROOT = Path("evidence")
   KNOWLEDGE_ROOT = Path("knowledge")

   # After:
   from foss_launcher_skills.config import load_config
   cfg = load_config()
   EVIDENCE_ROOT = cfg["resolved_evidence_root"]
   KNOWLEDGE_ROOT = cfg["resolved_knowledge_root"]
   ```

4. **Add config schema validation** on load:
   ```python
   def load_config(...):
       # ... load YAML ...
       validate(config, schema_name="config")  # validates against config.schema.json
       # ... resolve paths ...
   ```

5. **Add config caching** with mtime invalidation:
   ```python
   _cache = None
   _cache_mtime = 0.0

   def load_config(config_path=None):
       global _cache, _cache_mtime
       path = _find_config(config_path)
       mtime = path.stat().st_mtime
       if _cache and mtime == _cache_mtime:
           return _cache
       # ... reload ...
   ```

6. **Fix `content_repo`** to be empty by default, with env var override documented

7. **Update tests** to use config fixtures consistently

### Proof
- `pytest` green
- `python -c "from foss_launcher_skills.config import load_config; load_config()"` succeeds
- No `Path("evidence")` or `Path("knowledge")` hardcoded in evidence scripts (verified by grep)

### Rollback
- Revert config.py changes, restore hardcoded paths in evidence scripts

---

## Phase 3: Source/Runtime Split

**Goal**: Runtime data out of source tree.
**Risk**: Low-medium. Existing users with data in repo tree need migration path.

### Steps

1. **Update `.gitignore`**:
   ```
   # Runtime data (moved to $data_root)
   knowledge/
   evidence/
   output/
   reports/
   plans/
   golden/
   ```
   Exception: `reports/skills-product-audit/` is a one-time source artifact, committed before gitignore change.

2. **Add backward-compatible fallback** in config.py:
   ```python
   def resolve_data_root(config):
       # ... env var and config checks ...
       # Backward compat: if data_root is empty AND old directories exist, use "."
       project_root = _find_project_root()
       if (project_root / "evidence").is_dir() or (project_root / "knowledge").is_dir():
           return project_root  # Use legacy in-repo layout
       return _platform_default()
   ```

3. **Create data migration helper**:
   ```python
   # src/foss_launcher_skills/migrate.py
   def migrate_data_to_data_root():
       """Move runtime data from project tree to $data_root."""
       # For each runtime directory: knowledge, evidence, output, reports, plans, golden
       # If exists in project root AND data_root != project root:
       #   Copy to data_root, verify, then offer to remove originals
   ```

4. **Update AGENTS.md** paths section to reference configurable data_root

5. **Update install scripts** to create data directories at `$data_root`

### Proof
- Fresh clone has no knowledge/, evidence/, output/, reports/, plans/, golden/ directories
- `FLS_DATA_ROOT=. pytest` passes (development mode)
- Existing setups with data in repo tree still work (backward compat fallback)

### Rollback
- Revert .gitignore changes, remove migration helper

---

## Phase 4: Multi-Agent Manifest Enhancement

**Goal**: Rich skill metadata for production multi-agent support.
**Risk**: Low. All changes are additive to existing frontmatter.

### Steps

1. **Create `configs/schemas/skill_manifest.schema.json`**:
   - Required: name, id, description, args
   - Optional with defaults: version, execution, requires, safety, depends_on, required_by, produces, consumes, agent_hints

2. **Extend frontmatter in all 36 skills**:
   - Add `execution` block (mode, entry, timeout, idempotent)
   - Add `requires` list (agent capabilities needed)
   - Add `safety` block (autonomy_tier, write_paths, max_output_files)
   - Add `depends_on` / `required_by` lists
   - Add `produces` / `consumes` lists
   - Add `agent_hints` block

3. **Update `tools/distribute.py`**:
   - Parse full manifest (not just frontmatter/body split)
   - Validate against skill_manifest.schema.json
   - Generate per-agent install manifests:
     - `.claude/skills.json`
     - `.agents/manifest.json`
     - `.kilocode/manifest.json`
   - Validate skill chain DAG (no cycles, no orphans)
   - Warn on capability mismatches per agent
   - Add `--validate` flag for CI

4. **Add tests** for:
   - Manifest parsing and field extraction
   - Schema validation of all 36 skills
   - DAG validation (happy path + intentional cycle detection)
   - Per-agent manifest generation

### Proof
- `python tools/distribute.py --validate` exits 0
- All 36 skills pass schema validation
- `.claude/skills.json`, `.agents/manifest.json`, `.kilocode/manifest.json` generated
- DAG validation catches intentionally injected cycle

### Rollback
- Revert frontmatter additions (old fields preserved, new fields removed)
- Revert distribute.py enhancements

---

## Phase 5: Launcher Adapter Boundary

**Goal**: Replace copied scripts with adapter-mediated launcher consumption.
**Risk**: Medium. Adapter must correctly fall back to local scripts.

### Prerequisite
Launcher must have started extracting stable interfaces (see dependency-strategy.md). If launcher has not stabilized, this phase can be deferred indefinitely — the product works with local scripts.

### Steps

1. **Create adapter module**:
   ```
   src/foss_launcher_skills/adapters/__init__.py
   src/foss_launcher_skills/adapters/launcher.py
   ```

2. **Implement adapter** with try/fallback pattern:
   ```python
   class LauncherAdapter:
       def scout(self, family, platform, repo_path, output_dir):
           try:
               return self._scout_via_launcher(...)
           except (ImportError, FileNotFoundError):
               return self._scout_local(...)

       def _scout_via_launcher(self, ...):
           # Try library import, then CLI subprocess

       def _scout_local(self, ...):
           # Run scripts/scout.py directly
   ```

3. **Update skill instructions** (S-34, S-39) to reference adapter:
   - Instead of `python scripts/scout.py {args}`
   - Use `fls-scout {args}` (new entry point that goes through adapter)
   - Or keep current invocation with adapter as internal implementation

4. **Move golden scripts behind adapter**:
   - `golden_index.py` → adapter.build_golden_index()
   - `golden_conformance.py` → adapter.conformance_score()

5. **Make tree-sitter optional**:
   - `tree-sitter` in `[project.optional-dependencies.scout]`
   - Adapter gracefully handles missing tree-sitter: "Install with `pip install foss-launcher-skills[scout]`"

6. **Add adapter tests**:
   - Mock launcher import: test that adapter uses launcher when available
   - Mock launcher import failure: test that adapter falls back to local scripts
   - Validate output format from both paths

### Proof
- `pytest` green
- With launcher installed: adapter uses launcher
- Without launcher: adapter uses local fallback
- Skills execute correctly through both paths

### Rollback
- Remove adapter module, revert skill instructions to direct script calls

---

## Phase 6: CI/CD and Release

**Goal**: Automated quality and distribution.
**Risk**: Low. CI configuration only.

### Steps

1. **CI pipeline** (GitHub Actions / GitLab CI):
   ```yaml
   test:
     - pip install -e .[dev]
     - pytest --tb=short -q
     - python tools/distribute.py --validate

   lint:
     - validate config.yaml against schema
     - validate all skill frontmatter against schema
     - check no sys.path.insert in src/

   distribute:
     - python tools/distribute.py
     - verify output directories populated
   ```

2. **Release workflow**:
   - Tag triggers build
   - Generate `skills.zip` from `skills/` + `configs/`
   - Run distribute.py and include agent outputs
   - Publish to internal PyPI or GitHub Releases

3. **Version management**:
   - Version in `pyproject.toml` and `src/foss_launcher_skills/__init__.py`
   - Tag-based: `v0.1.0`, `v0.2.0`, etc.

### Proof
- CI pipeline green on main branch
- Tagged release produces distributable package

### Rollback
- Remove CI configuration files

---

## Phase Ordering and Dependencies

```
Phase 0 (fix tests)
  └→ Phase 1 (package structure)
       ├→ Phase 2 (config consolidation)
       │    └→ Phase 3 (source/runtime split)
       └→ Phase 4 (multi-agent manifest)
            └→ Phase 5 (launcher adapter) [can be deferred]
                 └→ Phase 6 (CI/CD)
```

- Phase 0 is prerequisite for everything
- Phase 1 is prerequisite for Phase 2, 3, 4
- Phase 2 and Phase 4 can run in parallel
- Phase 3 depends on Phase 2 (needs data_root)
- Phase 5 depends on Phase 4 (adapter referenced in manifest)
- Phase 5 can be deferred indefinitely
- Phase 6 can run after any phase

---

## Rollback Strategy Summary

| Phase | Rollback Method | Data Loss Risk |
|-------|----------------|----------------|
| 0 | Revert conftest.py and test changes | None |
| 1 | Move files back from src/ to scripts/ | None |
| 2 | Restore hardcoded paths in scripts | None |
| 3 | Revert .gitignore, restore runtime dirs to repo | None (data migration is copy, not move) |
| 4 | Remove new frontmatter fields | None (additive only) |
| 5 | Remove adapter, revert to direct script calls | None |
| 6 | Remove CI config | None |

Git tags at each phase boundary: `v0.0.1-phase0`, `v0.0.2-phase1`, etc.

---

## Required Launcher-Side Work (Prerequisite for Phase 5)

| Launcher Refactor | Priority | Blocks |
|-------------------|----------|--------|
| Extract `launcher.intake.scout` as stable CLI | High | Phase 5 scout adapter |
| Extract `launcher.intake.discover` as stable CLI | High | Phase 5 discover adapter |
| Extract `launcher.golden` as read-only module | Medium | Phase 5 golden adapter |
| Publish typed data classes (ScoutResult, GoldenIndex) | Medium | Phase 5 type safety |
| Ensure modules work without launcher config | High | Phase 5 isolation |

If launcher does not complete these, Phase 5 simply keeps using local scripts. The adapter fallback path is the permanent fallback.
