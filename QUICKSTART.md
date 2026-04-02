# QUICKSTART — foss-launcher-skills

A first-time operator's guide to generating FOSS product documentation with Claude Code, Codex CLI, or Kilo Code.

---

## 1. Prerequisites

| Requirement | Minimum version | Notes |
|-------------|----------------|-------|
| Python | 3.10+ | Used by all pipeline scripts |
| git | any | Required to clone source repos |
| Agent CLI | any | Claude Code, Codex CLI, or Kilo Code |
| Hugo content repo | — | The target repo where content is written |

Install Python 3.10 or later from https://www.python.org/downloads/ and confirm:

```bash
python --version
# Python 3.10.x or higher
```

Install your agent CLI. Examples:

```bash
# Claude Code
npm install -g @anthropic-ai/claude-code

# Codex CLI
npm install -g @openai/codex
```

---

## 2. Install Python dependencies

From the root of this repo:

```bash
pip install -r scripts/requirements.txt
```

This installs:

- `tree-sitter>=0.25` — parsing engine used by `scout.py`
- `tree-sitter-language-pack>=0.13` — language grammars for Python, Java, C++, TypeScript, JavaScript (auto-installed, no manual grammar build needed)
- `tree-sitter-c-sharp>=0.23` — C# / .NET grammar
- `pyyaml>=6.0` — YAML parsing for knowledge artifacts
- `requests>=2.28` — HTTP client for optional API lookups

Verify the install:

```bash
python -c "import tree_sitter; import tree_sitter_language_pack; print('OK')"
```

If you see `ModuleNotFoundError`, use the `--user` flag:

```bash
pip install -r scripts/requirements.txt --user
```

---

## 3. Configure your content repo

The skills read and write content to an external Hugo repository. You must tell the system where that repo lives before running any content skill.

### Option A — environment variable (recommended for CI and shell sessions)

```bash
export CONTENT_REPO_PATH=/path/to/your-content-repo
```

```powershell
# Windows PowerShell
$env:CONTENT_REPO_PATH = "C:\path\to\your-content-repo"
```

The variable is read at runtime by every pipeline script via `scripts/config_loader.py`. It overrides any value in `config.yaml`.

### Option B — config.yaml (recommended for standalone mode)

Open `config.yaml` in the root of this repo and set `content_repo`:

```yaml
content_repo: "/path/to/your-content-repo"
```

The installer (Section 4) sets this automatically in standalone mode.

---

## 4. Install skills into your content repo

The installer has two modes:

| Mode | What it does |
|------|-------------|
| **Embedded** (default) | Copies `scripts/`, `configs/`, `config.yaml`, and skill files into the target repo |
| **Standalone** | Skills stay in this repo; writes `content_repo` to `config.yaml` and a `.skills-link` marker in the target |

### Embedded mode

```bash
# Unix / macOS
./install.sh /path/to/your-content-repo

# Windows PowerShell
.\install.ps1 -Target C:\path\to\your-content-repo
```

After installation the target repo contains `scripts/`, `configs/`, `config.yaml`, `AGENTS.md`, and agent command directories (`.claude/commands/`, `.agents/`, `.kilocode/`).

### Standalone mode (skills stay here)

```bash
# Unix / macOS
./install.sh --standalone /path/to/your-content-repo

# Windows PowerShell
.\install.ps1 -Target C:\path\to\your-content-repo -Standalone
```

Standalone mode writes `content_repo: "/path/to/your-content-repo"` into `config.yaml` and runs `tools/distribute.py` to generate agent command directories in this repo.

After either mode, install Python dependencies (if you have not already):

```bash
pip install -r scripts/requirements.txt
```

---

## 5. Your first knowledge extraction

Knowledge extraction reads a FOSS source repository and produces structured artifacts in `knowledge/{family}/{platform}/scout/`. These artifacts are the ground truth for all content generation — nothing is written to your content repo without them.

### Step 5.1 — Clone a FOSS repository

```bash
git clone https://github.com/aspose-words/Aspose.Words-for-Python-via-.NET.git \
  /repos/aspose-words-python
```

The repo must be accessible on the local filesystem. Alternatively, `repo-scout` can auto-install from pip if you omit the repo path (see Step 5.2 below).

### Step 5.2 — Run /repo-scout

Open Claude Code (or your agent CLI) in the root of this repo and run:

```
/repo-scout words python /repos/aspose-words-python
```

Arguments: `{family} {platform} [{repo-path}]`

- `family` — product family identifier (e.g. `words`, `cells`, `pdf`, `3d`)
- `platform` — one of `python`, `net`, `java`, `cpp`, `typescript`
- `repo-path` — optional; when omitted the skill installs the pip package automatically

