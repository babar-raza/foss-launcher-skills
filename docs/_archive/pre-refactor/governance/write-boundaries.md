# Archived Document

Archived: 2026-05-30

Reason: Superseded by the docs architecture refactor. This file is retained for history only; do not use it as current operating guidance.

Successor: See docs/README.md for the current documentation map and canonical references.

Original path: docs/_archive/pre-refactor/governance/write-boundaries.md

---

---
# Governance child document — extracted from AGENTS.md
# Source: AGENTS.md §4 (including §4b, §4c)
# Plan: delightful-wondering-hartmanis (TC-03)
# Extracted: 2026-04-28
---

## 4. Allowed Write Paths (enforced by S-01 path-guard)

```
ALLOWED:
  content/docs.aspose.org/en/{family}/{platform}/
  content/blog.aspose.org/{family}/{platform}/
  content/kb.aspose.org/en/{family}/{platform}/
  content/products.aspose.org/en/{family}/            (family landing page — layout: family; managed by /family-sync)
  content/products.aspose.org/en/{family}/{platform}/ (platform product page — layout: plugin; managed by /new-products-page)
  content/reference.aspose.org/en/{family}/{platform}/
  knowledge/   (evidence artifacts and model only)
  reports/     (local-only audit artifacts — agents may write here; NEVER commit to git)
  keywords/    (SEO keyword data — written exclusively by seo-keyword-refresh CI; never hand-edited)
  data/        (Hugo registry data — written by update_product_registry.py)
  patches/     (SEO patch manifests — written by scripts/seo/pipeline/report.py)

FORBIDDEN (no agent may write here without explicit human override):
  themes/
  layouts/
  configs/
  CLAUDE.md
  CODEX.md
  AGENTS.md    (this file — only humans may update it)
  .claude/     (Claude Code config)
  .agents/     (Codex config)
  .kilocode/   (Kilo Code config)
  skills/      (canonical skill source — only humans may update)
  scripts/pipeline/commands/governance/path_guard.py  (self-protected enforcement oracle)
  docs/OPERATOR_BYPASSES.md      (operator-only bypass reference — agents must not read)
  .github/workflows/             (CI pipeline — not in content allowlist)

ALSO ALLOWED (pipeline and CI maintenance):
  scripts/pipeline/     (operational pipeline scripts — except path_guard.py above)
  scripts/ci/           (CI validators — standalone; no content writes)
  scripts/maintenance/  (operator-run one-off scripts — see §4b)
  scripts/translator/   (translation subsystem package)
  scripts/gap-eval/     (gap evaluation tool)
  scripts/seo/          (optional SEO analysis)
  scripts/generator/    (reference page generator)
  tests/                (test fixtures and integration tests)

FORBIDDEN Python file locations (no agent may create .py files here):
  <repo root>/*.py      — path_guard.py blocks staging; no exceptions
  scripts/*.py          — scripts/ root is not in allowlist; use a subdirectory
  scripts/one-shot/     — retired; no new files; existing files are legacy disorder
```

### Override token protocol (for forbidden-path edits)

Override tokens are **local-only artifacts** stored in `reports/overrides/pending/`. They are validated from disk by the pre-commit hook — do NOT stage or commit them. `reports/` is gitignored; the pre-commit hook enforces this boundary. If hooks are not installed (e.g., after a fresh clone), run `bash scripts/install-hooks.sh`.

> **Never use `--no-verify`** when committing files in or near protected paths.
> `--no-verify` bypasses the pre-commit hook entirely, including the `reports/` boundary
> guard and the forbidden-path token check. If the pre-commit hook fails, fix the root
> cause — do not bypass it.

When a forbidden-path edit is authorized by the human maintainer:

1. **Create an override token** BEFORE staging the forbidden-path file:
   ```bash
   python scripts/pipeline/commands/governance/override_manager.py create \
     --paths <path> --reason '...' --plan '<plan-name>'
   ```
   Token is written to `reports/overrides/pending/` (local only — do not stage it).
