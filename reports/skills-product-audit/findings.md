# Critical Findings — foss-launcher-skills Product Audit

> Date: 2026-03-19
> Status: Audit complete. Actionable findings below.

---

## Finding 1: The Repo Is a Partial Launcher Clone, Not a Thin Skills Layer

**Severity**: Critical — affects product identity and maintenance strategy

The repo contains 6,891 lines of Python pipeline code (verified via `wc -l`). Of those, 3,175 lines duplicate or parallel foss-launcher core logic:

| Script | Lines | Launcher Equivalent |
|--------|-------|-------------------|
| `scout.py` | 1,755 | `launcher.intake.scout` |
| `discover.py` | 574 | `launcher.intake.org_scanner` |
| `golden_conformance.py` | 438 | `launcher.evaluate.checks.golden_conformance` |
| `golden_index.py` | 410 | `launcher.golden_loader` |
| **Total duplicated** | **3,175** | |

Only the evidence pipeline (1,515 lines: materialize, mental_model, verify, decide, differ) is genuinely new. The repo's actual identity is "semi-embedded launcher with an evidence pipeline extension", not "standalone skills library".

**Impact**: Duplicated code will silently drift from launcher. Bug fixes in launcher won't propagate. Maintenance cost is roughly doubled.

**Recommendation**: Phase 5 of migration plan — adapter boundary with local fallback.

---

## Finding 2: 15 Test Failures from tree-sitter Dependency in Scout Subprocess

**Severity**: High — test suite does not pass cleanly

Actual test results (verified 2026-03-19): **15 failed, 212 passed in 26.76s**.

All 15 failures are in `test_scout_units.py`. Every failure has the same root cause: tests invoke `scripts/scout.py` as a subprocess, and the subprocess cannot import `tree_sitter_language_pack`. The module is installed in user site-packages but not available to the subprocess Python path.

Excluding scout tests: **210 passed, 0 failed** — all non-scout tests are green.

This is significant because:
- Scout is the largest script (1,755 lines) and the primary import candidate for launcher
- The tree-sitter dependency is the single biggest maintenance burden (6 language grammars)
- Test isolation depends on subprocess execution, which is fragile with user-site-packages

Separately, `config.yaml` line 9 contains an absolute developer-machine path:
```yaml
content_repo: "/c/Users/prora/OneDrive/Documents/GitHub/foss-launcher-skills/output/install-test"
```
No config schema exists to validate this. The config contract gap is real but does NOT currently cause test failures — evidence pipeline tests properly use monkeypatched paths.

**Impact**: 15/227 tests fail. Scout tests are not runnable without explicit tree-sitter setup. Config is fragile for new contributors.

**Recommendation**: Phase 0 (document tree-sitter setup in test requirements). Phase 2 (config schema + validation). Phase 5 (move scout to launcher adapter, eliminating the dependency).

---

## Finding 3: Three Scripts Explicitly Ported from Launcher with No Update Mechanism

**Severity**: High — guaranteed silent drift

These scripts were copied from launcher and will diverge:

| Script | Declared Origin |
|--------|----------------|
| `discover.py` | "Adapted from foss-launcher/src/launcher/intake/org_scanner.py" |
| `golden_index.py` | "Ported from foss-launcher's golden_loader.py" |
| `golden_conformance.py` | "Ported from foss-launcher's evaluate/checks/golden_conformance.py" |

There is no mechanism to:
- Detect when launcher's original has changed
- Merge launcher changes into local copies
- Verify compatibility between local copy and launcher version
- Track which launcher version the local copy was ported from

**Impact**: Logic drift will cause subtle correctness bugs. Golden corpus handling may break silently when launcher changes golden format.

**Recommendation**: Phase 5 adapter with launcher version pinning and format version validation.

---

## Finding 4: Multi-Agent Support Is File-Copy Formatting Only

**Severity**: Medium — limits product capability

`tools/distribute.py` treats multi-agent support as a file format problem:
- Claude Code: strip YAML frontmatter, keep markdown body
- Codex CLI: keep full file
- Kilo Code: keep full file

