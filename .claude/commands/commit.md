# S-76: Commit Prep — Stage and Commit Working Tree Changes

**Arguments**: $ARGUMENTS
Expected format:
```
[--scope "{conventional-commits-scope}"] [--hint "{free-text guidance}"]
```

| Parameter | Required | Values |
|-----------|----------|--------|
| `--scope` | No | Conventional Commits scope prefix, e.g. `slides` or `pipeline`. Pre-populates commit type guesses. |
| `--hint`  | No | Free-text guidance to the agent about what changed and why, e.g. `"fixed stale claim IDs in email reference pages"` |

**Examples:**
```
# Basic: let the skill inspect and decide everything
/commit

# With scope hint
/commit --scope slides --hint "updated C++ reference page layout migration"

# Content-only session
/commit --hint "KB locale batch update for slides/python"
```

---

## Purpose

Applies a full commit-preparation workflow to the current working tree:

1. **Inspect** — enumerate all changed, staged, and untracked files
2. **Categorize** — group changes into: feature, fix, refactor, docs/content, test, config/CI, hygiene
3. **Plan** — propose 2–8 logical Conventional Commits (never "everything in one commit")
4. **Hygiene** — verify no secrets, junk files, or accidentally staged ignore paths
5. **Repo-specific gates** — handle override tokens for protected paths; add `Skills invoked:` to content commits
6. **Stage with precision** — explicit file-by-file staging, never `git add -A`
7. **Quality gates** — run tests before committing
8. **Commit** — create each commit with imperative title + structured body
9. **Post-commit cleanup** — stage archived override tokens; ensure working tree is clean
10. **Final summary** — print log, per-commit breakdown, remaining items, follow-ups

---

## Pre-conditions

1. Working tree has uncommitted changes (if tree is clean, skill exits immediately).
2. `.venv` is usable: `.venv/Scripts/python` (Windows) or `.venv/bin/python` (Unix).
3. No unresolved merge conflicts (`git status` must not show `UU` entries).

---

## Steps

### A — Inspect repo state

Run all four commands and collect their output:
```
git status -sb
git diff --stat
git diff --staged --stat
git ls-files -m -o --exclude-standard
```

Then read `.gitignore` to confirm what is intentionally excluded.

Produce a **categorized change list**:

| Category | Description |
|----------|-------------|
| `feature` | New behaviour, new files, new skills/scripts |
| `fix` | Bug corrections, stale claim repairs, broken-link fixes |
| `refactor` | Internal restructuring with no behaviour change |
| `docs/content` | `content/` page updates, locale translations, blog/KB/products/reference |
| `test` | New or updated test files |
| `config/CI` | `configs/`, `.github/`, `scripts/pipeline/` infrastructure changes |
| `hygiene` | `.gitignore`, formatting, token lifecycle, reports cleanup |

---

### B — Decide commit boundaries

Create a **commit plan** with 2–8 commits (max). For each commit specify:

- **Conventional Commits type + scope**: `feat|fix|refactor|docs|test|chore|build|ci|perf`
  Scope is optional but recommended: e.g. `feat(skills)`, `content(reference)`, `chore(reports)`
- **Title**: imperative mood, ≤ 72 characters
- **Body**: bullet list of what changed + why + verification command
- **Exact file list**: which files go into this commit (no wildcards)

**Split rules** (in priority order):
1. Separate behaviour changes from formatting/whitespace-only changes.
2. Separate refactors from feature/bugfix (unless the refactor is required for the fix).
3. Keep locale/translation batches together (they are one logical change).
4. Keep mechanical renames/moves in their own commit if they cause large diff noise.
5. Keep docs/content updates near the feature they document, unless it's a bulk content update.
6. Hygiene commits (reports, token cleanup) go last.

---

### C — Repo hygiene before staging

1. **Secrets scan**: scan `git diff` output for API keys, tokens, passwords, connection strings.
   - If found: remove from file, add to `.gitignore`, do NOT commit.
2. **Junk files**: look for `__pycache__/`, `*.pyc`, `.DS_Store`, `node_modules/`, build outputs.
   - Add to `.gitignore` if not already covered; unstage if accidentally staged.
3. **Untracked ignore paths**: verify these directories remain untracked (never accidentally stage):
   - `reports/` — **strict local-only boundary; nothing under reports/ may ever be committed**
   - `plans/`, `foss-launcher/`, `.venv/`

---

### D — Override tokens for protected paths

This repo enforces a path-guard pre-commit hook. Any file in a **protected path** requires
an override token created and staged alongside the edit.

**Protected paths** (partial list — see `scripts/pipeline/path_guard.py` for full list):
- `AGENTS.md`, `CLAUDE.md`, `CODEX.md`
- `skills/`
- `.agents/skills/`, `.kilocode/skills/`, `.claude/commands/`
- `scripts/` (all subdirectories)
- `configs/`, `layouts/`, `themes/`

**Workflow for each protected-path commit**:

```bash
# 1. Create one token per logical group of protected files
.venv/Scripts/python scripts/pipeline/override_manager.py create \
  --paths "path/to/file1" "path/to/file2" \
  --reason "brief reason for the edit" \
  --plan "feat(scope): commit title"
# Token is written to reports/overrides/pending/ (local only — do NOT stage it)

# 2. Stage the protected files normally
git add path/to/file1 path/to/file2

# 3. Commit — hook reads token from disk, validates it, then consumes + archives it
git commit -m "..."
```

