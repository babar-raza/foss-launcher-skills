# Git Integration Protocol for Agent Sprints

> Added: 2026-05-17 — woolly-brewing-lamport-remaining-followups-closure sprint
> Authority: process hygiene record; updates require operator approval

## No-Stash Rule

**Agents MUST NOT use `git stash` during integration sprints.**

### Background

The woolly-brewing-lamport-post-execution-fix-integration sprint (2026-05-17) used
`git stash` to temporarily remove `.claude/settings.json` before rebasing. This bypassed
the classification-first requirement and set a risky precedent.

### Required Behavior

When local files are dirty before a rebase or push:

1. **Classify each dirty file first:**
   - Is it tracked? (appears in `git status --short` with M/A/D)
   - Is it untracked? (appears with ??)
   - Is it an IDE/user artifact? (e.g. `.claude/settings.json`, `.venv/`, `.kilo/`)
   - Is it session-owned content? (appears in session ledger candidates)

2. **IDE/user artifacts (.claude/settings.json, .venv/, etc.):**
   - These are gitignored or untracked local-only files.
   - They should NEVER be stashed, committed, or touched.
   - Do NOT use `git stash` to move them aside.
   - Proceed with the integration (fetch/rebase/push) — git will naturally ignore
     untracked files that are gitignored.
   - If git refuses to rebase due to unstaged tracked changes:
     STOP. Classify the tracked change. If it is IDE/user-only, confirm it is
     NOT in scope and report to operator before any destructive action.

3. **If a tracked file is dirty and not session-owned:**
   - Do NOT stash.
   - Do NOT reset.
   - Stop and produce a conflict-safe integration plan.
   - Report to operator with exact file list and classification.

4. **Narrow stash exception (requires explicit operator authorization):**
   - A stash may be used ONLY when the operator's prompt explicitly names:
     - The exact file(s) to stash
     - The reason (e.g. "stash only .claude/settings.json to allow rebase")
   - Without explicit authorization, stash is forbidden.

### Why This Rule Exists

`git stash` silently moves files out of the working tree without audit trail.
If an agent stashes the wrong file or fails to pop correctly, in-progress work
can be lost. For IDE/user artifacts like `.claude/settings.json`, no stash is
needed — git rebase operates on tracked, staged changes only.

### Enforcement

This rule is a process/governance note. It is not currently enforced by a hook.
Operators should verify compliance in sprint evidence reviews.

---

## Classification Table for Common Local Files

| File | Classification | Action during rebase |
|------|---------------|---------------------|
| `.claude/settings.json` | IDE/user artifact; gitignored | Leave untouched; rebase proceeds |
| `.venv/` | Local dependency cache; gitignored | Leave untouched |
| `.kilo/`, `.kilo-backlog/` | IDE artifact; gitignored | Leave untouched |
| `reports/` | Local evidence; gitignored | Leave untouched |
| `content/**/*.md` | Session-owned if in ledger | Commit before rebasing |
| `data/products.json` | Session-owned if in ledger | Commit before rebasing |
| `scripts/pipeline/**` | Session-owned if in ledger | Commit before rebasing |

---

## Integration Flow (Standard)

```
1. git fetch origin main
2. git log --oneline origin/main..HEAD  (classify local commits)
3. git log --oneline HEAD..origin/main  (classify remote commits)
4. git status --short                    (classify local dirty files)
5. For each dirty file: classify (session-owned / IDE / unknown)
6. If dirty files are only IDE artifacts: proceed to rebase
7. git rebase origin/main               (no stash needed)
8. Verify rebase result: git log --oneline origin/main..HEAD
9. Run validation gates
10. git push origin main
11. Verify: git rev-parse HEAD == git rev-parse origin/main
```

---

## Related: .claude/settings.json specifically

This file is modified by the Claude Code IDE extension when Bash tool allowances are
added (e.g. new `allowedTools` entries). It is gitignored and should never be committed.
During rebase, git does not touch untracked/gitignored files, so no special handling is
needed. If git refuses to rebase because of this file, check that it is gitignored:

