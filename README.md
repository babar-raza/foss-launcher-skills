# foss-launcher-skills

Evidence-based content generation skills for FOSS product documentation. Works with Claude Code, Codex CLI, and Kilo Code.

## What This Is

A standalone library of 48 agent skills that power a knowledge-grounded content pipeline:

1. **Discover** FOSS repositories across GitHub organizations
2. **Extract** truth from FOSS repositories (tree-sitter analysis)
3. **Learn** from existing content pages (golden corpus profiling)
4. **Generate** documentation, blog posts, KB articles, and API reference pages
5. **Validate** every claim against verified knowledge before writing
6. **Maintain** content freshness as upstream repos change

Every factual claim in generated content is traceable to the knowledge model — no hallucination.

## Quick Start

### Prerequisites

- Python 3.10+
- One of: Claude Code, Codex CLI, or Kilo Code
- A Hugo content repository (defaults configured for aspose.org structure)

### Install into your content repo

**Unix/macOS:**
```bash
git clone https://github.com/babar-raza/foss-launcher-skills.git
cd foss-launcher-skills
./install.sh /path/to/your-content-repo
```

**Windows (PowerShell):**
```powershell
git clone https://github.com/babar-raza/foss-launcher-skills.git
cd foss-launcher-skills
.\install.ps1 -Target C:\path\to\your-content-repo
```

Or run **standalone** (skills stay here, operate on external repo):
```bash
./install.sh --standalone /path/to/your-content-repo
```

### Install Python dependencies

```bash
pip install -r scripts/requirements.txt
```

This installs tree-sitter and language grammars used by the knowledge extraction pipeline.

### First run

```bash
# 1. Discover FOSS repos from configured GitHub orgs
/discover-products

# 2. Extract knowledge from a FOSS repo
/repo-scout 3d python /path/to/Aspose.3D-for-Python

# 3. Merge knowledge (works with scout-only — no external source needed)
/truth-merge 3d python

# 4. Generate an index
/truth-index 3d python

# 5. Scan existing content for style patterns
/corpus-scan 3d python docs

# 6. Create a docs page
/new-docs-page 3d python getting-started installation
```

## Skill Catalog

### Knowledge Pipeline

| ID | Skill | Purpose |
|----|-------|---------|
| S-34 | repo-scout | Extract truth from FOSS repo via tree-sitter |
| S-35 | truth-merge | Consolidate knowledge with provenance tagging |
| S-31 | truth-index | Generate knowledge index per product |
| S-15 | embed-knowledge | Embed into vector stores (3-tier fallback) |
| S-30 | truth-sync | Import external knowledge artifacts (optional) |
| S-37 | corpus-scan | Build golden corpus profile from existing content |
| S-39 | discover-products | Scan GitHub orgs for FOSS repositories |

### Knowledge Maintenance

| ID | Skill | Purpose |
|----|-------|---------|
| S-12 | knowledge-diff | Detect upstream repo changes |
| S-13 | stale-detect | Map changes to affected content pages |
| S-14 | knowledge-update | Refresh entire knowledge pipeline |
| S-36 | cross-platform | Check consistency across platforms in a family |

### Content Generation

| ID | Skill | Purpose |
|----|-------|---------|
| S-10 | project-phase-store | Record page creation intent and context |
| S-18 | page-plan | Plan page structure (sections → claims → snippets) |
| S-19 | page-draft | Draft content using site-type template |
| S-22 | faq-generate | Generate FAQ from knowledge model |
| -- | new-docs-page | Shortcut: generate docs page |
| -- | new-blog-post | Shortcut: generate blog post |
| -- | new-kb-howto | Shortcut: generate KB how-to |
| -- | new-kb-faq | Shortcut: generate KB FAQ |
| -- | new-reference-page | Shortcut: generate API reference page |

### Content Validation

| ID | Skill | Purpose |
|----|-------|---------|
| S-01 | path-guard | Enforce allowed/forbidden write paths |
| S-23 | ground-check | Pre-write evidence verification (truth gate) |
| S-33 | change-guard | Pre-write knowledge gate (forbidden claims) |
| S-32 | content-audit | Semantic audit against knowledge |
| S-24 | evidence-cite | Attach `<!-- evidence: -->` citations |
| -- | content-check | Structural/formatting validation |

### Content Quality

| ID | Skill | Purpose |
|----|-------|---------|
| S-17 | rubric-align *(internal)* | Quality gap analysis per dimension |
| S-21 | page-enhance | Apply targeted quality improvements |
| S-25 | eval-page | Assign A–F quality grade |
| S-26 | heal-page | Fix low-quality pages (grade D/F) |
| S-20 | page-update | Update content after knowledge refresh |
| S-63 | code-smoke | Syntax/type-check Python code blocks without executing |
| S-72 | evidence-repair | Fix broken/malformed evidence frontmatter blocks |
| S-78 | evidence-enhance | Improve evidence coverage on passing pages |
| S-41 | batch-eval-fix | Eval + deterministic auto-fix (no LLM); safe for batch runs |

