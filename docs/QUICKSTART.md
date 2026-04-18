<!--
OWNERSHIP: docs/QUICKSTART.md
AUTHORITY: First-session operator path (30-minute onboarding)
MUST NOT RESTATE: Governance rules — AGENTS.md is the only authority for rules
REVIEW TRIGGERS:
  - skills/session-start.md step sequence changes → update §3 Session Flow
  - AGENTS.md §11 Prohibited Actions changes → update §6 Key Safety Rules (pointer only)
  - AGENTS.md §2 Read Order changes → update §3 Session Flow
  - skills/getting-started.md step changes → update §2 Environment Setup
MAINTAINED BY: Human maintainer · CI: scripts/ci/check_onboarding_integrity.py
-->
# Operator Quick-Start Guide

**Last updated**: 2026-04-11

This guide gets a new operator productive in under 30 minutes. For full governance
rules, read `AGENTS.md`. For command cheatsheets, see `RUNBOOK.md`.

---

## 1. What This System Does

A skill-driven content pipeline that generates and maintains Aspose FOSS product
documentation across five subdomains: `docs.aspose.org`, `blog.aspose.org`,
`kb.aspose.org`, `products.aspose.org`, and `reference.aspose.org`.

**Core principle:** All tasks go through **skills** — markdown procedures invoked
via slash commands in Claude agent sessions. You do not run ad-hoc scripts or
edit content directly.

| If you want to... | Run this |
|---|---|
| Set up a fresh clone | `/getting-started` |
| Launch a new product | `/launch-product {family} {platform}` |
| Update after repo changes | `/refresh-product {family} {platform}` |
| Fix content quality issues | `/batch-remediate {family} {platform}` |
| Verify content | `/content-check {family} {platform}` |
| Commit changes | `/commit` (never `git commit` directly) |

---

## 2. Environment Setup

### Prerequisites

- Python 3.8+
- Git with SSH or HTTPS access to GitHub

### Bootstrap (run once)

```bash
python -m venv .venv
source .venv/Scripts/activate         # Windows Git Bash
# or: source .venv/bin/activate       # Unix/macOS

pip install -r scripts/requirements.txt
bash scripts/install-hooks.sh
```

### Credentials

Create `.env` at repo root (git-ignored):

```
GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxx        # Required — repo read scope
PROFESSIONALIZE_API_KEY=sk_xxxxxxxxxxxx  # Optional — LLM enrichment; TF-IDF fallback if absent
```

### Verify

```bash
.venv/Scripts/python scripts/pipeline/audit.py all
```

Should report 0 FAILs. If not, run `/getting-started` in a Claude session for
guided setup.

---

## 3. Session Flow: Init → Work → Commit

### Start every session with:

```
/session-start
```

This reads governance rules, initializes the session ledger, and captures the
current dirty-file snapshot. Skills will refuse to run without it.

### Work: invoke skills

```
/knowledge-update 3d python
/eval-page content/docs.aspose.org/en/3d/python/getting-started.md
/heal-page content/docs.aspose.org/en/3d/python/getting-started.md
```

Prerequisites are handled by the agent reading dependency rules from `AGENTS.md §6a`
and running upstream skills first. Completed stages are tracked in
`reports/phase_state.json` (checkpoint store), so re-running a completed stage is a
no-op. However, there is no code gate that prevents invoking a downstream skill before
its upstream prerequisite — correct ordering relies on the agent following AGENTS.md §6a
in the active session.

### Commit when done:

```
/commit
```

This stages only session-touched files, runs audit/path-guard hooks, and creates
a commit with skill IDs and evidence proof. Never use `git commit` directly.

---

## 4. Five Common Workflows

### 4.1 Launch a New Product

```
/launch-product {family} {platform}
```

Orchestrates 8 stages: knowledge bootstrap → site plan → page generation →
audit → grade → translation → verify → commit. Checkpoint-based; resumable
if interrupted.

### 4.2 Refresh After Upstream Changes

```
/refresh-product {family} {platform}
```

14-step chain: detect change → update knowledge → plan delta → update pages →
generate new → retire obsolete → validate → translate → commit.

### 4.3 Fix Quality Issues

```
/batch-eval-fix {family} {platform}    # Quick: deterministic auto-fixes only
/batch-remediate {family} {platform}   # Full: includes LLM reasoning pass
/heal-page {path}                      # Single page
```

### 4.4 Validate Content

```
/gap-eval {family} {platform}          # Verify against source repo
/content-check {family} {platform}     # Audit API accuracy
/eval-page {path}                      # Grade a single page
```

### 4.5 Manual Edit

```
/manual-edit {path}
```

The only sanctioned path for operator-directed content edits. Attaches evidence
and runs audit after the edit.

### 4.6 Hand Off to Another Operator

```
# Current operator: close the session
/commit

# New operator: start a fresh session and inherit prior work
/session-start
python scripts/pipeline/session_ledger.py inherit
```

The `inherit` command finds the most recent closed session and adopts all its
tracked files. Use `adopt --glob "content/**"` to selectively adopt files.

---

## 5. Common Errors and Fixes

### Knowledge errors

| Error | Fix |
|-------|-----|
| `PRECONDITION FAILED: api_surface.json not found` | Run `/knowledge-bootstrap {family} {platform}` |
| `Knowledge unavailable for {family}/{platform}` | Same — knowledge artifacts are missing |
| `model.yaml stale_since: {date}` | Run `/refresh-product {family} {platform}` |

### Commit errors

| Error | Fix |
|-------|-----|
| `No active session` | Run `/session-start` first |
| `path-guard DENY: {path}` | File is in a protected path; needs human override token |
| Pre-commit audit FAIL | Fix the content issue shown, re-stage, retry |

### Skill errors

| Error | Fix |
|-------|-----|
| Skill returns `STOP` | Read the message — it names the upstream skill to run first |
| `BROKEN` skill status | Run `/diagnose-skill-failure {skill-id} "{error}"` |

---

## 6. Key Safety Rules

- **Always** use `/commit`, never `git commit`
- **Never** use `--no-verify` on commits
- **Never** edit `AGENTS.md`, `CLAUDE.md`, `themes/`, or `scripts/` without authorization
- **Never** commit files under `reports/` — they are local-only (git-ignored)
- If no skill covers your task, file a gap report at `reports/skill-gaps/` — do not invent workarounds

---

## 7. Directory Map

```
aspose.org/
├── AGENTS.md              # Governance (read first)
├── content/               # Generated content (5 subdomains)
├── knowledge/             # Evidence layer (per product/platform)
│   └── {family}/{platform}/merged/
│       ├── model.yaml     # Product metadata + staleness flag
│       ├── api_surface.json
│       ├── claims.json
│       └── index.json
├── scripts/pipeline/      # Core pipeline scripts
├── skills/                # Skill definitions (source of truth)
├── .claude/commands/      # Claude Code mirror of skills
├── reports/               # Local-only artifacts (git-ignored)
└── .venv/                 # Python virtual environment
```

---

## 8. Further Reading

| Document | What it covers |
|----------|---------------|
| [`AGENTS.md`](../AGENTS.md) | Full governance — skills, evidence, write paths, launch gates |
| [`OPERATOR_GUIDE.md`](../OPERATOR_GUIDE.md) | Skill invocation patterns, CONTRACT model |
| [`RUNBOOK.md`](../RUNBOOK.md) | Command cheatsheet |
| [`.claude/commands/README.md`](../.claude/commands/README.md) | All available slash commands with argument syntax |
| [`scripts/pipeline/PIPELINE.md`](../scripts/pipeline/PIPELINE.md) | Pipeline architecture, New File Protocol |
