# content_eval/ — Multi-Dimensional Content Evaluation

A 16-evaluator system for assessing content pages against the knowledge model across multiple quality dimensions: API accuracy, platform purity, structural quality, risk language, evidence depth, and more.

## Overview

The DEFAULT set (9 evaluators) is fast, deterministic, and safe for unattended runs. The remaining 7 evaluators are slower, experimental, or require additional knowledge artifacts.

## All Evaluators

| Name | Default? | Purpose |
|------|----------|---------|
| `api_accuracy` | Yes | Verify API token references against `api_surface.json` |
| `platform_purity` | Yes | Detect foreign-platform code in code blocks and prose |
| `forbidden_claims` | Yes | Flag text matching forbidden/not-implemented claims |
| `page_role` | Yes | Verify page has an identifiable content role (tutorial, reference, etc.) |
| `structure` | Yes | Check heading hierarchy, section presence, placeholder detection |
| `risk_language` | Yes | Flag unsupported superlatives and marketing language |
| `evidence_depth` | Yes | Check `evidence:` frontmatter completeness |
| `prose_truth` | Yes | Token-overlap scoring of prose paragraphs against claims |
| `code_plausibility` | Yes | Detect implausible code patterns and syntax issues |
| `api_backtick` | No | Check that API identifiers use backtick formatting |
| `claim_coverage` | No | Measure how many known claims are referenced |
| `format_truth` | No | Verify format claims against `formats.json` direction |
| `install_recipe` | No | Validate install instructions against platform conventions |
| `limitations_check` | No | Detect references to known-unimplemented features |
| `coverage` | No | Snippet coverage — classes mentioned vs. classes with examples |
| `type_accuracy` | No | Verify type annotation references |

## CLI Usage

The `content_eval` package must be invoked as a module from the `scripts/pipeline/` directory, or using the full module path from the repo root.

```bash
# From scripts/pipeline/ directory:
python -m content_eval evaluate 3d python
python -m content_eval evaluate all
python -m content_eval evaluate --files content/docs.aspose.org/en/3d/python/index.md

# From repo root:
cd scripts/pipeline && python -m content_eval evaluate 3d java

# Select specific evaluators
python -m content_eval evaluate 3d python --evaluators api_accuracy,platform_purity

# JSON output
python -m content_eval evaluate 3d python --format json

# Include cross-page consistency checks
python -m content_eval evaluate 3d python --cross-page

# Exit 1 on any FAIL finding
python -m content_eval evaluate 3d python --strict

# Include remediation plan in output
python -m content_eval evaluate 3d python --remediation

# Dry run (print pages that would be evaluated)
python -m content_eval evaluate 3d python --dry-run

# Compare two reports
python -m content_eval diff reports/content_eval/eval-old.json reports/content_eval/eval-new.json
```

## Sub-packages

| Package | Purpose |
|---------|---------|
| `evaluators/` | 16 evaluator modules (BaseEvaluator subclasses, auto-registered) |
| `cross_page/` | `consistency.py`, `platform_alignment.py` — cross-page checks (enabled with `--cross-page`) |
| `extractors/` | Stub (future extension point) |
| `remediation/` | `triage.py`, `planner.py`, `runner.py`, `fixers/` — AUTO/LLM/HUMAN/SKIP classification |
| `reporters/` | `json_report.py`, `markdown.py` — report formatters |

## Grading

Grade is based on FAIL count across all evaluated pages:

| Grade | FAIL count |
|-------|-----------|
| A | 0 |
| B | 1–3 |
| C | 4–6 |
| D | 7–10 |
| F | 11+ |

Check `cli.py` for current thresholds — they are computed per-page then aggregated.

## Evaluator Architecture

Each evaluator is a class that:
1. Subclasses `BaseEvaluator` from `evaluators/__init__.py`
2. Sets a `name` class attribute matching the entry in `config.py`
3. Implements `evaluate(page: Page, knowledge: Knowledge) -> list[Finding]`
4. Self-registers when the module is imported

Evaluator modules are discovered and registered by `_ensure_loaded()` in `evaluators/__init__.py`.

## Models

| Class | Module | Description |
|-------|--------|-------------|
| `Page` | `models.py` | Content page: filepath, frontmatter, prose lines, code blocks, family, platform |
| `Finding` | `models.py` | Single evaluation result: level, category, filepath, line_no, message, suggestion, evaluator |
| `EvalReport` | `models.py` | Aggregated report: findings list, evaluators run, pages evaluated, scope |

## Remediation Workflow

```bash
# 1. Triage: classify findings without modifying files
python scripts/pipeline/commands/content/remediate.py triage reports/content_eval/eval-*.json

# 2. Fix: apply auto-fixable findings
python scripts/pipeline/commands/content/remediate.py fix reports/content_eval/eval-*.json

# 3. Dry run to preview changes
python scripts/pipeline/commands/content/remediate.py fix reports/content_eval/eval-*.json --dry-run

# 4. Fix specific categories only
python scripts/pipeline/commands/content/remediate.py fix reports/content_eval/eval-*.json --categories ST,RV

# 5. Full report (triage + fix + report)
python scripts/pipeline/commands/content/remediate.py report reports/content_eval/eval-*.json

# 6. Show status of a remediation report
python scripts/pipeline/commands/content/remediate.py status reports/remediation/rem-*.json
```

Triage buckets:
- `AUTO` — deterministic fixers available (structural issues, placeholder text, risk language)
- `LLM` — requires LLM-assisted rewriting (prose accuracy, claim coverage)
- `HUMAN` — requires human judgment (page role, design decisions)
- `SKIP` — already fixed or not applicable

## Output

Reports are written to `reports/content_eval/`. Default format is Markdown; use `--format json` for machine-readable output suitable as input to `remediate.py`.

Report filename pattern: `eval-{YYYYMMDD-HHMMSS}.{md|json}`
