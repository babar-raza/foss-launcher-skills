# Dependency Strategy — foss-launcher-skills ↔ foss-launcher

> Date: 2026-03-19
> Scope: How this product should depend on launcher core

---

## Recommended Boundary: Adapter Pattern with CLI-First, Library-Second

All launcher dependencies flow through a single adapter module (`src/foss_launcher_skills/adapters/launcher.py`). The adapter:
1. Tries launcher CLI/library import first
2. Falls back to local scripts if launcher unavailable
3. Validates output format before passing to evidence pipeline
4. Never exposes launcher internals to product code

---

## Per-Module Dependency Decisions

### scripts/scout.py → IMPORT via adapter

| Aspect | Decision |
|--------|----------|
| **Strategy** | Phase 1: CLI call. Phase 2: library import. |
| **Phase 1 interface** | `python -m launcher.intake.scout {family} {platform} {repo-path} {output-dir}` |
| **Phase 2 interface** | `from launcher.intake import scout; result = scout(family, platform, repo_path, output_dir)` |
| **Output contract** | `{output-dir}/model.yaml`, `api_surface.json`, `claims.json`, `formats.json`, `class_graph.json` (optional), `limitations.md` (optional), `snippets/` (optional) |
| **Launcher must provide** | Stable CLI with documented output contract. Accept explicit parameters, not launcher config. |
| **Fallback** | Keep local `scout.py` behind adapter. Used when launcher is not installed. |
| **Risk** | Launcher CLI may not exist yet. Local fallback mitigates. |
| **Why import** | 1,755 lines of tree-sitter grammar tracking across 6 languages. Highest maintenance cost in the repo. Launcher already does this. |

### scripts/discover.py → IMPORT via adapter

| Aspect | Decision |
|--------|----------|
| **Strategy** | Phase 1: CLI call. Phase 2: library import. |
| **Phase 1 interface** | `python -m launcher.intake.discover --config {config-path} --output {manifest.json}` |
| **Phase 2 interface** | `from launcher.intake import discover; repos = discover(orgs, config)` |
| **Output contract** | JSON array of `{family, platform, repo_url, stars, language, last_updated, ...}` |
| **Launcher must provide** | Stable discover CLI/function returning JSON manifest. |
| **Fallback** | Keep local `discover.py` behind adapter. |
| **Risk** | Same as scout. |
| **Why import** | 574 lines explicitly adapted from launcher's org_scanner.py. Identical purpose. |

### scripts/golden_index.py → IMPORT via adapter (Phase 2 only)

| Aspect | Decision |
|--------|----------|
| **Strategy** | Phase 2: library import only (no CLI needed — golden is read-only). |
| **Interface** | `from launcher.golden import build_golden_index; index = build_golden_index(golden_dir)` |
| **Output contract** | `GoldenIndex` dataclass with `pages`, `role_variant_map`, `tier_selection` |
| **Launcher must provide** | `launcher.golden` module with `build_golden_index()` function and `GoldenIndex` type. |
| **Fallback** | Keep local `golden_index.py` behind adapter. |
| **Risk** | Golden format may drift between repos. Pin golden corpus format version. |
| **Why import** | 410 lines ported from launcher's golden_loader.py. Golden corpus is launcher's asset. |

### scripts/golden_conformance.py → IMPORT via adapter (Phase 2 only)

| Aspect | Decision |
|--------|----------|
| **Strategy** | Phase 2: library import only. |
| **Interface** | `from launcher.evaluate.golden import conformance_score; result = conformance_score(content, template)` |
| **Output contract** | `ConformanceResult` with `score` (0.0–1.0), `dimensions` dict, `pass/fail` flag |
| **Launcher must provide** | `launcher.evaluate.golden` module with `conformance_score()` function. |
| **Fallback** | Keep local `golden_conformance.py` behind adapter. |
| **Risk** | Scorer dimensions/weights may change. Define minimum interface. |
| **Why import** | 438 lines ported from launcher's evaluate/checks/golden_conformance.py. |

### scripts/merge.py → KEEP local permanently

| Aspect | Decision |
|--------|----------|
| **Strategy** | Keep in product. Not a launcher import candidate. |
| **Reason** | Boundary-layer script (510 lines). Consumes scout output and produces evidence pipeline input. It's the glue between launcher's knowledge extraction and this product's evidence pipeline. Moving it to launcher would create a circular dependency. |

### scripts/index.py → KEEP local permanently

| Aspect | Decision |
|--------|----------|
| **Strategy** | Keep in product. Not a launcher import candidate. |
| **Reason** | Thin (197 lines). Derives product-specific metadata from merged artifacts. No launcher equivalent needed. |

### scripts/refresh_golden.py → KEEP local, simplify

| Aspect | Decision |
|--------|----------|
| **Strategy** | Keep as optional utility. Simplify to accept configurable source path. |
| **Reason** | 133 lines. Simple file copy. Not worth the adapter overhead. |
| **Change needed** | Remove hardcoded launcher filesystem assumptions. Accept `--source` argument. |

