---
# Governance child document — extracted from AGENTS.md
# Source: adapted from AGENTS.md §16
# Plan: delightful-wondering-hartmanis (TC-03)
# Ported: 2026-05-20 (parity migration sprint)
---

## 16. Testing Seam Contract — Tiered Monkeypatch Policy

Pipeline test code is governed by a four-tier model that classifies every mock/patch
usage by risk. Tiers 1–2 are **banned**; Tier 3 requires annotation; Tier 4 is permitted.

### 16.1 Tier Definitions

| Tier | Name | Examples | Required Alternative | Enforcement |
|------|------|---------|---------------------|-------------|
| **T1** | Path constant patching | `monkeypatch.setattr(mod, "REPO_ROOT", ...)`, `patch.object(mod, "_REPO_ROOT", ...)`, `@patch("mod.CONTENT_ROOT")` | `configure()` seam (legacy) or constructor/parameter DI (new code) | Block (CI + pre-commit) |
| **T2** | Internal function replacement | `monkeypatch.setattr(mod, "_private_func", ...)`, `patch.object(mod, "_run", ...)` | DI via constructor parameter, callback, protocol, or strategy | Block (CI ratchet + pre-commit) |
| **T3** | External I/O boundary mocking | `sys.argv`, `subprocess.run`, HTTP clients, `sys.stdout` | Prefer `main(argv=None)` for CLI; structured annotation required | Lint: require annotation |
| **T4** | Environment/dict patching | `patch.dict(os.environ, ...)`, `patch.dict(sys.modules, ...)` | None required | No enforcement |

### 16.2 Guarded Path Constants

The following module-level constants are T1-guarded. Any `monkeypatch.setattr`,
`patch.object`, `@patch`, or direct test-scope assignment targeting these names is a
T1 violation:

`REPO_ROOT`, `KNOWLEDGE_ROOT`, `CONTENT_ROOT`, `_SESSION_DIR`, `_DEFAULT_CACHE`,
`_DEFAULT_REPO_ROOT`, `_DEFAULT_KNOWLEDGE_ROOT`, `_DEFAULT_CONTENT_ROOT`,
`_REPO_ROOT`, `_DEFAULT_MANIFEST_PATH`, `REPORTS_ROOT`, `_ROOT`, `_PENDING_DIR`,
`_ARCHIVED_DIR`, `_RUNS_DIR`, `CANONICAL_DIR`, `_HERE`.

### 16.3 Seam Pattern — `configure()` for Legacy Modules

**For every pipeline script that defines a module-level path constant:**

1. **`configure()` function required** — Expose a module-level `configure()` function that
   accepts keyword arguments matching the path constants and overrides their values.
   Calling `configure()` with no arguments MUST reset all constants to their built-in defaults.

   ```python
   # Pattern: immutable default + mutable global + configure() + reset
   _DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[N]
   REPO_ROOT = _DEFAULT_REPO_ROOT

   def configure(repo_root: "Path | None" = None) -> None:
       global REPO_ROOT
       REPO_ROOT = repo_root if repo_root is not None else _DEFAULT_REPO_ROOT
   ```

2. **CLI arg required for tools with a `main()`** — Scripts with a CLI MUST also expose
   injectable paths as optional arguments (e.g. `--repo-root`) that call `configure()`
   before execution.

3. **Tests MUST use `configure()`, never `monkeypatch`** — Use `configure(path=tmp_path)`
   before the call and `configure()` in a `finally` block or `yield`-based fixture.

   ```python
   def test_run_in_isolation(tmp_path):
       import my_script
       my_script.configure(repo_root=tmp_path)
       try:
           result = my_script.run(...)
       finally:
           my_script.configure()  # reset to defaults
   ```

4. **New modules** SHOULD prefer constructor/parameter DI over `configure()`.
   `configure()` is acceptable for retrofitting existing modules only.

### 16.4 T3 Annotation Schema

Every T3 mock MUST have a conforming comment on the preceding line:

```python
# T3-MOCK: target=sys.argv reason="CLI main() does not accept argv param" removal=TC-MP-XX
monkeypatch.setattr("sys.argv", ["script", "--flag"])
```

Fields: `target` (what is mocked), `reason` (why DI is not feasible), `removal` (taskcard
ID or `PERMANENT` with human approval). Missing or malformed annotations are lint errors.

### 16.5 T2/T3 Boundary Rule

An internal function may be reclassified as T3-equivalent **only** if ALL conditions hold:
1. The function is a thin wrapper around a single external I/O call
2. The wrapper adds no business logic
3. The reclassification is entered in the exception register with `tier_override: "T2→T3"`
4. The exception is approved by the human maintainer
5. The exception has an expiry date (max 90 days) and a removal target taskcard

### 16.6 Agent Output Requirements

Agents MUST NOT recommend T1 or T2 monkeypatch patterns in plans, reports, or code
suggestions. When test isolation is needed:
- For path constants → recommend `configure()` seam or constructor DI
- For internal functions → recommend parameter injection, protocol, or callback DI
- For I/O boundaries → recommend T3 with annotation

Any plan or report file containing a T1/T2 recommendation outside a `<!-- HISTORICAL -->`
block is a lint failure.

### 16.7 Scope

This policy applies to all Python test files in:
- `scripts/pipeline/tests/`
- `scripts/ci/tests/`
- `scripts/translator/tests/`
- `tests/`

Plan-file scanning applies to:
- `.claude/plans/*.md`, `backlog/*.md` (except `CHANGELOG.md`), `reports/skill-gaps/*.md`,
  `reports/skill-breakage/*.md`, `docs/*.md`

### 16.8 Existing Violations and Sunset

Existing T1/T2 violations are tracked in the committed baseline at
a committed baseline file. The touched-file ratchet applies: if a PR
modifies a test file containing T1 violations, that file must reach T1=0 before merge.

T2 violations are governed by the exception register at
the exception register. Each exception has an owner, expiry (max 90
days), rationale, and removal target. Expired exceptions stop being exempt from lint.

### 16.9 Enforcement

| Mechanism | Location | Mode |
|-----------|----------|------|
| AST-first linter | `scripts/ci/checks/check_monkeypatch_lint.py` | `--tier 1,2 --strict` (blocking) |
| Pre-commit hook | Pre-commit audit script | Blocking for T1+T2 |
| CI workflow | CI content-audit workflow | Ratchet + baseline comparison |
| Plan-file scanner | Integrated in linter | Fail on T1/T2 recommendations |

**Invariant (INV-4):** Every policy statement in this section MUST have a corresponding
automated enforcement mechanism. Policy without enforcement is documentation, not governance.

### 16.10 Parallel-Test Safety

`configure()` seams use unsynchronized module globals. Tests MUST NOT run with
`pytest-xdist` or any parallel runner until seams are made thread-safe or replaced
with constructor DI.

---

## Metrics Testing Contract

Metrics tests must use fake HTTP clients and dry-run modes — no real network calls.

- `ProfessionalizeClient` accepts a `_http_transport` DI seam for testing
- `MetricsSubmitter` accepts a `_http_client` DI seam for testing
- Test rows use `job_type="test"` and `item_name` prefix `[TEST]`
- `MetricsEventLedger` accepts `ledger_root` for temp-dir isolation in tests
- Production submission (`MODE_PRODUCTION_SUBMIT`) must not be triggered in unit tests
- `check_metrics_no_secrets.py` scans metrics test files for leaked credentials