No differentiation between Codex and Kilo Code. No capability awareness (some agents can't execute Python). No dependency chain validation. No install manifest. No argument schemas. No output contracts.

**Impact**:
- Skills requiring Python execution get distributed to agents that can't run Python
- No machine-readable skill index for agents to discover capabilities
- Skill chains are documented in prose (AGENTS.md) but not machine-validated
- Agent integrations will break silently if skill format expectations change

**Recommendation**: Phase 4 — extended manifest schema + enhanced distribute.py.

---

## Finding 5: Runtime State Mixed with Source Code

**Severity**: Medium — affects installs, CI, and developer experience

These directories exist in the source tree alongside code:

| Directory | Content | Size |
|-----------|---------|------|
| `knowledge/` | Extracted knowledge artifacts (JSON, YAML, markdown) | Variable |
| `evidence/` | PEF, mental models, verification reports | Variable |
| `output/` | Generated content, install tests | Variable |
| `golden/` | Curated exemplar files | ~100+ files |
| `reports/` | Audit logs, conformance reports | Variable |
| `plans/` | Page plans, healing workflows | Variable |
| `repos/` | Cloned FOSS repositories | Large |

**Impact**:
- Fresh clones include stale runtime data
- CI must carefully gitignore or clean up
- Developer's local state leaks into commits
- `git status` is noisy
- Install size is unpredictable

**Recommendation**: Phase 3 — move to configurable `$data_root` outside source tree.

---

## Finding 6: No Python Package Boundary

**Severity**: Medium — blocks clean installation and distribution

The repo has no `pyproject.toml`, `setup.py`, or `setup.cfg`. Scripts use `sys.path.insert(0, ...)` to find each other:

```python
# Common pattern in test files:
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
import materialize
```

**Impact**:
- Not installable via `pip`
- No entry points for CLI access
- Import hacks are fragile and non-standard
- Cannot be depended upon by other packages
- Type checking and IDE support degraded

**Recommendation**: Phase 1 — `src/foss_launcher_skills/` package with pyproject.toml.

---

## Finding 7: Hardcoded Paths Bypass Config System

**Severity**: Medium — config_loader is partially decorative

Evidence scripts define module-level constants that bypass config_loader:

```python
# materialize.py
EVIDENCE_ROOT = Path("evidence")
KNOWLEDGE_ROOT = Path("knowledge")

# verify.py
EVIDENCE_ROOT = Path("evidence")

# mental_model.py
EVIDENCE_ROOT = Path("evidence")

# decide.py
EVIDENCE_ROOT = Path("evidence")
```

These make the config system's `evidence_path` and `knowledge_path` settings irrelevant for the evidence pipeline — the most important code in the repo.

**Impact**: Changing config paths doesn't actually change where evidence scripts read/write. The config system provides a false sense of control.

**Recommendation**: Phase 2 — replace with config-resolved paths.

---

## Finding 8: Golden Corpus Sync Depends on Launcher Filesystem Assumptions

**Severity**: Medium — fragile external dependency

`refresh_golden.py` syncs golden corpus from a hardcoded-style path:
```python
# Default source derived from config or command-line
# But ultimately assumes launcher's golden/ directory layout
```

If launcher restructures its `golden/` directory (renames, reorganizes, changes format), `refresh_golden.py` will silently break or produce corrupted index data.

**Impact**: Golden corpus (used for structural conformance scoring) could become stale or invalid without warning.

**Recommendation**: Add golden format version check. Simplify refresh_golden.py to accept explicit `--source` path. Put golden behind adapter in Phase 5.

---

## Finding 9: No Versioning Contract with Launcher

**Severity**: Medium — no compatibility safety net

There is no mechanism to:
- Declare which launcher version this product is compatible with
- Check launcher version before using imported capabilities
- Validate that scout output format matches expected schema
- Validate that golden index format matches expected schema

**Impact**: Any launcher change could break this product without warning. No way to pin to a known-good launcher version.

**Recommendation**: Add `launcher_compat` to config.yaml. Add format version checks in adapter. Pin golden `schema_version`.

---

## Finding 10: scout.py Is the Highest-Maintenance Liability

**Severity**: Medium — ongoing maintenance burden

`scout.py` is 1,755 lines of tree-sitter extraction across 6 languages:
- Python, C#, Java, C++, TypeScript, JavaScript
- Language-specific AST visitors for classes, methods, properties, docstrings
- Format detection from code patterns
- Limitation extraction from exception handling

Tree-sitter grammars update independently. Each grammar update may require parser adjustments. New language support requires new visitors. Bug fixes in one language extractor may not apply to others.

**Impact**: This single script accounts for ~33% of all Python code in the repo and requires language-specific expertise to maintain.

**Recommendation**: Phase 5 — consume from launcher, which already maintains this. Keep local as fallback only.

---

## Shipping Blockers Summary

| Blocker | Phase to Fix | Severity |
|---------|-------------|----------|
| 15 scout test failures / tree-sitter dependency | Phase 0 + 5 | High |
| No package boundary | Phase 1 | Medium |
| Runtime/source mixed | Phase 3 | Medium |
| Hardcoded paths bypass config | Phase 2 | Medium |
| No launcher version contract | Phase 5 | Medium |

All blockers are addressed in the migration plan. Phase 0 is the minimum to unblock development. Phases 0–3 are the minimum to ship.
