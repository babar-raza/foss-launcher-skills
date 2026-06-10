# foss-launcher-skills

Evidence-based content generation skills for FOSS product documentation. Works with Claude Code, Codex CLI, and Kilo Code.

## What This Is

A standalone library of 93 agent skills (7 internal sub-routines + 86 user-callable) that power a knowledge-grounded content pipeline:

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

### Validate your environment

```bash
python scripts/check_setup.py
# Check knowledge readiness for a specific product
python scripts/check_setup.py --family words --platform python
```

See `QUICKSTART.md` for a full step-by-step walkthrough.

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
| S-61 | knowledge-enrich | LLM semantic enrichment from scout artifacts |

### Knowledge Maintenance

| ID | Skill | Purpose |
|----|-------|---------|
| S-12 | knowledge-diff | Detect upstream repo changes |
| S-13 | stale-detect | Map changes to affected content pages |
| S-14 | knowledge-update | Refresh entire knowledge pipeline |
| S-36 | cross-platform | Check consistency across platforms in a family |
| S-85 | coverage-reconcile | Knowledge unit disposition table (used/orphaned/excluded) |
| S-86 | knowledge-coverage-audit | Per-claim disposition; no silent knowledge loss |

### Content Generation

| ID | Skill | Purpose |
|----|-------|---------|
| S-18 | page-plan | Plan page structure (sections → claims → snippets) |
| S-19 | page-draft | Draft content using site-type template |
| S-22 | faq-generate | Generate FAQ from knowledge model |
| S-51 | new-docs-page | Generate docs page |
| S-52 | new-blog-post | Generate blog post |
| S-53 | new-kb-howto | Generate KB how-to |
| S-54 | new-kb-faq | Generate KB FAQ |
| S-55 | new-reference-page | Generate API reference page |
| S-66 | new-products-page | Generate products.aspose.org landing page |
| S-67 | batch-reference | Generate reference pages in bulk for all classes/enums |
| S-74 | new-kb-index | Scaffold KB platform section landing page |
| S-75 | new-docs-index | Scaffold docs platform section landing page |
| S-76 | new-reference-index | Scaffold reference platform section landing page |
| S-108 | content-enrich | Post-launch enrichment audit and handoff-manifest workflow |

### Content Validation

| ID | Skill | Purpose |
|----|-------|---------|
| S-23 | ground-check | Pre-write evidence verification (truth gate) |
| S-32 | content-audit | Semantic audit against knowledge |
| S-48 | content-eval | Multi-dimensional content evaluation against repo truth |
| S-50 | content-check | Structural/formatting validation |
| S-68 | code-smoke | Syntax and type-check Python code blocks (never executes) |
| S-70 | link-validate | Validate cross-subdomain internal links |
| S-90 | truth-audit-content | Line-level truth audit; verify each unit against knowledge model |

### Evidence Pipeline (foss-launcher unique)

| ID | Skill | Purpose |
|----|-------|---------|
| S-43 | evidence-decide | Determine per-page content actions |
| S-44 | evidence-materialize | Build canonical Product Evidence File (PEF) |
| S-45 | mental-model | Build product mental model (capability tiers, gaps) |
| S-46 | evidence-verify | Deterministic content verification against PEF |
| S-47 | truth-audit | Member-level API verification |
| S-77 | evidence-repair | Repair evidence frontmatter on validator-blocked pages |
| S-83 | evidence-enhance | Improve evidence coverage on passing pages |

### Gap-Eval Pipeline (parallel to evidence pipeline)

| ID | Skill | Purpose |
|----|-------|---------|
| S-62 | gap-eval | Verify content against clone cache (3-tier: deterministic/vector/LLM) |
| S-63 | gap-plan | Convert gap-eval findings into wave-ordered fix plan |
| S-64 | gap-report | Cross-product synthesis of gap patterns |
| S-65 | gap-apply | Execute wave-ordered fix specs (waves 1–4) |

### Content Quality