The skill calls:

```bash
python scripts/pipeline/scout.py \
  words python /repos/aspose-words-python \
  knowledge/words/python/scout/
```

### Step 5.3 — Verify scout outputs

After `/repo-scout` completes, confirm these files exist:

```
knowledge/words/python/scout/
  model.yaml              # family, platform, version, repo_sha, source: scout
  api_surface.json        # list of classes with methods and properties
  claims.json             # factual claims array
  formats.json            # format support matrix (import/export)
  class_graph.json        # dependency relationships between classes
  coverage_matrix.json    # coverage statistics
  limitations.md          # known limitations table
  snippets/
    snippets_index.json   # code examples extracted from tests/ or examples/
```

A successful run prints a summary like:

```
words/python: 142 classes, 1847 methods, 38 snippets
repo_sha: a3f9c21...
output: knowledge/words/python/scout/
```

If `snippet_count: 0` appears, the repo has no `tests/` or `examples/` directory accessible to tree-sitter. This is not an error — snippets are optional.

---

## 6. Your first content page

With scout outputs in place, run three more skills to build the full knowledge model, then generate a page.

### Step 6.1 — Merge knowledge (/truth-merge)

```
/truth-merge words python
```

This runs `scripts/pipeline/merge.py words python` and produces:

```
knowledge/words/python/merged/
  model.yaml
  claims.json        # with provenance tags (scout_only / dual / fl_only)
  api_surface.json
  api_surface.md     # human-readable API reference injected into LLM prompts
  formats.json
  formats.md
  merge_report.md    # statistics: claim counts, dual-confirmed rate
  snippets/
    snippets_index.json
```

Check `merge_report.md` to confirm claim counts look reasonable. A `scout_only` source is normal when no FL (FOSS-Launcher) data exists yet.

### Step 6.2 — Index knowledge (/truth-index)

```
/truth-index words python
```

This runs `scripts/pipeline/index.py words python` and writes:

```
knowledge/words/python/merged/index.json   # api_confidence, forbidden_claims, stats
knowledge/_index.json                       # cross-product summary
```

`api_confidence: "high"` indicates deterministic scout data — safe to generate content.

### Step 6.3 — Generate a docs page (/new-docs-page)

```
/new-docs-page words python getting-started installation
```

Arguments: `{family} {platform} {section} {slug}`

Valid sections: `getting-started` | `developer-guide`

The skill reads `knowledge/words/python/merged/` to ground every claim, then writes:

```
{CONTENT_REPO_PATH}/content/docs.aspose.org/en/words/python/getting-started/installation.md
```

### Step 6.4 — Verify with ground-check (/ground-check)

```
/ground-check content/docs.aspose.org/en/words/python/getting-started/installation.md
```

Ground-check verifies that every factual claim in the page traces back to a verified knowledge artifact. It checks:

- Claim traceability against `claims.json`
- API names against `api_surface.json`
- Format claims against `formats.json`
- Forbidden claims (unsupported features or removed API) are blocked

Expected output:

```
GROUND CHECK — content/docs.aspose.org/en/words/python/getting-started/installation.md
...
RESULT: PASS
Report: reports/ground-check/words-python-installation-<timestamp>.md
```

A `WARN` result means minor ungrounded claims — review and fix before committing. A `FAIL` blocks the write entirely; revise the page and re-run (maximum 2 retries before human escalation).

You can also run the audit script directly against the output file:

```bash
python scripts/pipeline/audit.py --files \
  /path/to/content-repo/content/docs.aspose.org/en/words/python/getting-started/installation.md
```

---

## 7. Full product launch

For a new product, use `/launch-product` to run the complete pipeline in one invocation rather than sequencing each skill manually.

```
/launch-product words python /repos/aspose-words-python
```

Arguments: `{family} {platform} {repo-path}`

The orchestrator runs four phases:

**Phase 1 — Knowledge extraction**
1. `/repo-scout words python /repos/aspose-words-python`
2. `/truth-merge words python`
3. `/truth-index words python`
4. `/embed-knowledge words python` (skipped if no vector store configured)
5. `/corpus-scan words python docs|blog|kb|reference`
6. `/evidence-materialize words python`
7. `/mental-model words python`
8. `/evidence-decide words python`

A confidence gate reads `index.json` after Phase 1. If `api_confidence` is `low`, the launch halts before writing any content.

**Phase 2 — Page generation** (minimum viable launch set)
- `getting-started/installation` docs page
- `getting-started/quick-start` docs page
- launch announcement blog post
- KB how-to getting-started guide
- KB FAQ page
- Up to 10 API reference pages (top public classes by method count)