2. **Stage only the forbidden-path file**:
   ```bash
   git add <forbidden-path-file>
   ```
3. The pre-commit hook reads the token from disk, validates it, and allows the commit.
4. The post-commit hook automatically moves the token from `pending/` → `archived/`
   (local filesystem only — no staging required).

### path_guard batch mode (`--stdin`)

For large staged batches (> 100 files), use `--stdin` to avoid per-file Python startup overhead. The `--stdin` flag reads one path per line from stdin and prints only DENY paths to stdout.

```bash
# Pipe staged paths through path_guard in batch mode
git diff --cached --name-only --diff-filter=ACM | \
    python scripts/pipeline/commands/governance/path_guard.py --stdin
# Exit 0 → all paths ALLOW; exit 2 → one or more paths DENY (printed to stdout)

# With JSON output (for tooling)
git diff --cached --name-only --diff-filter=ACM | \
    python scripts/pipeline/commands/governance/path_guard.py --stdin --json
# Outputs JSON array of {"path": "...", "decision": "DENY", "reason": "..."} objects
```

**When to use `--stdin`:** Any automated pipeline staging thousands of files (e.g., provenance backfill commits, batch content generation). The pre-commit hook already uses `--stdin` internally (Step 1 pipes all staged paths through it in one Python invocation).

**Exit codes:** `0` = all paths allowed; `2` = at least one DENY (DENY paths printed to stdout, one per line). Exit `1` is reserved for internal errors. Scripts should check for exit `2`, not just non-zero.

**Windows/CRLF note:** On Windows, Python's `sys.stdout` in text mode emits `\r\n`. `path_guard.py` calls `sys.stdout.reconfigure(newline="\n")` in `--stdin` mode to force LF-only output. If consuming the output in a bash pipeline, add `| tr -d '\r'` as defence-in-depth.

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
- The PreToolUse Write hook (`scripts/ci/hooks/check_py_write_hook.sh`) blocks misplaced
  `.py` file creation before it reaches the commit stage.


## 4c. Content Filename Conventions (TC-NEW-01, enforced 2026-04-25)

All markdown files under `content/` must satisfy these filename rules before being committed.
The validator (`scripts/ci/checks/check_content_filenames.py`) is the authoritative enforcement oracle.

### Rules

**Structural rejections (apply to ALL content trees):**
- Leading hyphen: `-word.md` → REJECT (breaks Hugo URL slug)
- Trailing hyphen before extension: `word-.md` → REJECT
- Doubled hyphens: `word--word.md` → REJECT
- Uppercase or mixed-case extension: `.MD`, `.Md` → REJECT
- Space in filename: `word word.md` → REJECT
- Double dot: `word..md` → REJECT

**Prose trees** (`content/docs.aspose.org/`, `content/kb.aspose.org/`, `content/blog.aspose.org/`):
- Stem must match `[a-z0-9]+(-[a-z0-9]+)*` — all-lowercase with hyphens as separators only
- PascalCase stems (e.g., `Scene3D.md`) → REJECT in prose trees

**Reference tree** (`content/reference.aspose.org/`):
- PascalCase stems (e.g., `Scene3D.md`, `IFileFormat.md`) → ALLOWED (mirrors API member names)
- Structural rejections still apply

**Internal scaffolding** (excluded from validation):
- `content/templates/` directory is excluded — scaffold files follow their own conventions

### Validator CLI

```bash
# Check all content — exits 1 if any violations (default mode)
.venv/Scripts/python scripts/ci/checks/check_content_filenames.py --strict

# Print violations but exit 0 (advisory / pre-graduation mode)
.venv/Scripts/python scripts/ci/checks/check_content_filenames.py --report-only
```

### Enforcement

| Gate | Scope | Mode |
|------|-------|------|
| `scripts/pre-commit-audit.sh` Step 1b | Every staged commit | Blocking (exit 1) |
| `.github/workflows/content-audit.yml` "Check content filename conventions" | PRs touching `content/**/*.md` | Blocking |