### Content Governance & Repair

| ID | Skill | Purpose |
|----|-------|---------|
| S-73 | manual-edit | Operator-directed targeted content edit under full governance |
| S-66 | register-human-content | Register human-authored pages in provenance tracking |
| S-83 | page-retire | Retire outdated pages (set draft:true, retired_at) |

### Validation & Audit

| ID | Skill | Purpose |
|----|-------|---------|
| S-65 | link-validate | Validate cross-site internal links; detect broken slugs |
| S-90 | truth-audit | Member-level API verification against api_surface.json |
| S-85 | truth-audit-content | Line-level content truth audit; stable finding IDs |
| S-80 | coverage-reconcile | Knowledge unit disposition report; detects orphaned claims |
| S-81 | knowledge-coverage-audit | Per-claim 9-state disposition table; "no silent knowledge loss" |

### Session & Operations

| ID | Skill | Purpose |
|----|-------|---------|
| S-77 | session-start | Session gate: read governance, init ledger, backlog briefing |
| S-76 | commit | Stage and commit session-touched files (Conventional Commits) |
| S-88 | backlog | Unified backlog management across sessions |
| S-67 | diagnose-skill-failure | 5-class failure diagnosis for broken skill invocations |

### Orchestration

| ID | Skill | Purpose |
|----|-------|---------|
| S-38 | launch-product | Full FOSS product launch (knowledge → pages → report) |

## Skill Chains

```
Discovery:    S-39 → discovered.json → S-38 (per product)
New page:     S-10 → S-18 → S-19 → S-22 → S-23 → S-24 → S-01 → write
Maintenance:  S-12 → S-13 → S-14 → S-20 → S-23 → S-24 → S-01 → write
Enhancement:  S-17 → S-21 → S-23 → S-01 → write
Healing:      S-25 → S-26 → S-23 → S-25 → S-01 → write (or escalate)
Launch:       S-38 orchestrates:
                Phase 1 (knowledge): S-34 → S-35 → S-31 → S-15 → S-37
                Phase 2 (pages):     [S-10 → S-18 → S-19 → S-23 → S-24 → S-01] × page types
                Phase 3 (consistency): S-36
                Phase 4 (report):    reports/launch/{family}-{platform}-{timestamp}.md
```

## Project Structure

```
foss-launcher-skills/
├── skills/                    # 48 canonical skill files (YAML frontmatter + markdown)
├── scripts/                   # Python tooling (11 modules)
│   ├── scout.py               # Tree-sitter knowledge extraction
│   ├── merge.py               # Knowledge consolidation engine
│   ├── index.py               # Knowledge index generation
│   ├── embed.py               # Vector embedding (3-tier)
│   ├── corpus_scan.py         # Golden corpus profiling
│   ├── discover.py            # GitHub org product discovery
│   ├── golden_index.py        # Golden corpus index builder
│   ├── golden_conformance.py  # Conformance checking vs golden
│   ├── refresh_golden.py      # Golden corpus refresh
│   ├── config_loader.py       # Shared config resolution
│   ├── readme_sync.py         # README staleness detection
│   └── requirements.txt
├── tools/
│   └── distribute.py          # Generate agent-specific skill dirs
├── configs/
│   ├── families.yaml          # 24 product families × 15 platforms
│   └── intake_config.yaml     # 23 GitHub orgs for discovery
├── golden/                    # Golden corpus exemplars (5 site types)
│   ├── docs.aspose.org/
│   ├── blog.aspose.org/
│   ├── kb.aspose.org/
│   ├── products.aspose.org/
│   ├── reference.aspose.org/
│   └── _index.json            # Structural contracts per page type
├── intake/
│   └── scan_state.json        # Discovery scan state
├── knowledge/                 # Knowledge artifacts (per family/platform)
├── repos/                     # Cloned FOSS repositories
├── tests/                     # Test suite (10 test files + fixtures)
├── output/                    # Generated content (install tests)
├── plans/                     # Page plans and healing workflows
├── reports/
│   ├── agents/                # Agent session audit logs
│   └── conformance/           # Golden conformance reports
├── config.yaml                # Site paths, governance, corpus settings
├── discovered.json            # Discovered FOSS repos manifest
├── AGENTS.md                  # Agent governance (generated from template)
├── AGENTS.template.md         # Governance template for target repos
├── install.sh / install.ps1   # Installers
├── LICENSE
└── README.md
```