| ID | Skill | Purpose |
|----|-------|---------|
| S-17 | rubric-align | Quality gap analysis per dimension |
| S-21 | page-enhance | Apply targeted quality improvements |
| S-25 | eval-page | Assign A–F quality grade |
| S-26 | heal-page | Fix low-quality pages (grade D/F) |
| S-20 | page-update | Update content after knowledge refresh |
| S-40 | batch-remediate | Full eval→fix→LLM→re-eval remediation pipeline |
| S-41 | batch-eval-fix | Quick eval + deterministic auto-fix only |
| S-42 | category-fix | Run specific fixer on targeted files |
| S-78 | manual-edit | Operator-directed targeted content edit |
| S-79 | causal-backtrack | Resolve upstream dependency failures |
| S-88 | page-retire | Retire obsolete pages (draft:true mechanism) |
| S-94 | heal-batch | Batch healing from eval report (auto/LLM/regen modes) |

### Quality Audit

| ID | Skill | Purpose |
|----|-------|---------|
| S-95 | publish-readiness-review | Agent-executed governed inspection with publish verdict |
| S-97 | triage-confirm | Layer 2 body-prose staleness scanner (read-only) |
| S-109 | seo-review | Governance-only review gate for pending SEO recommendations |

### Orchestration / Pipeline

| ID | Skill | Purpose |
|----|-------|---------|
| S-38 | launch-product | Full FOSS product launch orchestrator |
| S-57 | site-plan | Produce pre-generation site manifest across all 5 subdomains |
| S-58 | family-sync | Update family page to reflect all launched platforms |
| S-59 | refresh-product-page | Re-generate products page with latest template |
| S-60 | launch-rollback | Revert product content to last committed state |
| S-84 | refresh-product | Full post-launch refresh cycle (14-step chain) |
| S-87 | delta-site-plan | Incremental site planning after knowledge update |
| S-106 | cleanroom-regen | 8-mode cleanroom regen workflow (inspect/snapshot/regen/diff/review/apply/verify/gate) |
| S-93 | system-heal | Audit-driven batch healing |

### Session & Workflow

| ID | Skill | Purpose |
|----|-------|---------|
| S-69 | getting-started | Bootstrap repo environment (7-step onboarding) |
| S-72 | diagnose-skill-failure | Governed diagnostic for skill/pipeline failures |
| S-73 | update-registry | Discover and register FOSS repos from GitHub orgs |
| S-71 | register-human-content | Onboard human-authored pages into quality systems |
| S-81 | commit | Stage and commit with structured conventional commits |
| S-82 | session-start | Mandatory session initialization gate |
| S-96 | plan-normalize | Execution-safe plan quality gate |
| S-110 | pipeline-harden | Parameterized pipeline hardening sprint |
| S-98 | backlog | Unified planning and backlog management (22 subcommands) |

### Translation

| ID | Skill | Purpose |
|----|-------|---------|
| S-99 | translate-page | Translate single page to one or more locales |
| S-100 | translate-batch | Batch translate entire family/platform to locales |
| S-107 | translate | Compatibility dispatcher for page or batch translation |
| S-101 | locale-patch | Propagate targeted fixes to locale translation copies |
| S-102 | repo-patrol | Scan GitHub orgs for new repos, score confidence |
| S-103 | change-sweep | Batch SHA comparison across products |
| S-104 | discovery-triage | Route patrol/sweep reports to backlog actions |
| S-105 | section-enhance | Inspect content sections, detect gaps, propose improvements |

### Internal Sub-routines (not user-callable)

| ID | Skill | Purpose |
|----|-------|---------|
| S-01 | path-guard | Enforce allowed/forbidden write paths |
| S-10 | project-phase-store | Record page creation intent |
| S-17 | rubric-align | Quality gap analysis (internal) |
| S-24 | evidence-cite | Attach evidence frontmatter citations |
| S-33 | change-guard | Pre-write knowledge gate |
| S-49 | knowledge-bootstrap | Pre-condition gate for knowledge state |
| S-56 | no-downgrade-guard | Pre-write quality comparison guard (ALLOW/WARN/BLOCK) |

## Skill Chains

```
Discovery:    S-39 → discovered.json → S-38 (per product)
New page:     S-10 → S-18 → S-19 → S-22 → S-23 → S-24 → S-01 → write
Maintenance:  S-12 → S-13 → S-14 → S-20 → S-23 → S-24 → S-01 → write
Enhancement:  S-17 → S-21 → S-23 → S-01 → write
Healing:      S-25 → S-26 → S-23 → S-25 → S-01 → write (or escalate)
Launch:       S-38 orchestrates:
                Phase 1   (knowledge):  S-34 → S-35 → S-31 → S-15 → S-37
                Phase 1.5 (evidence):   S-44 → S-45 → S-43 (decision.json)
                Phase 2   (pages):      [S-10 → S-18 → S-19 → S-23 → S-24 → S-01] × page types
                Phase 3   (consistency): S-36
                Phase 4   (report):     reports/launch/{family}-{platform}-{timestamp}.md
```

