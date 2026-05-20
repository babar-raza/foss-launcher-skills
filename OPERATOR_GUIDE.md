# Operator Guide — foss-launcher-skills Content Generation System

This guide explains how to operate the foss-launcher-skills content generation system
for new team members, maintainers, and anyone inheriting or debugging this system.

---

## Shell Requirement (Windows)

**All local operations on Windows MUST use Git Bash** (MSYS2/MINGW64, from
[Git for Windows](https://git-scm.com/downloads)). WSL, PowerShell, and cmd.exe
are not supported — governance scripts depend on bash semantics and Unix utilities.
WSL is permanently rejected due to environment-variable boundary failures.

For the full policy, see `AGENTS.md §2b`. CI runs on `ubuntu-latest` (no Windows
enforcement needed in CI).

## Python Virtual Environment — Platform Paths

Examples throughout this guide use the **Windows Git Bash** path for the virtual environment.
Adapt for your platform:

| Platform | Activate | Python binary |
|----------|----------|---------------|
| Windows (Git Bash) | `source .venv/Scripts/activate` | `.venv/Scripts/python` |
| Linux / macOS | `source .venv/bin/activate` | `.venv/bin/python` |

All `.venv/Scripts/python` references in this guide become `.venv/bin/python` on Linux/macOS.

---

## §1 — What Is This System?

The foss-launcher-skills system uses AI agents (Claude, Codex, Kilo Code) to generate,
validate, and repair Aspose FOSS product documentation across five subdomains:
`docs`, `blog`, `kb`, `products`, and `reference`.

Content is grounded in **knowledge models** (per product/platform) built from FOSS
source repositories. Every content page must cite evidence from the knowledge model.

**Standalone repo operation**: This repo owns the skills system. Content lives in an
external repository. Configure your content root before running any content-writing
skill:

```bash
# Option A: environment variable (recommended for shell sessions)
export CONTENT_REPO_PATH=/path/to/your/content-repo

# Option B: config.yaml in this repo root
# content_root: "/path/to/your/content-repo"
```

---

## §2 — What Is a "Skill"?

A **skill** is a markdown file in `skills/` (e.g. `skills/knowledge-update.md`). It
describes a procedure that an AI agent follows step by step.

**A skill is NOT a CLI command.** You cannot run a skill from a terminal directly.

| Concept | What it is |
|---------|-----------|
| `skills/knowledge-update.md` | Procedure document for the knowledge-update skill |
| `/knowledge-update 3d python` | How you invoke it — only inside an AI agent session |
| `scripts/pipeline/commands/knowledge/refresh_knowledge.py` | The backing script the agent calls automatically |

---

## §3 — How to Invoke a Skill

1. Configure your content root (see §1 above).
2. Open a Claude agent session in this repository:
   - Claude Code CLI: run `claude` in the repo root
   - IDE extension: open the repo folder, open the Claude sidebar
3. Type the slash command with arguments:
   ```
   /knowledge-update 3d python
   /launch-product slides java
   /content-check $CONTENT_REPO_PATH/content/docs.aspose.org/en/3d/python/getting-started/installation.md
   /batch-remediate 3d python
   ```
4. The agent reads the skill file and follows the steps. Script-backed steps run
   automatically. Agent-reasoned steps are performed by the agent.

---

## §4 — Skills vs Scripts (the CONTRACT model)

Every script-backed skill has a **CONTRACT comment** at the top of the skill file:

```markdown
<!-- CONTRACT: scripts/pipeline/commands/knowledge/refresh_knowledge.py (runs scout.py + enrich.py + promote.py + index.py)
     postcondition: refresh_knowledge.py executes all 4 pipeline steps
     postcondition: writes merged/pipeline_run.json confirming all 4 steps ran
     note: step 7 (stale flag clear) still requires explicit agent action
-->
```

The CONTRACT tells you:
- **Which script** is called automatically
- **What that script produces** (postconditions)
- **What the agent must do manually** (note: lines)

To find the backing script for any skill: look for the `<!-- CONTRACT: ... -->` block at
the top of the skill file. Skills without a CONTRACT block are fully agent-executed.

---

## §5 — Running Script Steps Manually (When No Agent Is Available)

If you need to run a skill's script portions without an active agent session:

> **Warning — hooks are inactive in terminal mode.**
> Claude Code's PreToolUse enforcement hooks only fire inside Claude Code. They do NOT
> run when you execute scripts from a terminal directly. To compensate, run these
> equivalents manually after any content changes:
> - API accuracy: `.venv/Scripts/python scripts/pipeline/commands/content/audit.py {family} {platform}`

### knowledge-update
Runs all 4 knowledge pipeline steps:
```bash
.venv/Scripts/python scripts/pipeline/commands/knowledge/refresh_knowledge.py {family} {platform} {clone_cache_path}
# Confirms completion: check knowledge/{family}/{platform}/merged/pipeline_run.json
```

### content-check
```bash
CONTENT_REPO_PATH=/path/to/content .venv/Scripts/python scripts/pipeline/commands/content/audit.py {family} {platform}
```

### batch-eval-fix
```bash
# Step 1: Evaluate
CONTENT_REPO_PATH=/path/to/content .venv/Scripts/python -m scripts.pipeline.content_eval evaluate {family} {platform} --format json --remediation
# Step 2: Auto-fix
.venv/Scripts/python scripts/pipeline/commands/content/remediate.py fix {eval-report-path}
# Step 3: Refresh evidence
CONTENT_REPO_PATH=/path/to/content .venv/Scripts/python scripts/pipeline/commands/content/attach_evidence.py --files {modified-files}
```

### translate
```bash
CONTENT_REPO_PATH=/path/to/content .venv/Scripts/python scripts/translator/cli.py batch {family} {platform} --locales all
```

---

## §6 — Quick System Health Commands

```bash
# Validate skill registry integrity
.venv/Scripts/python scripts/validate_skills.py

# Verify mirror sync (skills/ -> .claude/commands/ -> .agents/ -> .kilocode/)
.venv/Scripts/python scripts/sync_commands.py --check
.venv/Scripts/python scripts/sync_agents.py --check

# API accuracy audit (requires CONTENT_REPO_PATH set)
CONTENT_REPO_PATH=/path/to/content .venv/Scripts/python scripts/pipeline/commands/content/audit.py all

# Content quality evaluation for a product
CONTENT_REPO_PATH=/path/to/content .venv/Scripts/python -m scripts.pipeline.content_eval evaluate 3d python --format json

# Run all tests
.venv/Scripts/python -m pytest tests/ -q

# Check knowledge model freshness
cat knowledge/{family}/{platform}/merged/model.yaml | grep stale_since
```

---

## §7 — Initial Setup

```bash
# 1. Clone the repository
git clone <repo-url> foss-launcher-skills-gitlab
cd foss-launcher-skills-gitlab

# 2. Create and activate virtual environment
python -m venv .venv
source .venv/Scripts/activate      # Windows Git Bash
# source .venv/bin/activate        # Linux/macOS

# 3. Install dependencies
pip install -r scripts/requirements.txt

# 4. Set content root (required for content-writing skills)
export CONTENT_REPO_PATH=/path/to/your/content-repo

# 5. (Optional) Install git hooks
bash scripts/install-hooks.sh

# 6. Verify setup
.venv/Scripts/python scripts/check_setup.py
```

---

## §8 — Diagnosing Failures

### Audit reports unexpected FAILs
1. Run the audit: `CONTENT_REPO_PATH=/path/to/content .venv/Scripts/python scripts/pipeline/commands/content/audit.py {family} {platform}`
2. For stale claim IDs: re-run `attach_evidence.py` for the affected product
3. For missing API member: re-run `refresh_knowledge.py` (knowledge model may be stale)
4. In an agent session: `/diagnose-skill-failure` classifies failures into CONFIG / DATA /
   CODE / GOVERNANCE / REGRESSION with a resolution path for each.

### Detecting upstream repository changes
- **Single product**: Run `/knowledge-diff {family} {platform}` — fetches the clone cache
  and compares SHAs. If SHAs differ, `stale_since` is auto-set in `model.yaml`.
- **All products at once**: Run `/change-sweep` — batch SHA comparison across all active
  products with structured JSON output.

### Knowledge model is stale
1. Check `knowledge/{family}/{platform}/merged/model.yaml` → `stale_since` field
2. If not null: run `/knowledge-update {family} {platform}` in an agent session
3. After knowledge update: run `/delta-site-plan {family} {platform}` to compute
   page-level changes
4. Execute downstream updates per `docs/RUNBOOK.md` §3d

### Pre-commit hook is not running
Install hooks with the single-command installer:
```bash
bash scripts/install-hooks.sh
```

### Skill fails mid-execution
Use `/diagnose-skill-failure` in an agent session. It classifies failures and provides
a resolution path for each type.

### CONTENT_REPO_PATH not set
Most content-writing skills fail with a path error if `CONTENT_REPO_PATH` is not set.
Set it before starting any agent session:
```bash
export CONTENT_REPO_PATH=/path/to/your/content-repo
```

---

## §9 — DAR: Skill Dependency Rules

The DAR (Dependency Activation Rules) table in `AGENTS.md §6a` defines which skills must
run before others. For example, `/knowledge-bootstrap` must pass before any content
generation.

**Before invoking any content-generating skill:** verify required upstream checkpoints
are set. If missing, run the upstream skill first.

**There is no code-level gate** that prevents out-of-order skill invocation. Correct
ordering depends on the agent reading and following `AGENTS.md §6a` in the active session.

---

## §10 — Files and Directories at a Glance

| Path | Purpose |
|------|---------|
| `skills/` | Canonical skill files (source of truth) |
| `skills/registry.yaml` | Machine-readable skill registry with IDs, scripts, flags |
| `.claude/commands/` | Claude Code mirror of skills (auto-synced by sync_commands.py) |
| `.agents/skills/` | Codex CLI mirror of skills (auto-synced by sync_agents.py) |
| `.kilocode/skills/` | Kilo Code mirror of skills (auto-synced) |
| `knowledge/{family}/{platform}/` | Knowledge models per product (in this repo) |
| `knowledge/{family}/{platform}/merged/model.yaml` | Model metadata, stale_since |
| `knowledge/{family}/{platform}/merged/claims.json` | Factual claims |
| `knowledge/{family}/{platform}/merged/api_surface.json` | API surface |
| `knowledge/{family}/{platform}/merged/pipeline_run.json` | Confirms full 4-step pipeline ran |
| `reports/` | Local-only audit artifacts (gitignored) |
| `reports/skill-gaps/` | Gap escalation reports |
| `reports/skill-breakage/` | Skill breakage reports |
| `reports/discovery/` | Patrol and sweep discovery reports |
| `scripts/pipeline/` | Core pipeline scripts |
| `scripts/translator/` | Translation subsystem (9 sub-packages) |
| `scripts/ci/` | CI gate scripts |
| `scripts/validate_skills.py` | Skill registry validator |
| `scripts/sync_commands.py` | Sync skills/ to .claude/commands/ (excludes internal skills) |
| `scripts/sync_agents.py` | Sync skills/ to .agents/ and .kilocode/ |
| `AGENTS.md` | Canonical governance (read this first) |
| `docs/RUNBOOK.md` | Operations runbook for common tasks |

---

## §11 — Mirror Sync System

Three agent mirrors are maintained automatically:

| Mirror | Path | Internal skills |
|--------|------|----------------|
| Claude Code | `.claude/commands/{name}.md` | Excluded (7 internal skills hidden) |
| Codex CLI | `.agents/skills/{name}/SKILL.md` | Included |
| Kilo Code | `.kilocode/skills/{name}/SKILL.md` | Included |

After any skill file change in `skills/`:
```bash
.venv/Scripts/python scripts/sync_commands.py --sync
.venv/Scripts/python scripts/sync_agents.py --sync
```

> **Warning**: Do NOT use `tools/distribute.py` for syncing to `.claude/commands/` —
> it does not filter internal skills and will expose them to agents. Use
> `sync_commands.py` instead.

---

## §12 — Common Operator Workflows

### Launch a new product
```
/launch-product {family} {platform}
```
This orchestrates the full 8-phase pipeline: knowledge bootstrap → evidence →
site plan → page generation → validation → translation → commit.

### Refresh an existing product after upstream changes
```
/refresh-product {family} {platform}
```
Runs the complete refresh chain: knowledge diff → update → delta-site-plan → page-update
→ retire → family-sync → content-check → link-validate → translate → commit.

### Run quality evaluation on a product
```
/content-eval {family} {platform}
/publish-readiness-review {family} {platform}
```

### Scan for new FOSS products
```
/repo-patrol
/change-sweep
/discovery-triage
```

### Update skill registry after adding a skill
```
.venv/Scripts/python scripts/validate_skills.py
.venv/Scripts/python scripts/sync_commands.py --sync
.venv/Scripts/python scripts/sync_agents.py --sync
```