```bash
git check-ignore -v .claude/settings.json
```

If it is NOT gitignored, do not stash — instead, commit or discard the change with
operator approval.

---

## Background Sync Prevention

> Added: 2026-05-17 — code-snippet-spacing-remote-ci-closure sprint (PN-01)

### What happened

During the code-snippet-spacing sprint (2026-05-17), five sprint commits were pushed to
`origin/main` without any explicit `git push` from the agent. `git reflog` showed:

```
16:05:19  rebase (start): checkout origin/main
16:05:26  rebase (finish): returning to refs/heads/main
```

The push was performed by **GitHub Desktop's automatic background sync** (pull-with-rebase
+ push). GitHub Desktop detected that `origin/main` had 7 new commits from
`actions@github.com` and that the local branch had 5 sprint commits, and automatically
performed the rebase + push.

### Rule

Before starting any sprint that will produce commits intended for controlled push:

1. **Close or pause GitHub Desktop** (or any other GUI git client with auto-sync enabled).
   Auto-sync tools cannot distinguish "ready to push" from "still in progress".

2. **Record the `origin/main` SHA** at sprint start (see Sprint Git Preflight Checklist).
   This creates a baseline to detect unexpected remote changes during the sprint.

3. **After sprint commits are made but before push:** verify that `origin/main` has not
   moved since the sprint start baseline (see Sprint Closeout: Remote Origin Check).

4. **Push explicitly** when push authorization is confirmed. Do not rely on auto-sync.

### Scope

Applies to sprints that create commits intended for production (`main`) and require an
explicit push authorization step. Low-risk local-only sprints (evidence-only, no commits)
are exempt.

### Enforcement

Process/governance note. Not enforced by a hook. Operators should verify compliance by
checking sprint evidence for a recorded baseline SHA and closeout result.

---

## Sprint Git Preflight Checklist

For any sprint that will produce commits or require push authorization, record these five
items before doing any work. Write output to the sprint evidence directory.

```bash
# 1. Current branch
git branch --show-current

# 2. Ahead/behind origin/main
git rev-list --left-right --count origin/main...HEAD

# 3. origin/main SHA (baseline — record this; compare at closeout)
git rev-parse origin/main

# 4. GUI git client check (Windows)
tasklist 2>/dev/null | grep -i "GitHubDesktop\|gitkraken\|sourcetree\|fork.exe" \
  || echo "No known GUI git clients detected"

# 5. Push authorization status (fill in explicitly)
# Record one of:
#   "Push NOT authorized for this sprint"
#   "Push authorized by operator on YYYY-MM-DD for scope: ..."
```

**Record all output to:** `reports/{sprint-dir}/sprint-git-preflight.md`

If a GUI git client is detected in step 4: pause or close it before continuing.

If ahead/behind shows unexpected state (already ahead without sprint commits): stop and
investigate before continuing.

---

## Sprint Closeout: Remote Origin Check

After sprint commits are created but **before any push**, verify that `origin/main` has
not moved since sprint start:

```bash
# Fetch to update remote-tracking ref (no merge)
git fetch origin main

# Compare to baseline recorded at sprint start
BASELINE="<SHA from sprint-git-preflight.md>"
CURRENT=$(git rev-parse origin/main)

if [ "$BASELINE" = "$CURRENT" ]; then
  echo "REMOTE_STABLE: origin/main unchanged since sprint start"
else
  echo "REMOTE_SHIFTED: origin/main moved from $BASELINE to $CURRENT"
  git log --oneline "$BASELINE".."$CURRENT"
fi
```

**REMOTE_STABLE:** proceed with push (if authorized).

**REMOTE_SHIFTED:** classify the new commits before pushing.
- All new commits are `actions@github.com` automation → rebase is safe; confirm no
  conflicts, then rebase and push.
- Any new commits are from another developer or agent sprint → stop; coordinate before
  pushing; do not rebase without reviewing for conflicts.

**Record output to:** `reports/{sprint-dir}/sprint-git-closeout.md`