### scripts/corpus_scan.py → KEEP local temporarily

| Aspect | Decision |
|--------|----------|
| **Strategy** | Keep for now. Re-evaluate when launcher adds content profiling. |
| **Reason** | 388 lines. Somewhat unique to this product's golden anchoring pattern. Low overlap with launcher. |

### scripts/embed.py → KEEP local temporarily

| Aspect | Decision |
|--------|----------|
| **Strategy** | Keep for now. Re-evaluate when launcher adds vector store support. |
| **Reason** | 447 lines. Independent dual-tier embedding. No clear launcher equivalent today. |

---

## What Must NEVER Be Imported Directly

These launcher internals must not leak into foss-launcher-skills:

1. **Launcher configuration objects** — Launcher has its own config.yaml, config model, and config loading. This product has its own. Mixing them creates coupling.
2. **Launcher internal state management** — Database connections, evaluation pipeline state, web API sessions.
3. **Launcher web API contracts or authentication** — This product operates locally via CLI/files, not launcher's HTTP surface.
4. **Launcher singletons or global state** — No `launcher.app`, no `launcher.context`, no global registries.
5. **Launcher's content generation logic** — This product IS the content generation layer. Importing launcher's generation would create an identity crisis.
6. **Launcher's evaluation pipeline** — Beyond golden_conformance, the evaluation subsystem has different goals. Evidence pipeline here replaces it for this product's purposes.

---

## Versioning Strategy

### Launcher Compatibility Range
```yaml
# In config.yaml
launcher_compat: ">=0.5,<1.0"  # semver range of compatible launcher versions
```

The adapter checks `launcher.__version__` on import and warns if outside range.

### Golden Corpus Format Version
```json
// In golden/_index.json
{ "schema_version": 1, ... }
```

The adapter validates `schema_version` matches expected version before using golden data.

### Evidence Artifact Versions
All evidence artifacts already include `schema_version`:
- PEF: `"schema_version": 1`
- Mental model: `"schema_version": 1`
- Verification: `"schema_version": 1`
- Decision: `"schema_version": 1`
- Diff: `"schema_version": 1`

Validators handle version-specific logic. Bumping schema_version triggers migration.

### Scout Output Contract Version
Define a `SCOUT_OUTPUT_VERSION = 1` constant. The adapter validates scout output includes a version marker and matches expected format before passing to merge.

---

## Launcher Refactors Required (Before Phase 2 Import Becomes Safe)

These changes must happen in foss-launcher before this product can safely import:

### 1. Extract `launcher.intake.scout` as Stable Module
- Accept explicit parameters: `scout(family, platform, repo_path, output_dir)`
- Do NOT require launcher config, database connection, or global state
- Document output contract (files, schemas, optional/required)
- Publish as part of `launcher.intake` package

### 2. Extract `launcher.intake.discover` as Stable Module
- Accept explicit parameters: `discover(orgs, config_dict)` → list of repo dicts
- Do NOT require launcher config
- Document JSON manifest schema

### 3. Extract `launcher.golden` as Read-Only Module
- `build_golden_index(golden_dir) → GoldenIndex`
- `conformance_score(content, template) → ConformanceResult`
- Pure functions, no side effects, no global state
- Publish typed dataclasses: `GoldenIndex`, `GoldenPage`, `ConformanceResult`

### 4. Publish Stable Data Classes
- `ScoutResult` — typed container for scout output paths
- `GoldenIndex` — typed container for golden index data
- `ConformanceResult` — typed container for conformance scores
- These must be importable without pulling in all of launcher

### 5. Version and Tag Stable Interfaces
- Semantic versioning for `launcher.intake` and `launcher.golden`
- Breaking changes require major version bump
- This product's adapter pins to compatible range

---

## Adapter Architecture

```
src/foss_launcher_skills/adapters/launcher.py

class LauncherAdapter:
    """Single point of contact with foss-launcher.

    Tries launcher import/CLI first, falls back to local scripts.
    Validates all outputs before returning to callers.
    """

    def scout(self, family, platform, repo_path, output_dir) -> ScoutResult:
        # Try: launcher library import
        # Fallback: subprocess call to local scripts/scout.py
        # Validate: output files exist and match expected format

    def discover(self, config_path) -> list[dict]:
        # Try: launcher library import
        # Fallback: subprocess call to local scripts/discover.py
        # Validate: JSON manifest format

    def build_golden_index(self, golden_dir) -> dict:
        # Try: launcher library import
        # Fallback: local scripts/golden_index.py
        # Validate: schema_version match

    def conformance_score(self, content, template) -> dict:
        # Try: launcher library import
        # Fallback: local scripts/golden_conformance.py
        # Validate: score dimensions present
```

The adapter is the ONLY file that imports from launcher or calls launcher CLI. All other product code imports from the adapter. This isolates every launcher change to a single file.