## Project Structure

```
foss-launcher-skills/
├── runs/                      # pipeline run artifacts (gitignored)
├── skills/                    # 93 canonical skill files (86 user-callable + 7 internal)
│   └── registry.yaml             # Machine-readable skill registry (authoritative IDs)
├── scripts/                   # Python tooling
│   ├── scout.py               # Tree-sitter knowledge extraction
│   ├── merge.py               # Knowledge consolidation engine
│   ├── index.py               # Knowledge index generation
│   ├── embed.py               # Vector embedding (3-tier)
│   ├── corpus_scan.py         # Golden corpus profiling
│   ├── discover.py            # GitHub org product discovery
│   ├── golden_index.py        # Golden corpus index builder
│   ├── golden_conformance.py  # Conformance checking vs golden
│   ├── refresh_golden.py      # Golden corpus refresh
│   ├── config_loader.py       # Shared config resolution (fail-fast ConfigError)
│   ├── readme_sync.py         # README staleness detection
│   ├── check_setup.py         # Validate operator environment and knowledge readiness
│   ├── ops_log.py             # Append-only pipeline audit log
│   ├── path_guard.py          # Enforce forbidden write paths
│   ├── pre_write.py           # Pre-write gate: path_guard + audit_files
│   ├── validate_skills.py     # CI validator: unique IDs, registry completeness
│   ├── sync_commands.py       # Sync skills/ → .claude/commands/
│   ├── sync_agents.py         # Sync skills/ → .agents/ and .kilocode/ mirrors
│   ├── _skill_constants.py    # INTERNAL_SKILLS frozenset constant
│   ├── launcher_adapter.py    # Boundary layer for upstream launcher scripts; drift detection
│   ├── decide.py              # Evidence decision engine
│   ├── differ.py              # Knowledge diff helper
│   ├── materialize.py         # Build Product Evidence File (PEF)
│   ├── mental_model.py        # Build product mental model
│   ├── schema_validate.py     # YAML/JSON schema validation helper
│   ├── verify.py              # Deterministic content verification
│   ├── quarterly_readiness.py # Simulate quarterly reviewer rubric; output: reports/score-readiness-{date}.md
│   ├── verify_claims.py       # Trace AGENTS.md/skill claims to implementing tests
│   ├── content_repo_adapter.py # Content repo path resolution adapter
│   ├── local_gate.py          # Local pre-push validation gate
│   ├── generate_status.py     # Auto-generate STATUS.md test-count entries
│   ├── claim_lookup.py        # Deterministic claim ID resolver from PEF
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
├── evidence/                  # Product Evidence Files (PEF) — regenerated by pipeline
├── knowledge/                 # Knowledge artifacts (per family/platform)
├── repos/                     # Cloned FOSS repositories
├── tests/                     # Test suite (10 test files + fixtures)
├── output/                    # Generated content (install tests)
├── backlog/                   # Planning and task backlog files
├── data/                      # Static data files
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

### The validation pipeline (two complementary tools):

```
Pre-write gate:   scripts/pipeline/commands/content/audit.py       (S-23 ground-check)
                  → verifies API tokens, evidence frontmatter, internal links
                  → FAIL blocks the write

Post-write grade: scripts/pipeline/content_eval/  (S-25 eval-page / S-40 batch-remediate)
                  → assigns A–F quality grades, runs content evaluators
                  → FAIL triggers remediation, not write block
```

Use `audit.py` before writing any content page. Use `content_eval` to measure and improve
quality of already-written pages. See `AGENTS.md §12` for detailed usage guidance.

### The enforcement layer:

```
check_setup.py → validate environment + knowledge readiness (min 50 claims / 10 classes)
pre_write.py   → path_guard (forbidden paths) + audit_files (ground-check gate)
               → missing knowledge model = FAIL (exit 1), not silent skip
ops_log.py     → append-only audit trail for all pipeline write operations
```

Run `python scripts/check_setup.py` before any content generation session.
Run `python scripts/validate_skills.py` in CI to catch skill registry drift.
Run `python scripts/sync_commands.py --check` to verify `.claude/commands/` is in sync with `skills/`.

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
