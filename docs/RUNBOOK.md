# foss-launcher Runbook

Operational reference for the foss-launcher skills system. Covers common workflows,
troubleshooting, and skill chain invocations for the standalone Aspose FOSS documentation
generation and maintenance pipeline.

---

## Prerequisites

Before running any content workflow:

1. Clone this repo
2. Install dependencies: `pip install -r requirements.txt`
3. Configure content repo: `export CONTENT_REPO_PATH=/path/to/content-repo`
4. Set credentials in `.env`: `GITHUB_TOKEN=...` (required for product discovery)
5. Install git hooks: `bash scripts/install-hooks.sh`

See `/getting-started` (S-69) for the full 7-step bootstrap sequence.

---

## Common Workflows

### 1. First-time product launch

```
/session-start
/getting-started {family} {platform}
/knowledge-diff {family} {platform}      # baseline SHA
/knowledge-update {family} {platform}    # extract knowledge
/knowledge-bootstrap {family} {platform} # confirm READY
/site-plan {family} {platform}           # generate site manifest
/launch-product {family} {platform}      # run full launch pipeline
/link-validate {family} {platform}       # check cross-site links
/commit --scope {family}/{platform}
```

### 2. Post-launch refresh (upstream changed)

```
/session-start
/refresh-product {family} {platform}    # full 14-step refresh chain
```

Refresh-product auto-invokes: knowledge-diff → knowledge-update → delta-site-plan →
page-update → new pages → page-retire → reference update → family-sync → verification → commit.

### 3. Content quality investigation

```
/eval-page {path}                        # grade a single page
/content-eval {family} {platform}        # grade all pages
/gap-eval {family} {platform}            # verify against clone cache
/truth-audit-content {family} {platform} # line-level truth audit
/publish-readiness-review {family} {platform}  # governed verdict
```

### 4. Fix low-quality content

```
# Single page:
/heal-page {path}

# Batch from eval report:
/heal-batch reports/gap-analysis/{family}-{platform}.json --mode all

# Operator-directed fix:
/manual-edit {path} --scope body-wording --intent "{description of change}"
```

### 5. Fix broken evidence (pre-commit blocked)

```
/evidence-repair {path}          # auto-attach then LLM reasoning
/evidence-enhance {path}         # improve coverage on passing pages
```

### 6. Translate content

```
# Single page:
/translate-page content/docs.aspose.org/en/{family}/{platform}/{page}.md fr,de,ar

# Full product batch:
/translate-batch {family} {platform} all all

# Fix a content bug in all locale copies:
/locale-patch {family} {platform} docs {page}.md \
  --patches '[{"old_text": "wrong text", "new_text": "correct text"}]'
```

### 7. Knowledge maintenance

```
/knowledge-diff {family} {platform}         # detect upstream changes
/knowledge-update {family} {platform}       # refresh knowledge model
/knowledge-coverage-audit {family} {platform}  # check coverage
/coverage-reconcile {family} {platform}     # disposition table
```

### 8. Gap-eval pipeline (parallel to evidence pipeline)

```
/gap-eval {family} {platform}       # verify against clone cache
/gap-plan {family} {platform}       # generate fix plan
/gap-apply {family} {platform}      # execute waves 1–3
/gap-report                         # cross-product synthesis
```

---

## Skill Chains

### New product launch (full)

```
S-69 → S-12 → S-14 → S-49 → S-57 → S-38
```
(getting-started → knowledge-diff → knowledge-update → knowledge-bootstrap → site-plan → launch-product)

### Post-launch refresh

```
S-84 = S-12 → S-14 → S-87 → S-20 → [S-51,52,53,54,55] → S-88 → S-67 → S-58 → verify → S-81
```

### Content quality → fix pipeline

```
S-25 → S-26 (grade C/D) | S-21 (grade B) | S-78 (operator)
```

### Evidence pipeline

```
S-43 → S-44 → S-45 → S-46
```
(evidence-decide → evidence-materialize → mental-model → evidence-verify)

### Gap-eval pipeline

```
S-62 → S-63 → S-65 → S-23 → S-56 → write
```
(gap-eval → gap-plan → gap-apply → ground-check → no-downgrade-guard)

---

## Troubleshooting

### Skill fails to run

```
/diagnose-skill-failure {skill-id} "{error-summary}"
```

Classifications: CONFIG / DATA / CODE / GOVERNANCE / REGRESSION

### Validation errors before commit

```
python scripts/validate_skills.py           # check registry
python scripts/sync_commands.py --check     # check .claude/commands/
python scripts/sync_agents.py --check       # check .agents/ and .kilocode/
```

### Knowledge model stale

```
/knowledge-diff {family} {platform}
/knowledge-update {family} {platform}
```
Check: `knowledge/{family}/{platform}/merged/model.yaml` → `stale_since` should be `null`.

### Pre-commit hook blocks commit

```
# Registry integrity failure:
python scripts/validate_skills.py

# Mirror sync failure:
python scripts/sync_commands.py --sync
python scripts/sync_agents.py --sync

# Forbidden path staged:
# Check AGENTS.md for allowed write paths; obtain human override
```

### Content page blocked by no-downgrade-guard

```
python -m scripts.pipeline.content_eval evaluate --files {path} --format json
```
Review the grade. If the existing page is genuinely higher quality, fix the new content
to match or exceed it before writing.

---

## Internal Skills (not user-callable)

