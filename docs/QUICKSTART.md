# QUICKSTART — Aspose.org Content System (~30 minutes)

> **See also**: For in-depth skill and governance details, read [OPERATOR_GUIDE.md](../OPERATOR_GUIDE.md) and [AGENTS.md](../AGENTS.md) after completing this guide.

---

## Prerequisites

- **Windows**: Use Git Bash (MSYS2/MINGW64 from [Git for Windows](https://git-scm.com/downloads)). WSL, PowerShell, and cmd.exe are not supported.
- **Python**: Python 3.12 (pinned in `.python-version` at repo root, matching every CI workflow's `actions/setup-python@v5` pin) in the repo venv at `.venv/`
- **Git**: Clone the repo, then run `git log --oneline -3` to confirm you're at HEAD

---

## Step 1: Environment Setup (5 minutes)

```bash
# Activate venv
source .venv/Scripts/activate   # Windows Git Bash

# Install dependencies
pip install -r scripts/pipeline/requirements.txt

# Install governance hooks
bash scripts/install-hooks.sh

# Verify setup
.venv/Scripts/python --version
.venv/Scripts/python -m pytest scripts/pipeline/tests/ -q --co 2>&1 | tail -3
```

**Expected**: Python 3.x, tests collect without import errors.

---

## Step 2: Understand the System (5 minutes)

This repo is a Hugo multi-site monorepo for Aspose FOSS product documentation across 5 subdomains:

| Subdomain | Content path | Purpose |
|-----------|-------------|---------|
| `docs.aspose.org` | `content/docs.aspose.org/en/` | Conceptual/how-to docs |
| `blog.aspose.org` | `content/blog.aspose.org/` | Release announcements, tutorials |
| `kb.aspose.org` | `content/kb.aspose.org/en/` | Searchable how-to articles |
| `products.aspose.org` | `content/products.aspose.org/en/` | Product landing pages |
| `reference.aspose.org` | `content/reference.aspose.org/en/` | API reference index |

All content is **agent-generated** and grounded in **knowledge models** built from FOSS source repos. The knowledge pipeline: FOSS repo → scout → enrich → promote → `knowledge/{family}/{platform}/merged/`.

**Skills** are procedures in `.claude/commands/` that AI agents follow. You invoke them with `/skill-name {args}` inside a Claude session — they are not CLI commands.

**Agent commit rule**: Every agent commit must include exactly one `Co-authored-by`
trailer matching the agent's own identity.  The commit-msg hook enforces this —
missing or multiple trailers are blocked.  Each agent's S-76 skill mirror carries
the correct trailer for that agent:

| Agent | Co-authored-by trailer |
|---|---|
| Claude Code | `Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>` |
| Codex CLI | `Co-authored-by: Codex <codex@openai.com>` |
| Kilo Code | `Co-authored-by: Kilo Code <kilocode@kilocode.ai>` |

---

## Step 3: Verify a Product is Working (5 minutes)

```bash
# Check knowledge is fresh for a live product
.venv/Scripts/python -c "
import yaml
m = open('knowledge/pdf/net/merged/model.yaml').read()
data = yaml.safe_load(m)
print('stale_since:', data.get('stale_since'))
print('version:', data.get('version'))
"
# stale_since: null means knowledge is current

# Run audit on pdf/net (all Grade A — expect 0 FAILs)
PYTHONPATH=scripts/pipeline .venv/Scripts/python \
  scripts/pipeline/commands/content/audit.py pdf net
```

---

## Step 4: Five Common Operator Workflows (15 minutes — read, don't execute yet)

### Workflow 1: Launch a New Product

```
/launch-product {family} {platform}
```

Orchestrates: site plan → page generation → evidence → audit → grade. See [launch-product guide](guides/launch-product.md).

### Workflow 2: Refresh After Upstream Changes

```
/knowledge-diff {family} {platform}    # detect changes
/knowledge-update {family} {platform}  # re-scout + enrich + promote
```

See [refresh-product guide](guides/refresh-product.md).

### Workflow 3: Validate Content Quality

```bash
# Evaluate content grades
PYTHONPATH=scripts/pipeline .venv/Scripts/python -m content_eval evaluate {family} {platform}

# Run truth audit (claims vs FOSS source)
PYTHONPATH=scripts/pipeline .venv/Scripts/python \
  scripts/pipeline/commands/content/audit.py {family} {platform}
```

See [content audit guide](guides/content-audit-and-evaluation.md).

### Workflow 4: Translate to New Locales

`/translate` is permanently retired. Use `/ht-translate` (single page) or
`/ht-translate-batch` (multiple pages):

```
/ht-translate {src_path} {site} {locales}
```

**Note**: `/ht-translate` currently depends on a separate `hugo-translator` tool
cloned as a sibling repo, with a hardcoded local path in its skill definition
(`.claude/commands/ht-translate.md`) — it will not work out of the box on a
fresh clone or a different contributor's machine. See the Troubleshooting
table below.

### Workflow 5: Heal Quality Failures

```
/heal-page content/kb.aspose.org/en/{family}/{platform}/{slug}.md
```

See [heal content guide](guides/heal-content.md).

---

## After This Quickstart

1. Read [AGENTS.md](../AGENTS.md) in full — it contains all operating rules
2. Read [OPERATOR_GUIDE.md](../OPERATOR_GUIDE.md) — explains skills and invocation
3. Check [RUNBOOK.md](../RUNBOOK.md) — terminal command cheatsheet
4. Before your first content task, run the session-start checklist: `/session-start`

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| Hook blocks bare `python` | Use `.venv/Scripts/python` always |
| `skill_context.py not found` | Path is `scripts/pipeline/commands/governance/skill_context.py` |
| Clone cache empty | Run `/knowledge-update {family} {platform}` |
| Commit blocked by missing skill run record | Run `skill_run_manager.py create --skills S-73 --run-type targeted` |
| `stale_since` is set in model.yaml | Run `/knowledge-diff` then `/knowledge-update` before content tasks |
| `git rm` deletion commits without DGR check | Pre-commit hook is stale — re-run `bash scripts/install-hooks.sh` then verify with `diff .git/hooks/pre-commit scripts/pre-commit-audit.sh` |
| `/ht-translate` fails to find a site profile / venv | It depends on a separate `hugo-translator` repo cloned as a sibling directory with its own `.venv`, currently hardcoded to one contributor's machine path in `.claude/commands/ht-translate.md`. Clone `hugo-translator` yourself and update that path, or ask the maintainer for the current install location — this is a known portability gap, not a local misconfiguration. |
| Confused about which CI workflow actually gates a push | `content-audit.yml` is permanently retained but inert (PR-only trigger, this repo never uses PRs). `content-governance-checks.yml` is the live push-triggered gate — see [governance gates](reference/governance-gates.md). |
| `MISSION_AUTHORITY.yaml` looks stale or contradicts what you know is in flight | Its `governing_plan_path` is validated for presence only — nothing in this repo ever reads or resolves that path's contents, so it can silently point at a dead/local file. Treat it as informational only; check `plans/master-plan.md` and `reports/plan_state/{mission_id}/` locally (both gitignored, so only visible on a machine that ran that work) for real state. If neither exists locally, nothing from a prior session is in flight on this clone. |

For hook installation issues, see [hook-installation guide](operations/hook-installation.md).
For venv enforcement policy, see [docs/STATUS-venv-closure.md](STATUS-venv-closure.md).
