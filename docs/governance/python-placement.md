---
# Governance child document — extracted from AGENTS.md
# Source: adapted from AGENTS.md §4b
# Plan: delightful-wondering-hartmanis (TC-03)
# Ported: 2026-05-20 (parity migration sprint)
---

## 4b. Python File Placement Rules

**Apply this decision tree before creating any `.py` file.**

### Decision tree

1. **Does the capability already exist in `scripts/pipeline/` or `scripts/ci/`?**
   YES → extend the existing script. Never create a parallel helper.

2. **Will a skill or CI step invoke this script?**
   YES → `scripts/pipeline/` — follow the 8-step New File Protocol in `scripts/pipeline/PIPELINE.md`.

3. **Is this a CI-only read-only validator (no content writes)?**
   YES → `scripts/ci/check_{what}.py` or `validate_{what}.py`

4. **Is this a standalone one-off mutation, repair, or migration run manually by the operator?**
   YES → `scripts/maintenance/{verb}_{what}_{scope}.py` + add entry to `scripts/maintenance/registry.yaml`

5. **Does this belong to the translator, gap-eval, seo, or generator subsystem?**
   YES → add to that subsystem's package directory.

6. **None of the above** → do not create the file. File a gap escalation report at
   `reports/skill-gaps/` first; propose the correct directory and why.

### Naming conventions

| Directory | Convention | Example |
|-----------|-----------|---------|
| `scripts/pipeline/` | `{noun}.py` or `{verb}_{noun}.py` | `audit.py`, `attach_evidence.py` |
| `scripts/ci/` | `check_{what}.py` or `validate_{what}.py` | `check_pipeline_registration.py` |
| `scripts/maintenance/` | `{verb}_{what}_{scope}.py` | `repair_stale_claims_cells.py` |

### Extend-before-create rule
Search `scripts/pipeline/core/` and `scripts/pipeline/lib/path_utils.py` before adding any
utility function. Never create a duplicate helper.

### Import boundary
- `scripts/pipeline/`: imports within `scripts/pipeline/` only (PYTHONPATH=scripts/pipeline).
- `scripts/ci/`: standalone — call pipeline scripts as subprocesses, never import them directly.
- `scripts/maintenance/`: may insert `scripts/pipeline/` into sys.path.

### Enforcement
- `path_guard.py` blocks staging any `.py` file outside the ALLOWED_PREFIXES list.
- `scripts/ci/checks/check_python_placement.py` runs in CI (`--check-baseline`) and in the
  pre-commit hook (`--check-staged`).
- The write hook blocks misplaced
  `.py` file creation before it reaches the commit stage.

---