## Configuration

Edit `config.yaml` to match your content repo:

```yaml
# Path to the external content repo
content_repo: "/path/to/your-content-repo"

# Intake configs for product discovery
intake_config: "configs/intake_config.yaml"
families_config: "configs/families.yaml"

# Golden corpus — curated exemplar files for structural/stylistic anchoring
golden_dir: "golden/"
golden_corpus:
  sample_count: 3
  min_words: 200
  profile_dir: "_corpus"

# Site path templates (defaults match aspose.org Hugo multisite)
sites:
  docs:
    content_path: "content/docs.aspose.org/en/{family}/{platform}/"
  blog:
    content_path: "content/blog.aspose.org/{family}/{platform}/"
  # ... etc.

# Agent governance
governance:
  default_role: writer
  roles:
    scout:
      skills: [S-34, S-35, S-31, S-15, S-30, S-37, S-39]
      write_paths: [knowledge/, reports/]
    writer:
      skills: [S-10, S-18, S-19, S-20, S-21, S-22, S-24, new-*]
      required_gates: [S-01, S-23]
      write_paths: [content/, plans/, output/, reports/]
    reviewer:
      skills: [S-25, S-26, S-17, S-32, S-33, S-23, S-01, content-check, S-36]
      write_paths: [reports/, content/]
    orchestrator:
      skills: [all]
      write_paths: [knowledge/, content/, plans/, output/, reports/]
  session_limits:
    max_pages_per_session: 20
    max_families_per_session: 3
    max_consecutive_fails: 3
```

You can also set `$CONTENT_REPO_PATH` environment variable to override `content_repo`.

## How It Works

### The installer (`install.sh` / `install.ps1`):
1. Copies `scripts/` to the target repo
2. Runs `tools/distribute.py` to generate agent-specific skill directories:
   - `.claude/commands/` — skills with YAML frontmatter stripped (Claude Code format)
   - `.agents/skills/` — full skill files in `{name}/SKILL.md` dirs (Codex format)
   - `.kilocode/skills/` — full skill files in `{name}/SKILL.md` dirs (Kilo Code format)
3. Optionally creates `AGENTS.md` from `AGENTS.template.md`

### The knowledge pipeline:
```
FOSS repo → scout.py → knowledge/{f}/{p}/scout/
                                                 \
                                                  merge.py → knowledge/{f}/{p}/merged/ → index.py → index.json
                                                 /
(optional) external source → truth-sync → knowledge/{f}/{p}/external/
```

When only `scout/` exists, `merge.py` runs a fast-path passthrough consolidation.

### The golden corpus pipeline:
```
golden/                → golden_index.py → golden/_index.json (structural contracts)
content repo           → corpus_scan.py  → knowledge/{f}/{p}/_corpus/{site-type}_profile.json
conformance reports    → golden_conformance.py → reports/conformance/{page}-conformance.json
```

Golden exemplars define the structural and stylistic targets. Corpus scanning profiles existing content. Conformance checking measures how well generated pages match the golden standard.

### The product discovery pipeline:
```
configs/intake_config.yaml → discover.py → discovered.json (repo manifest)
                                          → intake/scan_state.json (scan state)
discovered.json → launch-product (S-38) per product
```

Monitors 23 GitHub organizations for FOSS repositories, matches them to the product family taxonomy (24 families × 15 platforms), and feeds them into the launch pipeline.

### The content pipeline:
```
knowledge/merged/ → page-plan → page-draft → ground-check → evidence-cite → path-guard → write
```

## Agent Governance

Agents operate under a role-based governance model defined in `AGENTS.md` and `config.yaml`.

### Roles

| Role | Purpose | Write Paths |
|------|---------|-------------|
| **scout** | Extract and consolidate knowledge | `knowledge/`, `reports/` |
| **writer** | Generate and update content pages | `content/`, `plans/`, `output/`, `reports/` |
| **reviewer** | Evaluate, audit, and heal content | `reports/`, `content/` |
| **orchestrator** | Run full product launches | All allowed paths |

### Autonomy Tiers

| Tier | Behaviour |
|------|-----------|
| **AUTO** | Read, validate, extract, write reports — no approval needed |
| **WARN** | Write content pages, small knowledge updates — proceed, flag for review |
| **BLOCK** | Product launches, bulk updates — pause for human approval |
| **HUMAN-ONLY** | Modify governance, skills, or scripts — agents must not attempt |

Session limits enforce guardrails: 20 pages, 3 families, 3 consecutive failures → halt.

See `AGENTS.md` for the full governance specification including evidence requirements, hard stops, escalation conditions, and audit trail format.

## License

MIT
