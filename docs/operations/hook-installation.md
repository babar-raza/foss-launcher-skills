# Hook Installation

Status: Current
Audience: Operator, Contributor
Canonical reference: `docs/reference/governance-gates.md`
Last code-backed audit: 2026-08-08

The hook installer is `scripts/install-hooks.sh`.

## Initial Installation

Run after cloning:

```bash
bash scripts/install-hooks.sh
```

**Design (2026-08-08):** hooks are no longer copied into the untracked `.git/hooks/`
directory. The installer instead points git at the tracked `scripts/githooks/`
directory via `git config core.hooksPath scripts/githooks`. Each file in that
directory is a thin wrapper that `exec`s the real, tracked script directly —
`reference-transaction` is tracked verbatim (no wrapper needed, it was already
self-contained). Editing a hook's source now takes effect on the very next commit;
there is no separate copy left to fall behind. This replaced a copy-based design
that had silently drifted in production — the installed copy was missing a bug fix
and an entire safety step (the media-asset-size guard) that had already landed in
`scripts/pre-commit-audit.sh`, and the only way the drift was intended to surface
was a near-miss in production. See `scripts/install-hooks.sh`'s own header comment
for the full incident.

| Hook | Wrapper (tracked) | Real source | Purpose |
|------|--------------------|--------------|---------|
| `pre-commit` | `scripts/githooks/pre-commit` | `scripts/pre-commit-audit.sh` | Path guard, deletion gate (Step 1), API audit, and the rest of the numbered steps (Tier 1) |
| `commit-msg` | `scripts/githooks/commit-msg` | `scripts/commit-msg-skills.sh` | Skills invoked field, DGR token validation |
| `post-commit` | `scripts/githooks/post-commit` | `scripts/post-commit-override.sh` | Override token consumption |
| `reference-transaction` | `scripts/githooks/reference-transaction` (tracked directly, no wrapper) | — | Auto-unshallow shallow clones |

**Tier 2 (pre-push) removed 2026-08-16.** `scripts/githooks/pre-push` and
`scripts/pre-push-audit.sh` (added 2026-08-14, TC-CIR-06) ran the full governance
test suite, a full-tree Python-placement baseline check, actionlint on changed
workflows, and a non-blocking dependency dry-run on every push. Removed because it
broke on GitHub Desktop (see below) and its runtime (~281s observed) badly exceeded
its own 90s budget. Its checks are not enforced anywhere else: the governance test
suite only reruns in `skill-governance.yml` CI when specific paths change, the
full-tree Python-placement baseline had no other caller, and actionlint on changed
workflows was otherwise only run manually via `/workflow-harden`. Accepted gap, not
solved — same posture as `git push --no-verify` always was: CI remains the backstop
for whatever a push-time gate doesn't catch. Gates today: pre-commit (Tier 1) + CI
(what was "Tier 3"; there is no Tier 2 anymore).

## Re-syncing After Governance Updates

Nothing to re-sync. Because `core.hooksPath` points at a tracked directory whose
`pre-commit`/`commit-msg`/`post-commit` wrappers `exec` the real script by path, an
edit to `scripts/pre-commit-audit.sh` (or the other two real scripts) is live on the
very next commit — there is no installed copy to fall behind. `install-hooks.sh`
only needs to be rerun after a **fresh clone** (to set `core.hooksPath` and restore
the executable bit — `core.fileMode=false` in this repo means git does not track or
restore it), not after routine hook-source edits.

## Verifying Current State

```bash
# Confirm the mechanism is wired correctly
git config --get core.hooksPath   # expect: scripts/githooks

# Confirm the wrapper resolves and executes (does not require a real commit)
git hook run pre-commit

# Confirm current line count of the real source (no frozen number to go stale)
wc -l scripts/pre-commit-audit.sh
```

If `core.hooksPath` is unset or points elsewhere, re-run `bash scripts/install-hooks.sh`.

## Manual Fallback

If the installer fails, wire the mechanism manually:

```bash
chmod +x scripts/githooks/pre-commit scripts/githooks/commit-msg \
         scripts/githooks/post-commit scripts/githooks/reference-transaction
git config core.hooksPath scripts/githooks
```

## Rollback

To restore the previous copy-based mechanism (e.g. while diagnosing an issue with
the new one): `git config core.hooksPath .git/hooks` — this does not touch
`scripts/pre-commit-audit.sh` or any other real hook source, only the pointer to
where git looks for hooks, so it is an immediate, zero-data-loss revert.

## Related

- [Governance gates reference](../reference/governance-gates.md) — what each hook enforces
- [Deletion governance](../DELETION_GOVERNANCE.md) — DGR protocol and deletion gate behavior
