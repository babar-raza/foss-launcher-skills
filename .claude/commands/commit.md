# S-81: Commit — Stage and Commit Working Tree Changes

**Arguments**: $ARGUMENTS
Expected format:
```
[--scope "{conventional-commits-scope}"] [--hint "{free-text guidance}"]
```

| Parameter | Required | Values |
|-----------|----------|--------|
| `--scope` | No | Conventional Commits scope prefix, e.g. `slides` or `pipeline`. Pre-populates commit type guesses. |
| `--hint`  | No | Free-text guidance about what changed and why. |

**Examples:**
```
# Basic: let the skill inspect and decide everything
/commit

# With scope hint
/commit --scope slides --hint "updated C++ reference page layout"

# Content-only session
/commit --hint "KB locale batch update for slides/python"
```

---

## Purpose

Applies a full commit-preparation workflow to working tree changes.

1. **Inspect** — enumerate all changed, staged, and untracked files
2. **Categorize** — group changes deterministically by path-prefix commit groups
3. **Preview** — present commit plan with file lists; get confirmation
4. **Hygiene** — verify no secrets, junk files, or accidentally staged ignore paths
5. **Stage with precision** — explicit file-by-file staging, never `git add -A`
6. **Quality gates** — run tests before committing
7. **Commit** — create each commit with imperative title + structured body
8. **Final summary** — print log, per-commit breakdown, remaining items

---

## Pre-conditions

1. Working tree has uncommitted changes (if tree is clean, skill exits immediately).
2. No unresolved merge conflicts (`git status` must not show `UU` entries).

---

## Steps

### A — Inspect repo state

Run all commands and collect their output:
```bash
git status -sb
git diff --stat
git diff --staged --stat
git ls-files -m -o --exclude-standard
```

Then read `.gitignore` to confirm what is intentionally excluded.

---

### B — Decide commit boundaries

Group changes deterministically by path prefix. Each group becomes one commit.

**Group names** follow Conventional Commits type+scope derived from path prefixes:
- `content(docs)`, `content(kb)`, `content(reference)`, `content(products)`, `content(blog)` — content by site
- `content(locale)` — non-English locale translations
- `knowledge` — knowledge model artifacts
- `fix(pipeline)` — pipeline scripts
- `chore(ci)`, `chore(skills)`, `chore(scripts)` — subsystem changes
- `test` — test files
- `chore(misc)` — anything not matching a known prefix

Agent may further sub-scope a group by `{family}/{platform}` when spanning multiple products.

**Split rules** (in priority order):
1. Separate behavior changes from formatting/whitespace-only changes.
2. Separate refactors from feature/bugfix.
3. Keep locale/translation batches together.
4. Keep mechanical renames/moves in their own commit if they cause large diff noise.
5. Hygiene commits (reports, cleanup) go last.

---

### B.5 — Commit plan preview

**Before any staging or committing**, present the commit plan to the user:

```
=== COMMIT PLAN ===

Commit 1/N: {type(scope)}: {title}
  Files ({count}):
    {file1}
    {file2}
    ...
  Skills invoked: [{S-xx, ...}]   ← content commits only
```

**Wait for user confirmation** before proceeding to Step C.
If the user requests changes to the plan, adjust and re-present.

---

### C — Repo hygiene before staging

1. **Secrets scan**: scan `git diff` output for API keys, tokens, passwords, connection strings.
   - If found: remove from file, add to `.gitignore`, do NOT commit.
2. **Junk files**: look for `__pycache__/`, `*.pyc`, `.DS_Store`, build outputs.
   - Add to `.gitignore` if not already covered.
3. **Untracked ignore paths**: verify these remain untracked (never accidentally stage):
   - `reports/` — strict local-only boundary; nothing under reports/ may ever be committed
   - `.venv/`, `runs/`

---

### D — Content commit requirements

For any commit that touches `content/` paths:

1. **`Skills invoked:` line** is required in the commit body:
   ```
   Skills invoked: S-xx, S-yy, ...
   ```
   Use the actual skill IDs that produced or modified the content.
   If content was edited manually, use: `Skills invoked: manual`

2. **Pre-commit content audit** runs automatically via the commit-msg hook:
   - `FAIL` → commit is blocked; fix the issue before retrying
   - `WARN` → non-blocking; note in commit body if relevant

---

### E — Stage with precision

For each planned commit:

```bash
# Stage only the intended files by explicit path
git add content/path/to/file1.md content/path/to/file2.md

# Validate: inspect what's staged
git diff --staged --stat

# Cross-check: ensure no unrelated files slipped in
git diff --staged --name-only
```

**Never use** `git add -A`, `git add .`, or `git add *`.

---

### F — Verify quality gates

Before creating any commit, run:

```bash
python -m pytest tests/ -q
```

**Interpret results**:
- All pass → proceed
- Failures from uncommitted changes (e.g. new skill not yet mirrored) → expected pre-commit
  state; document in commit body and proceed
- Failures from existing code (regression) → fix root cause before committing

Record the result in the commit body:
```
Verification: pytest tests/ -q → N passed
```

---

### G — Create commits

Use Conventional Commits format for every commit:

```
type(scope): imperative title ≤ 72 chars

- What changed (bullet list)
- Why (motivation)
- Verification: <command> → <result>

[Skills invoked: S-xx, ...]        ← content commits only

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
```

Pass the message via a heredoc to preserve formatting:
```bash
git commit -m "$(cat <<'EOF'
feat(skills): add S-81 commit skill

- Create skills/commit.md canonical skill file
- Register S-81 in registry.yaml
- Sync to all mirrors
- Verification: pytest tests/ -q → N passed

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Post-conditions

- `git status -sb` shows only intentionally excluded files as dirty.
- All commits pass pre-commit hooks (no `--no-verify` used).
- `git log --oneline -N` shows N logical, independently reviewable commits.
- No secrets, junk files, or accidentally staged ignore paths in any commit.

---

## Error handling

| Error | Resolution |
|-------|-----------|
| `Content API audit FAIL` | Fix the content file, `git add` the fix, retry |
| Tests fail (regression) | Fix root cause; never use `--no-verify` |
| Working tree clean | Nothing to commit; exit immediately |
| Merge conflicts present | Resolve conflicts first; then re-run this skill |

---

## Final deliverable

Print after all commits are complete:

**1. Git log:**
```
git log --oneline -n N
```

**2. Commit Summary table:**

| Hash | Title | Files | What it contains |
|------|-------|-------|-----------------|

**3. Remaining uncommitted changes** (and why left out).
