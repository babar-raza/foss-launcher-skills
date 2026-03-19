# Target Architecture — foss-launcher-skills

> Date: 2026-03-19
> Recommendation: Model B — Semi-Embedded with hard ownership lines

---

## Product Model Decision

### Recommendation: Model B — Semi-Embedded

**Own locally**: Skills, evidence pipeline, distribution, governance, schemas, config, boundary-layer knowledge scripts (merge, index).

**Consume from launcher**: Knowledge extraction (scout, discover), golden corpus handling (golden_index, golden_conformance). Through a defined adapter boundary with local fallback.

### Why Not Model A (Thin Adapter)

Model A assumes most logic lives in launcher and this repo is just skills + packaging. This fails because:

- The evidence pipeline (materialize, mental_model, verify, decide, differ — 1,515 lines) is genuinely NEW IP that doesn't exist in launcher. There's nothing to import.
- The governance model (AGENTS.md, config.yaml governance section) is product-specific, not launcher-generic.
- The golden anchoring pattern (corpus_scan integration with evidence pipeline) is unique to this product's approach.

A thin adapter would either need to push the evidence pipeline into launcher (wrong — it's product-specific) or leave it local (making "thin adapter" a fiction).

### Why Not Model C (Self-Contained)

Model C means permanently maintaining all pipeline code locally. This fails because:

- `scout.py` (1,755 lines) tracks tree-sitter grammars across 6 languages. Every grammar update, new language, or AST parsing fix must be done independently from launcher. This is duplicated maintenance.
- `discover.py` (574 lines) is explicitly adapted from launcher's org_scanner. Maintaining it separately guarantees silent drift.
- `golden_index.py` and `golden_conformance.py` (848 lines combined) are ported from launcher's evaluate subsystem. Same drift risk.
- Total: ~3,175 lines of code that launcher already maintains. Keeping it local means double the bug surface.

### Why Model B Works

Model B draws the correct line between what this product uniquely owns and what it should consume:

| Owned | Consumed | Bridge |
|-------|----------|--------|
| Evidence pipeline (1,513 lines NEW) | Scout (1,755 lines — launcher) | Merge (509 lines — glue) |
| Skills (36 definitions) | Discover (574 lines — launcher) | Index (196 lines — glue) |
| Distribution, governance, schemas | Golden handling (848 lines — launcher) | |
| Config, tests, packaging | | |

The adapter pattern means:
- When launcher is available → consume through stable interface
- When launcher is unavailable → fall back to local copies
- Product code never directly touches launcher internals
- Migration from local to imported happens behind the adapter, invisible to product code

---

## Module Boundaries

### Product Boundary
Everything inside `src/foss_launcher_skills/` and `skills/` is the product. This includes:
- Evidence pipeline: materialize, mental_model, verify, decide, differ
- Knowledge boundary layer: merge, index
- Config resolution
- Schema validation
- Launcher adapter (single contact point)

### Runtime Boundary
Everything under `$data_root/` is runtime state. This includes:
- knowledge/, evidence/, output/, reports/, plans/, golden/
- Not version-controlled
- Created by pipeline execution
- Configurable location

### Code Ownership Boundary
- `src/foss_launcher_skills/evidence/` — owned by this product, no launcher equivalent
- `src/foss_launcher_skills/knowledge/` — boundary layer, owned by this product
- `src/foss_launcher_skills/adapters/` — integration point, owned by this product
- `scripts/scout.py`, `scripts/discover.py` — local fallbacks, eventually deprecated when launcher stabilizes

### Asset Boundary
- `skills/*.md` — canonical skill definitions (source asset)
- `configs/*.yaml` — product configuration (source asset)
- `configs/schemas/*.json` — evidence contracts (source asset)
- `golden/` — synced asset at `$data_root`, not source

### Config Boundary
- `config.yaml` — product config, never imported from launcher
- `configs/families.yaml` — product taxonomy
- `configs/intake_config.yaml` — discovery scope
- Launcher has its own config. The adapter accepts explicit parameters, never launcher config objects.

### Test Boundary
- `tests/` — product tests, testing product code
- Tests mock launcher adapter, never depend on launcher being installed
- Integration tests use tmp_path fixtures, not real runtime data directories

### Distribution Boundary
- `tools/distribute.py` produces `.claude/`, `.agents/`, `.kilocode/` from `skills/`
- Generated outputs are committed to repo (they are the product's deliverable for agent users)
- Manifests (skills.json, manifest.json) are generated alongside skill files

### Dependency Boundary with Launcher Core
- Single adapter file: `src/foss_launcher_skills/adapters/launcher.py`
- Imports only: data classes (ScoutResult, GoldenIndex, ConformanceResult), pure functions (scout, discover, build_golden_index, conformance_score)
- Never imports: launcher config, launcher state, launcher singletons, launcher web API
- Version pinned: `launcher_compat: ">=0.5,<1.0"` in config.yaml

---

## Target Directory Layout

```
foss-launcher-skills/
│
├── pyproject.toml                              # Package: foss-launcher-skills
├── README.md
├── AGENTS.md                                   # Governance (human-maintained)
├── config.yaml                                 # Site-specific config
├── .gitignore
│
├── src/
│   └── foss_launcher_skills/
│       ├── __init__.py                         # Package root, version
│       ├── config.py                           # Config loading, caching, validation
│       ├── schema_validate.py                  # JSON schema validation utility
│       │
│       ├── evidence/                           # Evidence pipeline (NEW IP)
│       │   ├── __init__.py
│       │   ├── materialize.py                  # PEF builder
│       │   ├── mental_model.py                 # Capability tiers, readiness
│       │   ├── verify.py                       # Content verification
│       │   ├── decide.py                       # Action decision engine
│       │   └── differ.py                       # PEF snapshot comparison
│       │
│       ├── knowledge/                          # Boundary layer
│       │   ├── __init__.py
│       │   ├── merge.py                        # Knowledge consolidation
│       │   └── index.py                        # Knowledge indexing
│       │
│       └── adapters/                           # Launcher integration
│           ├── __init__.py
│           └── launcher.py                     # CLI/import adapter with fallback
│
├── skills/                                     # Canonical skill definitions
│   ├── launch-product.md                       # S-38
│   ├── evidence-materialize.md                 # S-40
│   ├── mental-model.md                         # S-41
│   ├── evidence-verify.md                      # S-42
│   ├── evidence-decide.md                      # S-43
│   ├── repo-scout.md                           # S-34
│   ├── truth-merge.md                          # S-35
│   ├── truth-index.md                          # S-31
│   └── ... (36 total)
│
├── configs/
│   ├── families.yaml                           # 21 families × 13 platforms
│   ├── intake_config.yaml                      # 24 GitHub orgs
│   └── schemas/
│       ├── config.schema.json                  # NEW: config validation
│       ├── skill_manifest.schema.json          # NEW: frontmatter validation
│       ├── pef.schema.json
│       ├── mental_model.schema.json
│       ├── verification.schema.json
│       ├── decision.schema.json
│       └── diff.schema.json
│
├── tools/
│   └── distribute.py                           # Agent distribution engine
│
├── scripts/                                    # Backward-compatible wrappers
│   ├── materialize.py                          # → imports from src/
│   ├── mental_model.py
│   ├── verify.py
│   ├── decide.py
│   ├── differ.py
│   ├── merge.py
│   ├── index.py
│   ├── scout.py                                # Local fallback (adapter uses)
│   ├── discover.py                             # Local fallback (adapter uses)
│   ├── golden_index.py                         # Local fallback (adapter uses)
│   ├── golden_conformance.py                   # Local fallback (adapter uses)
│   ├── corpus_scan.py                          # Keep temporarily
│   ├── embed.py                                # Keep temporarily
│   ├── refresh_golden.py                       # Optional utility
│   └── readme_sync.py                          # README maintenance
│
├── tests/
│   ├── conftest.py                             # Shared fixtures
│   ├── evidence/
│   │   ├── test_materialize.py
│   │   ├── test_mental_model.py
│   │   ├── test_verify.py
│   │   ├── test_decide.py
│   │   └── test_differ.py
│   ├── knowledge/
│   │   ├── test_merge_units.py
│   │   └── test_index.py
│   ├── test_config.py
│   ├── test_schema_validate.py
│   ├── test_distribute.py
│   ├── test_distribute_integration.py
│   └── fixtures/
│       ├── repo/                               # Fixture source repo
│       └── content/                            # Fixture content pages
│
├── .claude/                                    # Generated by distribute.py
│   ├── commands/*.md
│   ├── skills.json                             # NEW: skill index
│   └── settings.local.json
│
├── .agents/                                    # Generated by distribute.py
│   ├── skills/{name}/SKILL.md
│   └── manifest.json                           # NEW: skill index
│
└── .kilocode/                                  # Generated by distribute.py
    ├── skills/{name}/SKILL.md
    └── manifest.json                           # NEW: skill index
```

### Runtime Data (at `$data_root`, NOT in source tree)

```
$data_root/
├── knowledge/{family}/{platform}/
│   ├── scout/                                  # Scout output
│   ├── external/                               # External knowledge
│   └── merged/                                 # Consolidated knowledge
├── evidence/{family}/{platform}/
│   ├── pef.json                                # Product Evidence File
│   ├── pef_previous.json                       # Previous snapshot
│   ├── mental_model.json                       # Capability assessment
│   ├── decision.json                           # Page action decisions
│   ├── changelog.json                          # Materialization history
│   ├── diffs/                                  # Change reports
│   └── verification/                           # Per-page verification
├── golden/                                     # Synced exemplar corpus
│   └── _index.json
├── output/
│   ├── content/                                # Generated pages
│   └── distributed/                            # Agent skill outputs
├── reports/
│   ├── agents/                                 # Audit logs
│   ├── conformance/                            # Golden conformance scores
│   └── launch/                                 # Launch reports
└── plans/                                      # Page plans
```

---

## Packaging Model

### Hybrid: Python Package + Content Assets

```toml
# pyproject.toml
[build-system]
requires = ["setuptools>=68.0"]
build-backend = "setuptools.build_meta"

[project]
name = "foss-launcher-skills"
version = "0.1.0"
description = "Evidence-based content generation skills for FOSS products"
requires-python = ">=3.10"
dependencies = [
    "pyyaml>=6.0",
]

[project.optional-dependencies]
scout = [
    "tree-sitter>=0.25",
    "tree-sitter-language-pack>=0.13",
    "tree-sitter-c-sharp>=0.23",
]
golden = [
    "requests>=2.28",
]
embed = [
    "requests>=2.28",
]
dev = [
    "pytest>=7.0",
    "jsonschema>=4.0",
]
all = [
    "foss-launcher-skills[scout,golden,embed,dev]",
]

[project.scripts]
fls-materialize = "foss_launcher_skills.evidence.materialize:main"
fls-mental-model = "foss_launcher_skills.evidence.mental_model:main"
fls-verify = "foss_launcher_skills.evidence.verify:main"
fls-decide = "foss_launcher_skills.evidence.decide:main"
fls-differ = "foss_launcher_skills.evidence.differ:main"
fls-merge = "foss_launcher_skills.knowledge.merge:main"
fls-index = "foss_launcher_skills.knowledge.index:main"
fls-distribute = "tools.distribute:main"
```

### Install Modes

| Mode | Command | What You Get |
|------|---------|-------------|
| **Minimal** | `pip install foss-launcher-skills` | Evidence pipeline + merge/index. Skills as data. |
| **With local scout** | `pip install foss-launcher-skills[scout]` | + tree-sitter for local knowledge extraction |
| **Full** | `pip install foss-launcher-skills[all]` | Everything including dev dependencies |
| **Development** | `pip install -e .[all]` | Editable install with all extras |

---

## Config Model

### Current Problems
1. No schema validation
2. Absolute developer-machine path in `content_repo`
3. Hardcoded `Path("evidence")` in scripts bypasses config
4. No `data_root` concept
5. No caching (re-reads YAML every call)

### Target Config

```yaml
# config.yaml — all REQUIRED keys shown
data_root: ""                              # Runtime data location
                                           # Empty = platform default:
                                           #   Windows: ~/.foss-launcher-skills/
                                           #   Linux: $XDG_DATA_HOME/foss-launcher-skills/
                                           # "." = project directory (development mode)
                                           # Override: $FLS_DATA_ROOT env var

content_repo: ""                           # Hugo content repo path
                                           # Override: $CONTENT_REPO_PATH env var

sites:
  docs:    { content_path: "content/docs.aspose.org/en/{family}/{platform}/", type: docs }
  blog:    { content_path: "content/blog.aspose.org/{family}/{platform}/", type: blog }
  kb:      { content_path: "content/kb.aspose.org/en/{family}/{platform}/", type: kb }
  products: { content_path: "content/products.aspose.org/en/{family}/", type: products }
  reference: { content_path: "content/reference.aspose.org/en/{family}/{platform}/", type: reference }

knowledge_path: "knowledge/{family}/{platform}/"    # relative to data_root
evidence_path: "evidence/{family}/{platform}/"      # relative to data_root
reports_path: "reports/"                             # relative to data_root
forbidden_paths: [themes/, layouts/, configs/, AGENTS.md, CLAUDE.md, CODEX.md, .claude/, .agents/, .kilocode/, skills/, scripts/]

governance:
  default_role: writer
  roles:
    scout:        { skills: [...], write_paths: [...] }
    writer:       { skills: [...], required_gates: [...], write_paths: [...] }
    reviewer:     { skills: [...], write_paths: [...] }
    orchestrator: { skills: [all], write_paths: [...] }
  session_limits: { max_pages_per_session: 20, max_families_per_session: 3, max_consecutive_fails: 3 }
  audit: { log_path: "reports/agents/" }

# OPTIONAL
golden_dir: "golden/"
golden_corpus: { sample_count: 3, min_words: 200, profile_dir: "_corpus", variant_defaults: { ... } }
intake_config: "configs/intake_config.yaml"
families_config: "configs/families.yaml"
launcher_compat: ">=0.5,<1.0"
```

### Config Loading

```python
# src/foss_launcher_skills/config.py

_cache: dict | None = None
_cache_mtime: float = 0

def load_config(config_path=None) -> dict:
    """Load config.yaml with caching, schema validation, and data_root resolution."""
    # 1. Find config.yaml (walk up from CWD, or use explicit path)
    # 2. Check mtime, return cache if unchanged
    # 3. Parse YAML
    # 4. Validate against configs/schemas/config.schema.json
    # 5. Resolve data_root: $FLS_DATA_ROOT > config value > platform default
    # 6. Resolve all relative paths against data_root
    # 7. Cache and return
```

---

## Launcher Integration Model

See [dependency-strategy.md](dependency-strategy.md) for full details.

Summary:
- Single adapter at `src/foss_launcher_skills/adapters/launcher.py`
- CLI-first (Phase 1), library-import (Phase 2)
- Local fallback for every imported capability
- Validates all launcher output before using
- Never exposes launcher internals

---

## Golden Corpus Strategy

### Current: In-repo synced directory
`golden/` lives in the source tree. `refresh_golden.py` copies from launcher filesystem.

### Target: Runtime asset at `$data_root`
- `golden/` moves to `$data_root/golden/`
- `refresh_golden.py` accepts `--source` argument (no hardcoded launcher path)
- `golden/_index.json` includes `schema_version` for format compatibility
- The adapter can also build golden index from launcher library if available

### Bundled Seed Corpus (Optional)
For first-run experience, package a minimal golden seed as package data. Full corpus synced on first `refresh_golden.py` run.

---

## Observability Strategy

| Layer | Mechanism |
|-------|-----------|
| Script execution | Structured JSON logs at `{data_root}/reports/agents/{session_id}.log` |
| Evidence state | PEF `materialized_at`, mental_model `generated_at`, decision `decided_at` timestamps |
| Change tracking | PEF `changelog.json` — append-only record of every materialization |
| Drift detection | `differ.py` — timestamped diffs between PEF snapshots |
| Content grounding | `verify.py` — `grounded_pct` per page with issue list |
| Quality grading | `eval-page` skill — 6-dimension rubric scores with A–F grades |
| Launch status | Launch reports at `{data_root}/reports/launch/` with COMPLETE/PARTIAL/FAILED status |
| Skill invocation | Audit trail: session ID, skill ID, timestamp, result in agent log |

---

## Test Strategy

### Test Categories

| Category | Speed | What | How |
|----------|-------|------|-----|
| Unit | Fast | Pure functions in evidence pipeline | No filesystem, monkeypatched inputs |
| Integration | Medium | Evidence pipeline end-to-end | tmp_path fixtures with full directory trees |
| Contract | Fast | Schema validation of all artifact types | Load schema, validate sample data |
| Distribution | Fast | Skill parsing, manifest generation | tmp_path with skill fixtures |
| Config | Fast | Config loading, path resolution | monkeypatch environment, tmp config |
| Adapter | Fast | Launcher adapter with mocked launcher | Mock subprocess/import, test fallback |

### Shared Fixtures (conftest.py)

```python
@pytest.fixture
def minimal_config(tmp_path):
    """Valid config.yaml with all required keys, data_root pointing to tmp_path."""

@pytest.fixture
def sample_pef():
    """Valid PEF dict for evidence pipeline tests."""

@pytest.fixture
def knowledge_tree(tmp_path):
    """Full knowledge/{family}/{platform}/merged/ tree."""

@pytest.fixture
def evidence_tree(tmp_path):
    """Full evidence/{family}/{platform}/ tree with pef.json."""
```

### Import Strategy
- All imports via package: `from foss_launcher_skills.evidence.materialize import materialize`
- No `sys.path.insert` hacks
- `pip install -e .` before running tests

### CI Pipeline
```
pytest --tb=short -q                  # All tests
pytest -m "not slow" --tb=short -q    # Fast tests only (exclude tree-sitter, network)
python tools/distribute.py --validate  # Skill manifest validation
```

---

## Migration Constraints

1. **Backward compatibility during migration**: `python scripts/X.py` must continue working via wrapper scripts
2. **No big-bang**: Each phase is independently shippable and reversible
3. **Tests green at every phase**: No phase that makes tests worse before making them better
4. **Launcher not required**: Product must work standalone with local fallbacks at all times
5. **Data migration**: Existing runtime data in repo tree must be movable, not destroyed
6. **Agent outputs stable**: distribute.py output format changes are additive, not breaking
