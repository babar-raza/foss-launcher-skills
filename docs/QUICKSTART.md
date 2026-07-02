# QUICKSTART — Aspose.org Content System (~30 minutes)

> **See also**: For in-depth skill and governance details, read [OPERATOR_GUIDE.md](../OPERATOR_GUIDE.md) and [AGENTS.md](../AGENTS.md) after completing this guide.

---

## Prerequisites

- **Windows**: Use Git Bash (MSYS2/MINGW64 from [Git for Windows](https://git-scm.com/downloads)). WSL, PowerShell, and cmd.exe are not supported.
- **Python**: Python 3.11+ in the repo venv at `.venv/`
- **Git**: Clone the repo, then run `git log --oneline -3` to confirm you're at HEAD

---

## Step 1: Environment Setup (5 minutes)

```bash
# Activate venv
source .venv/Scripts/activate   # Windows Git Bash

# Install dependencies
pip install -r scripts/pipeline/requirements.txt
pip install -r scripts/translator/requirements.txt

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

**Codex commit rule**: When Codex creates any commit in this repository, the
commit message must include `Co-authored-by: Codex <codex@openai.com>`.

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

```
/translate {family} {platform} --locales es,fr,de
```

See [translator CLI reference](reference/cli.md).

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

For hook installation issues, see [hook-installation guide](operations/hook-installation.md).
For venv enforcement policy, see [docs/STATUS-venv-closure.md](STATUS-venv-closure.md).
