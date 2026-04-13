<!-- CONTRACT: scripts/pipeline/session_ledger.py
     purpose: stage and commit session changes with structured conventional commits
     preconditions: active session ledger (or --force-all); uncommitted changes in working tree
     postcondition: git commit(s) created with skill IDs, evidence, and verification results
     idempotent: no — each invocation creates new commit(s)
     verified: 2026-04-11
-->
# S-76: Commit Prep — Stage and Commit Working Tree Changes

**Arguments**: $ARGUMENTS
Expected format:
```
[--scope "{conventional-commits-scope}"] [--hint "{free-text guidance}"] [--force-all]
```

| Parameter | Required | Values |
|-----------|----------|--------|
| `--scope` | No | Conventional Commits scope prefix, e.g. `slides` or `pipeline`. Pre-populates commit type guesses. |
| `--hint`  | No | Free-text guidance to the agent about what changed and why, e.g. `"fixed stale claim IDs in email reference pages"` |
| `--force-all` | No | Bypass session ledger scoping and include all dirty files (emergency escape hatch). |

**Examples:**
```
# Basic: let the skill inspect and decide everything
/commit

# With scope hint
/commit --scope slides --hint "updated C++ reference page layout migration"

# Content-only session
/commit --hint "KB locale batch update for slides/python"

# Emergency: commit all dirty files regardless of session ledger
/commit --force-all --hint "manual cleanup of orphaned changes"
```

---

## Purpose

Applies a full commit-preparation workflow **scoped to the current session's touched files**.

1. **Inspect** — enumerate all changed, staged, and untracked files
2. **Session scope** — filter candidates to session-touched files only (via session ledger)
3. **Categorize** — group changes deterministically by path-prefix commit groups
4. **Preview** — present commit plan with file lists and exclusion report; get confirmation
5. **Hygiene** — verify no secrets, junk files, or accidentally staged ignore paths
6. **Repo-specific gates** — handle override tokens for protected paths; add `Skills invoked:` to content commits
7. **Stage with precision** — explicit file-by-file staging, never `git add -A`
8. **Quality gates** — run tests before committing
9. **Commit** — create each commit with imperative title + structured body
10. **Post-commit cleanup** — stage archived override tokens; ensure working tree is clean
11. **Final summary** — print log, per-commit breakdown, remaining items, follow-ups

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

---

### A.5 — Session-scope filtering

**Check for session ledger:**
```bash
.venv/Scripts/python scripts/pipeline/session_ledger.py current
```

**If a session ledger exists** (exit 0):
1. Get commit candidates (session-touched ∩ git-dirty):
   ```bash
   .venv/Scripts/python scripts/pipeline/session_ledger.py candidates --format json
   ```
2. The `candidates` list is the **only** set of files eligible for commit.
3. `excluded_dirty_at_start` files were dirty before this session — do NOT commit them.
4. `excluded_not_in_ledger` files became dirty from an unknown source — do NOT commit them.
5. Print both exclusion lists so the user can see what is being left out and why.

**If no session ledger exists** (exit 2):
1. **Run diagnostics BEFORE giving up** — do not assume "no session" without evidence:
   ```bash
   .venv/Scripts/python scripts/pipeline/session_ledger.py diagnose
   ```
2. Report the diagnostic output to the user verbatim.
3. If diagnostics confirm no active session:
   - Warn the user: `"⚠ No session ledger active. Consider running /session-start first."`
   - If `--force-all` was passed: proceed with ALL dirty files (legacy behavior).
   - If `--force-all` was NOT passed: **refuse to proceed**. Print the warning and exit.
     The user must either:
     1. Run `/session-start` to initialize a ledger, then use `adopt` to claim files:
        ```bash
        .venv/Scripts/python scripts/pipeline/session_ledger.py init
        # Adopt all dirty files:
        .venv/Scripts/python scripts/pipeline/session_ledger.py adopt --all
        # Or adopt by commit group:
        .venv/Scripts/python scripts/pipeline/session_ledger.py adopt --group "content(locale)"
        # Or adopt by glob pattern:
        .venv/Scripts/python scripts/pipeline/session_ledger.py adopt --glob "content/kb.aspose.org/*"
        # Or inherit a prior session's work (when continuing interrupted work):
        .venv/Scripts/python scripts/pipeline/session_ledger.py inherit
        # Or inherit a specific prior session:
        .venv/Scripts/python scripts/pipeline/session_ledger.py inherit --session-id <prior-id>
        ```
     2. Or pass `--force-all` to bypass scoping entirely.

  Use `dirty` to see all dirty files with their commit group and adoption status:
  ```bash
  .venv/Scripts/python scripts/pipeline/session_ledger.py dirty
  ```