These skills are auto-invoked sub-routines. Do not invoke directly:

| Skill | ID | Purpose |
|---|---|---|
| path-guard | S-01 | Enforce allowed write paths |
| project-phase-store | S-10 | Record page creation intent |
| rubric-align | S-17 | Align content to quality rubric |
| evidence-cite | S-24 | Attach evidence citations |
| change-guard | S-33 | Guard against harmful changes |
| knowledge-bootstrap | S-49 | Pre-condition gate for knowledge state |
| no-downgrade-guard | S-56 | Pre-write quality comparison guard |

---

## Registry and Sync Scripts

| Script | Purpose |
|---|---|
| `scripts/validate_skills.py` | Validate registry integrity and internal skill enforcement |
| `scripts/sync_commands.py --sync` | Sync skills/ → .claude/commands/ (strips frontmatter, skips internal) |
| `scripts/sync_agents.py --sync` | Sync skills/ → .agents/skills/ and .kilocode/skills/ |
| `scripts/install-hooks.sh` | Install pre-commit and commit-msg hooks |

---

## Content Paths (relative to `$CONTENT_REPO_PATH`)

| Site | Path |
|---|---|
| docs.aspose.org | `content/docs.aspose.org/en/{family}/{platform}/` |
| blog.aspose.org | `content/blog.aspose.org/{family}/{platform}/` |
| kb.aspose.org | `content/kb.aspose.org/en/{family}/{platform}/` |
| products.aspose.org | `content/products.aspose.org/en/{family}/` |
| reference.aspose.org | `content/reference.aspose.org/en/{family}/{platform}/` |

---

## References

- `AGENTS.md` — authoritative agent governance
- `CLAUDE.md` — agent ground rules and setup
- `skills/registry.yaml` — canonical skill registry
- `docs/parity/` — parity program artifacts
- `docs/id-mapping.md` — cross-reference of foss IDs to aspose.org IDs

## Git Hooks

The repository ships with optional git hooks for local development. Install them with:

```bash
bash scripts/install-hooks.sh
```

### Pre-commit hook (`scripts/pre-commit-audit.sh`)

Runs `audit.py --files` on staged `.md` files before committing. If any FAIL findings
are detected, the commit is blocked.

**Override** (emergency only):
```bash
OVERRIDE_AUDIT=1 git commit -m "..."
```

### Commit-msg hook (`scripts/commit-msg-skills.sh`)

Validates that the commit message includes a `Skills invoked:` line when content files
are staged. Format: `Skills invoked: [S-XX, S-YY]`.

### Uninstalling hooks

```bash
rm .git/hooks/pre-commit .git/hooks/commit-msg
```

## Override Tokens

When `path_guard.py` blocks a write path and you need a one-time override:

```bash
# Create override token
python scripts/pipeline/override_manager.py create --path content/foo/bar.md --reason "emergency fix"

# List active tokens
python scripts/pipeline/override_manager.py list

# Revoke token after use
python scripts/pipeline/override_manager.py revoke --token-id {id}
```

Override tokens expire after 1 hour by default. The post-commit hook auto-revokes
tokens used in the committed files.

## Session Tracking

The `session_ledger.py` tracks which files were modified in a session to scope commits:

```bash
# Start a new session
python scripts/pipeline/session_ledger.py start

# Record a file touch
python scripts/pipeline/session_ledger.py touch content/docs.aspose.org/en/slides/net/index.md

# Get files for commit scope
python scripts/pipeline/session_ledger.py list-touched

# Finalize session after commit
python scripts/pipeline/session_ledger.py finalize --commit-sha $(git rev-parse HEAD)
```

Sessions are stored in `reports/sessions/` (gitignored).

## Skill Run Records

Track skill invocations for audit trail and commit message validation:

```bash
# Create a pending run record
python scripts/pipeline/skill_run_manager.py create --skills S-48 S-23

# Record step completion
python scripts/pipeline/skill_run_manager.py record-step \
  --run-id {id} --skill S-48 --type full

# Get declared skills for commit message
python scripts/pipeline/skill_run_manager.py get-declared-skills --run-id {id}

# Finalize after commit
python scripts/pipeline/skill_run_manager.py finalize \
  --run-id {id} --outcome success --commit-sha {sha}
```

## Launch Gate

Before any product launch, run all automated gates:

```bash
python scripts/pipeline/launch_gate.py {family} {platform}
```

Gate IDs and what they check:

| Gate | ID | Check |
|------|----|-------|
| Knowledge freshness | L-01 | model.yaml stale_since is null |
| Evidence coverage | L-02 | All content files have evidence block |
| API accuracy | L-04 | audit.py exits 0 FAIL |
| Format truth | L-05 | format evaluator exits 0 FAIL |
| Pipeline tests | L-07 | pytest tests/ exits 0 |

## Stale Detection

Check which content pages have evidence pointing to an outdated knowledge SHA:

```bash
# Markdown report
python scripts/pipeline/stale_detect.py {family} {platform}

# JSON report
python scripts/pipeline/stale_detect.py {family} {platform} --json
```

Exit code 0 = no stale pages; exit code 1 = stale pages found.

## Post-Refresh Verification

After running `/refresh-product`, verify the refresh completed correctly:

```bash
# Check progress
python scripts/pipeline/post_refresh_verify.py {family} {platform} --status

# Run verification gate
python scripts/pipeline/post_refresh_verify.py {family} {platform} --verify
```