**Batching**: Group related protected files into one token to minimise noise.
Maximum 20–25 paths per token call (CLI limit).

**After commit**: the post-commit hook moves the token from `pending/` → `archived/`
locally. Both directories live under `reports/` which is gitignored. No staging of
token files is ever needed.

---

### E — Content commit requirements

For any commit that touches `content/` paths:

1. **`Skills invoked:` line** is required in the commit body:
   ```
   Skills invoked: [S-xx, S-yy, ...]
   ```
   Use the actual skill IDs that produced or modified the content.
   If content was edited manually or via S-73, use `[S-73, S-23, S-24, S-01]`.

2. **Pre-commit content API audit** runs automatically:
   - `FAIL` → commit is blocked; fix the issue before retrying
   - `WARN` → non-blocking; note in commit body if relevant

3. **Common FAIL causes and fixes**:

   | Cause | Fix |
   |-------|-----|
   | `evidence.claims` references unknown `claim_id` | Replace stale `ERC-*` IDs with valid `CLM-*` IDs from `knowledge/{family}/{platform}/merged/claims.json` |
   | `evidence.apis` lists unknown member | Remove or correct the API name against `knowledge/{family}/{platform}/merged/api_surface.md` |
   | `plugin_platform` is non-canonical | Fix to canonical value per `knowledge/registry.yaml` |
   | Blog slug hygiene failure | Fix the slug per the `check-blog-slugs.py` output |

---

### F — Stage with precision

For each planned commit:

```bash
# Stage only the intended files by explicit path
git add content/path/to/file1.md content/path/to/file2.md

# Validate: inspect what's staged
git diff --staged --stat

# Cross-check: ensure no unrelated files slipped in
git diff --staged --name-only
```

**Never use** `git add -A`, `git add .`, or `git add *` — these risk staging secrets,
junk files, or files that belong to a different logical commit.

---

### G — Verify quality gates

Before creating any commit, run:

```bash
.venv/Scripts/python -m pytest scripts/pipeline/tests/ -q
```

**Interpret results**:
- All pass → proceed
- Failures from **uncommitted changes** (e.g. new skill not yet mirrored) → expected pre-commit
  state; document in commit body and proceed
- Failures from **existing code** (regression) → fix root cause before committing; never skip
  with `--no-verify`

Record the result in the commit body:
```
Verification: pytest scripts/pipeline/tests/ -q → 927 passed, 2 expected pre-commit failures
```

---

### H — Create commits

Use Conventional Commits format for every commit:

```
type(scope): imperative title ≤ 72 chars

- What changed (bullet list, 3–8 items)
- Why (1–3 bullets explaining motivation)
- Verification: <command> → <result>

[Skills invoked: [S-xx, ...]]        ← content commits only

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
```

Pass the message via a heredoc to preserve formatting:
```bash
git commit -m "$(cat <<'EOF'
feat(skills): add S-76 commit skill

- Create skills/commit.md canonical skill file
- Mirror to .agents/, .kilocode/, .claude/commands/
- Register S-76 in AGENTS.md §12 and skills/README.md
- Verification: sync_skills.py --check → 0 drift

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

---

### I — Post-commit hook cleanup

After **each** commit, run:
```bash
git status -sb
```

If the hook consumed override tokens you will see no reports/ entries — token files live
under `reports/` which is gitignored and never committed. The hook moves them from
`pending/` → `archived/` locally; no staging or cleanup commit is needed.

---

## Post-conditions

- `git status -sb` output: only `## main...origin/main [ahead N]`, no modified or untracked
  tracked files.
- All commits pass pre-commit hooks (no `--no-verify` used).
- `git log --oneline -N` shows N logical, independently reviewable commits.
- No secrets, junk files, or accidentally staged ignore paths in any commit.

---

## Error handling

| Error | Resolution |
|-------|-----------|
| `BLOCKED: no valid token covers path '...'` | Create override token with `override_manager.py create`, stage it, retry commit |
| `Content API audit FAIL` | Fix stale claim ID / broken evidence in the file, `git add` the fix, retry |
| `Forbidden path staged: ...` (token exists) | Token path list does not cover exact path string — recreate with correct paths |
| `git rm -f` fails on pending token | File is not tracked (was never committed); ignore, it will disappear on its own |
| Tests fail (regression) | Fix root cause; never use `--no-verify`; label as `[BLOCKED]` if investigation needed |
| Hook moves token but `git status` shows ` D` | File is tracked; use `git rm -f` to stage the deletion |

---

## Final deliverable

Print to the user after all commits are complete:

**1. Git log:**
```
git log --oneline -n <N>
```

**2. Commit Summary table:**

| Hash | Title | Files | What it contains |
|------|-------|-------|-----------------|
| `abc1234` | `feat(skills): ...` | 43 | AGENTS.md, skills/, 3 mirrors |
| `def5678` | `content(reference): ...` | 283 | 3D TypeScript regen, Slides C++ migration |

**3. Remaining uncommitted changes** (and why left out):
- List any files intentionally excluded (junk, in-progress, external caches)

**4. Follow-ups** (only if unavoidable):
- Broken internal links found by audit (WARN-level, not regressions)
- Skill run record mismatches (non-blocking warnings)