**Critical**: Always capture BOTH stdout and stderr from session_ledger.py commands.
Do not assume "no session" without actually running `current` and examining its output.

**Refusal conditions** (even with a ledger):
- If ledger is empty (session touched no files) → refuse: `"Session ledger is empty — nothing to commit."`
- If candidates list is empty after filtering → refuse: `"No session-touched files are currently dirty."`

---

### B — Decide commit boundaries

**Get deterministic commit groups** from the session ledger classifier:
```bash
.venv/Scripts/python scripts/pipeline/session_ledger.py groups --format json
```

This returns a JSON object mapping group names to file lists. Each group becomes one commit.

**Group names** are deterministic Conventional Commits type+scope derived from path prefixes:
- `content(docs)`, `content(kb)`, `content(reference)`, `content(products)`, `content(blog)` — English content by site
- `content(locale)` — non-English locale translations
- `knowledge` — knowledge model artifacts
- `fix(pipeline)` — pipeline scripts
- `chore(ci)`, `chore(maintenance)`, `chore(translator)`, `chore(generator)` — subsystem scripts
- `test` — test files
- `chore(data)` — Hugo data registry
- `chore(misc)` — anything not matching a known prefix

**Agent refinement** (optional, within group constraints):
- The agent may further sub-scope a content group by `{family}/{platform}` when the group
  spans multiple families. E.g., `content(docs)` with both words/python and cells/net files
  becomes two commits: `content(words/python)` and `content(cells/net)`.
- The agent may override the commit type (e.g., `feat` instead of `content`) when the `--hint`
  or `--scope` indicates a feature, fix, or other type.
- The agent may NOT add files to a commit that are not in the session ledger candidates list.

**For each commit, specify:**
- **Conventional Commits type + scope** (from group name, optionally refined)
- **Title**: imperative mood, ≤ 72 characters
- **Body**: bullet list of what changed + why + verification command
- **Exact file list**: from the group output (no wildcards, no additions outside ledger)

**Split rules** (in priority order):
1. Separate behaviour changes from formatting/whitespace-only changes.
2. Separate refactors from feature/bugfix (unless the refactor is required for the fix).
3. Keep locale/translation batches together (they are one logical change).
4. Keep mechanical renames/moves in their own commit if they cause large diff noise.
5. Keep docs/content updates near the feature they document, unless it's a bulk content update.
6. Hygiene commits (reports, token cleanup) go last.

---

### B.5 — Commit plan preview

**Before any staging or committing**, present the commit plan to the user:

```
=== COMMIT PLAN (session {session_id}) ===

Commit 1/N: {type(scope)}: {title}
  Files ({count}):
    {file1}
    {file2}
    ...
  Skills invoked: [{S-xx, ...}]   ← content commits only

Commit 2/N: ...
  ...

EXCLUDED (dirty before session start):
  {file_a}
  {file_b}
  ...

EXCLUDED (not in session ledger):
  {file_c}
  ...
```

**Wait for user confirmation** before proceeding to Step C.
If the user requests changes to the plan, adjust and re-present.

**Exception**: When invoked from an automated workflow (e.g., S-84 refresh-product) with
`--auto` flag, skip the confirmation prompt and proceed directly.

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
[Addresses: [item-IDs, ...]]         ← when session addresses backlog items

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

- Only session-touched files were committed (or all files if `--force-all` was used).
- `git status -sb` may still show dirty files that were excluded (pre-existing or non-session).
- All commits pass pre-commit hooks (no `--no-verify` used).
- `git log --oneline -N` shows N logical, independently reviewable commits.
- No secrets, junk files, or accidentally staged ignore paths in any commit.

---

## Error handling

| Error | Resolution |
|-------|-----------|
| `No active session` / `session ledger is empty` | Run `/session-start` to initialize a session; or pass `--force-all` for legacy behavior |
| `No session-touched files are currently dirty` | Files may have been committed already; check `git log`; or record files with `session_ledger.py record` |
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