Every page passes through ground-check (S-23) before being written. Pages that fail ground-check after one retry are skipped and logged.

**Phase 3 — Cross-platform consistency** (skipped if this is the first platform in the family)

**Phase 4 — Launch report** written to `reports/launch/words-python-<timestamp>.md`

### Expected terminal output

```
LAUNCH COMPLETE — words/python
Repository: /repos/aspose-words-python
Knowledge SHA: a3f9c21...
API confidence: high

Phase 1 — Knowledge:
  Scout:      OK
  Merge:      OK (0 conflicts)
  Index:      OK
  Embed:      SKIPPED
  Corpus:     OK (docs, blog, kb, reference)

Phase 2 — Pages:
  Written:    15
  Skipped:    0

Phase 3 — Cross-platform: SKIPPED

Launch report: reports/launch/words-python-2026-03-31T12:00:00Z.md
```

---

## 8. Verify outputs

After a launch, check these locations:

### Knowledge artifacts (in this repo)

```
knowledge/words/python/
  scout/          # raw extraction outputs
  merged/         # reconciled knowledge model
    model.yaml    # check: stale_since: null, source: scout_only or dual
    index.json    # check: api_confidence: high
    api_surface.md
    merge_report.md
```

### Content pages (in your content repo)

```
content/docs.aspose.org/en/words/python/getting-started/
  installation.md
  quick-start.md

content/blog.aspose.org/words/python/
  words-python-launch.md

content/kb.aspose.org/en/words/python/
  how-to-get-started-with-words-python.md
  faq.md

content/reference.aspose.org/en/words/python/
  Document.md
  DocumentBuilder.md
  ...
```

### Reports

```
reports/
  launch/words-python-<timestamp>.md   # launch summary
  ground-check/                        # per-page verification results
  audit/                               # API accuracy audit logs
```

### Success criteria

- Every page in `content/` has `<!-- evidence: ... -->` citations in the body
- `model.yaml` shows `stale_since: null`
- `index.json` shows `api_confidence: "high"`
- All ground-check reports show `RESULT: PASS` or `RESULT: WARN`
- `merge_report.md` shows non-zero `merged_claims`

---

## 9. Troubleshooting

### tree-sitter not found

```
ModuleNotFoundError: No module named 'tree_sitter'
```

Fix:

```bash
pip install tree-sitter tree-sitter-language-pack tree-sitter-c-sharp --user
USER_SITE=$(python -m site --user-site)
PYTHONPATH="$USER_SITE" python -c "import tree_sitter; print('OK')"
```

The `repo-scout` skill automatically prepends `$USER_SITE` to `PYTHONPATH` before running `scout.py`.

### CONTENT_REPO_PATH not set

```
ERROR: content repo not configured
```

Fix — set the environment variable:

```bash
export CONTENT_REPO_PATH=/path/to/your-content-repo
```

Or set `content_repo` in `config.yaml` (see Section 3).

### 0 classes extracted

```
WARN: 0 classes extracted — verify repo_path points to package root
```

The repo path points to a directory that contains no Python (or target language) source files at the expected depth. Check that `repo-path` points to the root of the package, not a parent directory or a subdirectory of one file.

For a Python repo, `repo-path` should contain `.py` files or subdirectories with `.py` files directly under it.

### No content files found during corpus-scan

```
WARN: no existing content found for words/python docs
```

This is expected for a brand-new product. The skill falls back to default templates. No action needed; page generation proceeds normally.

### Knowledge model stale

```
FAIL: Knowledge is stale — run /knowledge-update first
```

`model.yaml` has `stale_since` set to a non-null timestamp, meaning the upstream repo has changed since the last scout run. Fix:

```
/knowledge-diff words python
/repo-scout words python /repos/aspose-words-python
/truth-merge words python
/truth-index words python
```

Then retry your content generation skill.

### Wrong platform folder name

Platform folder names are fixed identifiers — do not use aliases:

| Platform | Correct identifier | Wrong |
|----------|--------------------|-------|
| .NET / C# | `net` | `dotnet`, `csharp` |
| Python | `python` | `py` |
| Java | `java` | `jvm` |
| C++ | `cpp` | `c++`, `cplusplus` |
| TypeScript | `typescript` | `ts` |

Using the wrong identifier causes scripts to write artifacts to the wrong path and content skills to fail their pre-condition checks.

### audit.py usage

To audit a single content file:

```bash
python scripts/pipeline/audit.py --files path/to/file.md
```

To audit all content for a product:

```bash
python scripts/pipeline/audit.py words python
```

To audit all products:

```bash
python scripts/pipeline/audit.py all
```

Machine-readable JSON output:

```bash
python scripts/pipeline/audit.py all --json
```
