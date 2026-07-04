# Deletion Governance — DGR Protocol

> Last updated: 2026-07-04
> Plan: `humming-wondering-storm`
> Authority: Human maintainer only (this file is in `docs/` — writable by agents but not under `docs/governance/`)

---

## Overview

No tracked file in this repository may be deleted without a **Deletion Governance Record (DGR)**.
This covers: `git rm`, `os.remove`, `Path.unlink`, `shutil.rmtree`, and renames of tracked source paths.

Content retirement (marking a page obsolete) MUST use `draft: true` via skill S-83.
**Never use `git rm` for content retirement.**

---

## Tier Classification

| Tier | Applies to | DGR path | Gate |
|------|-----------|----------|------|
| **T-00** | FORBIDDEN_EXACT paths (AGENTS.md, CLAUDE.md, path_guard.py, hook scripts) and FORBIDDEN_PREFIXES (`themes/`, `layouts/`, `configs/`, `.claude/`, `skills/`, `docs/governance/`, etc.) | **No DGR path exists** | Always blocked |
| **T-01** | ALLOWED_PREFIXES content/knowledge/tests/scripts/pipeline/data, plus any tracked file not in T-00 or T-02 | DGR required | Blocked without valid DGR |
| **T-02** | `docs/` (non-FORBIDDEN), `scripts/maintenance/`, `scripts/generator/`, `scripts/seo/`, `scripts/gap-eval/` | Advisory | Warn; allow |
| **T-03** | Gitignored/unprotected, generated artifacts | None | Silent pass |

---

## DGR File Format

DGRs are stored as YAML files in `deletion-approvals/` (tracked, CI-visible).

```yaml
dgr_id: DGR-{yyyymmdd}-{slug}
dgr_version: "1.0"
approver: human-maintainer
approved_at: "2026-07-04T12:00:00Z"    # ISO8601 UTC
expires_at: "2026-07-11T12:00:00Z"     # approved_at + 7 days
plan_ref: "humming-wondering-storm"
reason: "Retiring obsolete locale page replaced by regeneration"
files:
  - path: content/products.aspose.org/ar/old-page/_index.md
    deletion_class: T-01
    operation: hard_delete    # hard_delete | rename | retire
rename_destination: null
redirect_plan: ""
references_updated: true
commit_message_token: "Deletion-Approved: DGR-{dgr_id}"
```

**Rules:**
- `files[].deletion_class` must never be `T-00` — `create` rejects T-00.
- `expires_at` is `approved_at + 7 days`. Expired DGRs are rejected (fail-closed).
- Malformed YAML → `validate-for-path` exits 2 (fail-closed).
- `deletion-approvals/` must exist and be tracked (not in .gitignore).

---

## Manager CLI

```bash
# Create a new DGR
python scripts/pipeline/commands/governance/deletion_governance_manager.py create \
  --files content/products.aspose.org/ar/old-page/_index.md \
  --reason "Obsolete page — English source removed in commit abc123" \
  --plan "humming-wondering-storm" \
  --class T-01 \
  --operation hard_delete

# Validate that a DGR covers a path (exit 0 = valid, 2 = blocked)
python scripts/pipeline/commands/governance/deletion_governance_manager.py validate-for-path \
  content/products.aspose.org/ar/old-page/_index.md

# Consume (archive) after the deletion commit
python scripts/pipeline/commands/governance/deletion_governance_manager.py consume \
  --dgr-id DGR-20260704-content-products-asp \
  --commit-sha abc123def

# List pending (uncommitted) DGRs
python scripts/pipeline/commands/governance/deletion_governance_manager.py list-pending

# Audit archived DGRs
python scripts/pipeline/commands/governance/deletion_governance_manager.py audit
```

---

## Step-by-Step Procedure for T-01 Deletions

1. **Classify the path** — run `check_staged_deletions.py` in dry-run mode or manually inspect tiers.
2. **Create the DGR**:
   ```bash
   python scripts/pipeline/commands/governance/deletion_governance_manager.py create \
     --files <path> --reason "..." --plan "<plan-slug>" --class T-01
   ```
3. **Stage and commit the DGR YAML** in `deletion-approvals/` with a normal commit.
4. **Stage the deletion** (`git rm <path>`).
5. **Commit with token** — commit message must include:
   ```
   Deletion-Approved: DGR-<dgr_id>
   ```
   The pre-commit Step 0b and `.git/hooks/commit-msg` validate the token.
6. **Consume the DGR** after the deletion commit:
   ```bash
   python scripts/pipeline/commands/governance/deletion_governance_manager.py consume \
     --dgr-id <id> --commit-sha <sha>
   ```

---

## T-00 Paths — No Deletion Path

The following paths can **never** be deleted. No DGR exists for them:

- `AGENTS.md`, `CLAUDE.md`, `CODEX.md`
- `scripts/pipeline/commands/governance/path_guard.py`
- All files in `scripts/ci/hooks/`
- Anything under `FORBIDDEN_PREFIXES`: `themes/`, `layouts/`, `configs/`, `.claude/`, `skills/`, `docs/governance/`, `docs/workflows/`, `docs/registries/`

Attempting to delete these paths:
- Pre-commit Step 0b: prints "Tier 0 — no DGR authorizes this" and blocks (exit 2).
- CI GUARD-DEL-01: blocks the PR.
- `.git/hooks/commit-msg`: blocks the commit.

---

## Content Retirement (NOT deletion)

To retire content pages, use skill `S-83`:
```
/page-retire content/products.aspose.org/{locale}/{family}/{platform}/_index.md
```
This sets `draft: true` in frontmatter. Hugo excludes draft pages from builds.
The file remains in git — it is NOT deleted.

---

## Emergency Policy

If a T-01 deletion is needed urgently and the 7-day TTL is a blocker:
1. Human maintainer creates a DGR YAML manually in `deletion-approvals/`.
2. Human maintainer commits the DGR and the deletion in a single commit with the token.
3. No agent may override the TTL — only human maintainer action is authorized.

---

## Gates Summary

| Gate | File | When |
|------|------|------|
| Pre-commit Step 0b | `scripts/pre-commit-audit.sh` | Every `git commit` |
| commit-msg DGR token | `.git/hooks/commit-msg` | Every `git commit` with staged deletions |
| CI GUARD-DEL-01 | `.github/workflows/content-audit.yml` | Every PR |
| `clean_locales.py` guard | `scripts/website/clean_locales.py` | Script execution |

---

## Related Documents

- `docs/reference/governance-gates.md` — Path guard allowlist/denylist reference
- `AGENTS.md §11` — Prohibited actions (includes deletion rules D-1 through D-6)
- `scripts/pipeline/commands/governance/deletion_governance_manager.py` — DGR manager CLI
- `scripts/ci/checks/check_staged_deletions.py` — Pre-commit deletion scanner
- `scripts/ci/checks/check_pr_deletion_approvals.py` — CI PR deletion gate
