# Write Boundaries — foss-launcher Governance

**Source**: Adapted from aspose.org `docs/governance/write-boundaries.md`
**Adapted**: 2026-05-15 (PAR-013 GV-002)

---

## Allowed Write Paths (enforced by S-01 path-guard)

```
ALLOWED (content repository — set via $CONTENT_REPO_PATH or config.yaml:content_root):
  $CONTENT_REPO_PATH/content/docs.aspose.org/en/{family}/{platform}/
  $CONTENT_REPO_PATH/content/blog.aspose.org/{family}/{platform}/
  $CONTENT_REPO_PATH/content/kb.aspose.org/en/{family}/{platform}/
  $CONTENT_REPO_PATH/content/products.aspose.org/en/{family}/
  $CONTENT_REPO_PATH/content/products.aspose.org/en/{family}/{platform}/
  $CONTENT_REPO_PATH/content/reference.aspose.org/en/{family}/{platform}/

ALLOWED (this repo — foss-launcher-skills-gitlab):
  knowledge/        (evidence artifacts and model only)
  reports/          (local-only audit artifacts — never commit)
  data/             (pipeline registry data)
  scripts/pipeline/ (operational pipeline scripts — except path_guard.py)
  scripts/ci/       (CI validators — no content writes)
  tests/            (test fixtures and integration tests)

FORBIDDEN (no agent may write here without explicit human override):
  themes/
  layouts/
  configs/
  CLAUDE.md
  AGENTS.md         (only humans may update)
  .claude/          (Claude Code config)
  .agents/          (Codex config)
  .kilocode/        (Kilo Code config)
  skills/           (canonical skill source — only humans may update)
  scripts/path_guard.py  (self-protected enforcement oracle)
  .github/workflows/     (CI pipeline)
  docs/              (governance docs — only humans and authorized agents may update)

FORBIDDEN Python file locations:
  <repo root>/*.py   — use a subdirectory
  scripts/*.py       — scripts/ root is not in allowlist; use a subdirectory
```

## Python File Placement Rules

**Apply this decision tree before creating any `.py` file.**

1. **Does the capability already exist in `scripts/pipeline/` or `scripts/ci/`?**
   YES → extend the existing script. Never create a parallel helper.

2. **Will a skill or CI step invoke this script?**
   YES → `scripts/pipeline/commands/{category}/` — must have `main()` and `--help`.

3. **Is this a CI-only read-only validator (no content writes)?**
   YES → `scripts/ci/check_{what}.py` or `validate_{what}.py`

4. **Is this a standalone one-off mutation or repair run manually by the operator?**
   YES → `scripts/maintenance/{verb}_{what}_{scope}.py`

5. **None of the above** → do not create the file. File a gap escalation report at
   `reports/skill-gaps/` first; propose the correct directory and why.

### Naming conventions

| Directory | Convention | Example |
|-----------|-----------|---------|
| `scripts/pipeline/commands/{category}/` | `{noun}.py` or `{verb}_{noun}.py` | `audit.py`, `remediate.py` |
| `scripts/ci/` | `check_{what}.py` or `validate_{what}.py` | `check_pipeline_registration.py` |

## Content Filename Conventions

All markdown files under `$CONTENT_REPO_PATH/content/` must satisfy:

**Structural rejections (all content trees):**
- Leading hyphen: `-word.md` → REJECT
- Trailing hyphen: `word-.md` → REJECT
- Doubled hyphens: `word--word.md` → REJECT
- Space in filename: `word word.md` → REJECT
- Uppercase extension: `.MD` → REJECT

**Prose trees** (docs, kb, blog):
- Stem must match `[a-z0-9]+(-[a-z0-9]+)*`

**Reference tree**:
- PascalCase stems (e.g., `Scene3D.md`) allowed (mirrors API member names)

## Skill-System Self-Protection

`skills/` is a protected write path. Only human operators may update skill files directly.
Agents must use S-78 (manual-edit) with explicit human authorization for any skill content change.
