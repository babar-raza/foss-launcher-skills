---
name: commit
id: S-76
description: >
  Stage and commit working tree changes with structured Conventional Commits format.
  Scoped to session-touched files; previews the commit plan before writing.
args: "[--scope {scope}] [--hint {guidance}] [--force-all]"
---

# S-76: Commit — Stage and Commit Working Tree Changes

**Arguments**: $ARGUMENTS

| Parameter | Required | Values |
|---|---|---|
| `--scope` | No | Conventional Commits scope prefix, e.g. `words` or `pipeline` |
| `--hint` | No | Free-text guidance about what changed and why |
| `--force-all` | No | Bypass session scoping and include all dirty files (emergency) |

## Purpose

Apply a full commit-preparation workflow scoped to session-touched files:
1. **Inspect** — enumerate all changed, staged, and untracked files
2. **Session scope** — filter candidates to session-touched files only
3. **Categorize** — group changes by path-prefix commit groups
4. **Preview** — present commit plan; get confirmation
5. **Hygiene** — scan for secrets, junk files, accidentally staged paths
6. **Stage with precision** — explicit file-by-file staging, never `git add -A`
7. **Quality gates** — run tests before committing
8. **Commit** — create each commit with imperative title + structured body
9. **Final summary** — print log, per-commit breakdown, remaining items

## Pre-conditions

1. Working tree has uncommitted changes
2. Python environment is active (`python --version` succeeds)
3. No unresolved merge conflicts (`git status` must not show `UU` entries)

> **Optional context gate** — if `scripts/skill_context.py` exists, run before step 1:
> ```bash
> python scripts/skill_context.py begin --skill S-76 --scope "*"
> ```

## Steps

### Step A: Inspect repo state

```bash
git status -sb
git diff --stat
git diff --staged --stat
git ls-files -m -o --exclude-standard
```

Read `.gitignore` to confirm what is intentionally excluded.

### Step A.5: Session-scope filtering

**If `scripts/session_ledger.py` exists** (session tracking configured):
```bash
python scripts/session_ledger.py current
python scripts/session_ledger.py candidates --format json
```

The `candidates` list is the only set of files eligible for commit.
Print both the included candidates and any excluded files (with reasons).

**If no session ledger exists**: warn the user that session tracking is not configured.
- If `--force-all` was passed: proceed with all dirty files
- If `--force-all` was NOT passed: refuse and print guidance to either initialize a
  session first or pass `--force-all`

### Step B: Decide commit boundaries

Group files into logical commit groups based on path prefixes:
- `content/docs/` files → `content(docs)` group
- `content/kb/` files → `content(kb)` group
- `content/blog/` files → `content(blog)` group
- `content/reference/` files → `content(reference)` group
- `knowledge/` files → `knowledge` group
- `scripts/` files → `fix(pipeline)` or `feat(pipeline)` group
- `tests/` files → `test` group
- `skills/` or provider directories → `feat(skills)` group

Each group becomes one commit. The agent may further sub-scope a content group by
`{family}/{platform}` when the group spans multiple products.

For each commit, specify:
- Conventional Commits type + scope
- Title: imperative mood, ≤ 72 characters
- Body: bullet list of what changed + why + verification command
- Exact file list (no wildcards)

### Step B.5: Commit plan preview

**Before any staging**, present the commit plan:

```
=== COMMIT PLAN ===

Commit 1/N: {type(scope)}: {title}
  Files ({count}):
    {file1}
    {file2}
  Skills invoked: [{S-xx, ...}]   ← content commits only

Commit 2/N: ...

EXCLUDED (reason):
  {file_a} — {reason}
```

Wait for user confirmation before proceeding.

### Step C: Repo hygiene

1. **Secrets scan**: check for API keys, tokens, passwords in `git diff` output
   - If found: remove from file; add to `.gitignore`; do NOT commit
2. **Junk files**: look for `__pycache__/`, `*.pyc`, `.DS_Store`, `node_modules/`
   - Add to `.gitignore` if not already covered
3. **Protected directories**: never stage `reports/`, `.venv/`, or build outputs

### Step D: Content commit requirements

For any commit that touches content pages:
1. Add `Skills invoked: [S-xx, ...]` to the commit body
2. If a ground-check pre-commit hook is configured, fix any FAIL before retrying

### Step E: Stage with precision

```bash
# Stage only the intended files by explicit path
git add path/to/file1 path/to/file2

# Validate what's staged
git diff --staged --stat
git diff --staged --name-only
```

**Never use** `git add -A`, `git add .`, or `git add *`.

### Step F: Verify quality gates

```bash
python -m pytest tests/ -q
```

- All pass → proceed
- Failures from uncommitted changes → expected pre-commit state; document in commit body
- Failures from existing code (regression) → fix root cause before committing

Record the result in the commit body:
```
Verification: pytest tests/ -q → N passed
```

### Step G: Create commits

Use Conventional Commits format:

```
type(scope): imperative title ≤ 72 chars

- What changed (3–8 bullets)
- Why (1–3 bullets explaining motivation)
- Verification: <command> → <result>

[Skills invoked: [S-xx, ...]]   ← content commits only

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
```

Pass message via heredoc:
```bash
git commit -m "$(cat <<'EOF'
feat(skills): add session-start skill S-77

- Create skills/session-start.md
- Distribute to .agents/, .kilocode/, .claude/commands/
- Verification: pytest tests/ -q → N passed

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

### Step H: Post-commit cleanup

```bash
git status -sb
```

Confirm working tree is in the expected state after each commit.

> **Optional context close** — if `scripts/skill_context.py` exists, run after the last step:
> ```bash
> python scripts/skill_context.py end --skill S-76 --status completed
> ```

## Final deliverable

After all commits:

**1.** `git log --oneline -n {N}`

**2.** Commit Summary table:

| Hash | Title | Files | What it contains |
|---|---|---|---|
| `abc1234` | `feat(skills): ...` | 5 | New skill files |

**3.** Remaining uncommitted changes (and why left out)

**4.** Follow-ups (broken links, missing tests, etc.)

## Error handling

| Error | Resolution |
|---|---|
| No session ledger | Run `/session-start` to initialize; or pass `--force-all` |
| No dirty files after filtering | Check `git log`; files may already be committed |
| Tests fail (regression) | Fix root cause; never use `--no-verify` |
| Merge conflict | Resolve conflicts before committing |
