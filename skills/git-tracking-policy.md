<!-- CONTRACT: scripts/pipeline/commands/ops/git_tracking_policy_sync.py
     postcondition: --fix writes a deterministic "# BEGIN/END GIT-TRACKING-POLICY" block
       into .gitignore, derived from scripts/pipeline/config/git_tracking_policy.yaml
     postcondition: --check exits 0 iff .gitignore's marked block matches what the policy
       file currently resolves to (including live family-name resolution), else exits 1
       with a unified diff
     verified: 2026-09-06
-->
# S-125: Git Tracking Policy — Selectively Track a Subtree of an Ignored Directory

**Arguments**: $ARGUMENTS
Optional format: `[--check | --fix]` (default: `--check`)

## Purpose

Some directories in this repo are blanket-gitignored (e.g. `reports/` — see
`docs/content-system/generated-vs-maintained.md`), yet occasionally grow one curated
subtree that should be durable and reviewable in git history instead of local-only.
Hand-writing the `.gitignore` negation chain for that ("un-ignore every ancestor directory
level, then re-ignore its siblings, then re-include only the named children") is a
well-known git footgun that fails **silently** when a level is missed — the negation is
simply a no-op with no error. The "named children" set (Aspose family names, in the one
case this skill currently governs) also usually already has a canonical source elsewhere
in the repo; hand-copying it into `.gitignore` is the same drift risk `data/blog_family_routes.yaml`'s
own header comment already warns about ("pre-registered here to avoid the `/font/` class
of bug").

This skill is the reusable fix for **any future instance of the same class of problem**:
"track a curated subtree of an otherwise-ignored directory, keyed off a canonical name
list." To add a new case, add an entry to `scripts/pipeline/config/git_tracking_policy.yaml`
and run `--fix` — do not hand-edit `.gitignore`'s managed block, and do not invent a new
one-off negation chain for a new case; extend the policy file instead.

**Not the same problem as `knowledge_git_migration.py`** (`knowledge_tracking_policy.yaml`):
that module solves the mirror-image direction — default-**track** a root, selectively
**drop** named subpaths (`knowledge/`) — and deliberately keeps `.gitignore` hand-synced
for reviewability, because its patterns are flat single-line ignores with no ancestor-chain
gotcha. This skill's direction is default-**ignore**, selectively **track** — the chain
construction is the error-prone part, so it IS generated here.

---

## Modes

| Flag | Behaviour |
|------|-----------|
| `--check` (default) | Recompute the expected block from policy; diff against the current marked block in `.gitignore`. Exit 1 with a diff on drift, 0 if clean. Never writes. |
| `--fix` | Recompute and write the block into `.gitignore` in place. Also removes any now-redundant bare top-level ignore line for a policy root's first path segment (e.g. a standalone `reports/`) — that bare form is a directory match and blocks descent regardless of later negations, so it must be replaced with `{root}/*`, not merely supplemented. Idempotent. |

---

## Pre-conditions

1. `.venv` is activated (or invoke via `PYTHONPATH=scripts/pipeline .venv/Scripts/python`)
2. `scripts/pipeline/config/git_tracking_policy.yaml` exists and parses
3. Every policy entry's `keep[].source` file (e.g. `data/blog_family_routes.yaml`) exists
   and has a top-level `families:` mapping (for `type: family_glob` entries)

---

## Steps

> **Skill context gate** — run before step 1 (only needed when editing the policy file or
> a governed file this skill's own maintenance touches — not needed to simply run `--check`
> or `--fix`, since neither writes to a governed path other than `.gitignore` itself, which
> requires its own override token, see step 3):
> ```bash
> PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/commands/governance/skill_context.py begin --skill S-125 --scope "scripts/pipeline/config/git_tracking_policy.yaml"
> ```

1. **Add or edit a policy entry** in `scripts/pipeline/config/git_tracking_policy.yaml`:
   ```yaml
   - root: reports/some-new-tool
     keep:
       - type: family_glob          # resolve names from a families: mapping
         source: data/blog_family_routes.yaml
       # or: - type: literal
       #     names: [explicit, name, list]
   ```

2. **Preview**: `PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/commands/ops/git_tracking_policy_sync.py --check` — confirm the diff shown is the change you intend.

3. **Apply**: `.gitignore` is not in `path_guard.py`'s `ALLOWED_PREFIXES` (default-deny at
   repo root) — create an override token first:
   ```bash
   PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/commands/governance/override_manager.py create \
     --paths .gitignore --operation edit --reason "<why>" --plan "<plan file or task ref>"
   ```
   then:
   ```bash
   PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/commands/ops/git_tracking_policy_sync.py --fix
   ```

4. **Verify**: `git status --porcelain` on the newly-tracked subtree; spot-check both
   directions with `git check-ignore -v <path>` (a kept path must NOT be listed; a sibling
   path must be). Re-run `--check` — must exit 0.

5. **Commit** via the repo's standard git-plumbing procedure (CLAUDE.md § Git Push), citing
   `--skills S-125`. The override token is auto-consumed by `git_plumb_commit.py` for any
   `--files` entry that is a `path_guard` DENY covered by a pending token.

> **Skill context close** — run after the last step, if step 1's gate was used:
> ```bash
> PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/commands/governance/skill_context.py end --skill S-125 --status completed
> ```

---

## Post-conditions

- `.gitignore` contains exactly one `# BEGIN/END GIT-TRACKING-POLICY` block, matching what
  `git_tracking_policy_sync.py --check` computes from the current policy file
- No bare top-level ignore line remains for any policy root's first path segment
- Every `keep` name resolves against real git semantics (`git check-ignore`), not just
  string content — verified by `scripts/pipeline/tests/test_git_tracking_policy_sync.py`'s
  `TestRealGitCheckIgnore` suite
- `scripts/pre-commit-audit.sh` Step 41 blocks any future commit that reintroduces drift
  between `.gitignore`, the policy file, or the family registry it resolves against

---

## Error handling

- **Unknown `keep[].type`**: `resolve_keep_names()` raises `ValueError` — fix the policy
  entry; there is no silent fallback.
- **`keep[].source` file missing or has no `families:` key**: fails loudly (file-not-found
  or empty-mapping resolves to zero names, which still renders a valid — fully-ignored —
  block; it does not error, but also tracks nothing, so check the diff before `--fix`).
- **`--check` drift**: print the diff, run `--fix`, re-verify with `--check` before
  committing. Never hand-edit inside the marked block — the next `--fix` or CI gate run
  will silently overwrite (`--fix`) or block (`Step 41`) a hand-edit.
- **`.gitignore` write denied (path_guard)**: create an override token per Step 3 above —
  this is expected, not a bug; `.gitignore` is intentionally not in the write allowlist.

---

## Next steps after a policy change

- If the newly-tracked subtree is large or contains anything unexpected, review
  `git status --porcelain` before committing — this skill only decides *what's eligible* to
  be tracked, not what to stage.
- If `docs/content-system/generated-vs-maintained.md` documents the parent directory as
  "never committed," update that doctrine to note the new exception (see the
  `reports/repo-presenter-regen-full/{family}/**` precedent already documented there).