### Root cause and resolution (2026-04-25)

Commit `05952a134c` (2026-03-27) introduced `content/docs.aspose.org/en/3d/net/developer-guide/-graph.md` — a leading-hyphen filename caused by a creation typo. The file was renamed to `scene-graph.md` (37 locale copies) in the recovery. Nginx redirects were added to `docs.aspose.org.redirects.txt` for all affected locales.

**Do NOT:**
- Use `segment.strip("-")` or any silent slug sanitization anywhere in the toolchain
- Pass only the filename stem (without the full path) to the validator

---

## Metrics Write Boundaries

The following metrics paths are **local-only** and must never be staged or committed:
- `reports/metrics/` — all metrics evidence (events, runs, dry-runs, tests, failed, bundles)
- `reports/overrides/` — governance override tokens
- `scripts/pipeline/.env` — credentials file

Metrics source files that ARE committed live under `scripts/pipeline/commands/ops/` and
`scripts/pipeline/config/`. New call sites must be registered in
`metrics_callsite_registry.yaml` before committing. Unregistered direct calls to
`llm.professionalize.com` will fail `check_professionalize_call_sites.py` in CI.
Token values (`AGENT_METRICS_TOKEN`, `GPT_OSS_API_KEY`, `LLM_API_KEY`) must never be
committed. See `AGENTS.md §15` for the full metrics obligation.

---

## Hugo Output Discipline (TC-HUGO-03, enforced 2026-05-23)

All agent-invoked `hugo` builds **must** write output to a system temp directory,
never to a relative path inside the repo root.

### Rule

| Context | Required destination |
|---------|---------------------|
| Validation build (L-09, L-13 gates) | `{tmpdir}` via `tempfile.mkdtemp()` in Python |
| Agent ad-hoc Bash build | `$(mktemp -d)` assigned to a variable first |
| `hugo server` (local dev preview) | No `-d` flag — Hugo uses `public/` by default |

### Prohibited patterns (blocked by PreToolUse hook)

```bash
# BLOCKED — destination is a relative path starting with "public"
hugo --config configs/products.aspose.org.toml -d public-test/ --quiet
hugo --config configs/blog.aspose.org.yml --destination public-iv-blog/
hugo --config configs/docs.aspose.org.toml -d public/
```

### Allowed patterns

```bash
# Correct — absolute temp dir, cleaned up by OS
tmpdir=$(mktemp -d)
hugo --config configs/products.aspose.org.toml -d "$tmpdir" --quiet
rm -rf "$tmpdir"

# Correct — local dev server (no -d flag)
hugo server --config configs/products.aspose.org.toml

# Correct — Python subprocess pattern (launch_gate.py, readiness_gate.py)
# import tempfile, subprocess
# tmpdir = tempfile.mkdtemp()
# subprocess.run(["hugo", "--config", str(config_path), "-d", tmpdir, "--quiet"])
```

### Reference implementation

`scripts/ci/hooks/check_hugo_build.sh` — canonical correct pattern using
`tmpdir=$(mktemp -d)` and `trap "rm -rf '$tmpdir'" EXIT`.

### Enforcement

| Gate | Scope | Mode |
|------|-------|------|
| `scripts/ci/hooks/check_destructive_bash_hook.sh` | Every Bash tool call | Blocking (exit 2); bypass via `SKIP_DESTRUCTIVE_BASH_CHECK=1` is **prohibited for agent sessions** — see `docs/BYPASS_REGISTRY.md` |
| `.gitignore` glob `/public-*/` | Every `git add` | Prevents accidental staging |

### Root cause (2026-05-22)

During the `enterprise-positioning-anchor-schema` backlink campaigns, agents ran
`hugo -d public-as-{site}/` and `hugo -d public-iv-{site}/` for rendered anchor
verification. The ad-hoc relative names were chosen to avoid collision across runs.
Ten full-site HTML directories accumulated in the repo root. They were gitignored
reactively (commit `777cadf711`). This section closes the proactive enforcement gap.
