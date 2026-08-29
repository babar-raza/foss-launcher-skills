# S-118: LLMs Fidelity -- Audit Content Fidelity

**Arguments**: $ARGUMENTS (all optional)

## Purpose
Score each generated page against its source across title preservation,
heading/code-fence/table counts, and absence of Hugo-shortcode or
evidence-frontmatter leakage -- catches quality regressions that a plain
presence/coverage check (`/llms-coverage`) would miss.

## Pre-conditions
Run `/llms-generate` first.

## Steps

1. Run the fidelity audit:
   ```bash
   .venv/bin/python scripts/llms_fidelity.py --output llms-output --report reports/llms-fidelity.json
   ```

2. Enforce a gate:
   ```bash
   .venv/bin/python scripts/llms_fidelity.py --output llms-output --gate 90
   ```

## Fidelity Dimensions (per page, each worth 1/6 of the page score)

| Check | Description |
|-------|-------------|
| `title_preserved` | Source title appears near the top of the output |
| `h2_count_ok` | Output H2 count >= source H2 count (headings not dropped) |
| `code_fence_count_ok` | Output code-fence count >= source code-fence count |
| `table_row_count_ok` | Output table-row count >= source table-row count |
| `no_shortcode` | No `{{` or `{%` in output (Hugo shortcodes not leaked) |
| `no_evidence_field` | No `claim_id:`/`model_sha:`/`graded_content_hash:` leakage |

## Gate
Default recommendation: overall score >= 90%. Pages scoring below 80% count
as `failing_pages` for that site.

## Negative Control (how to verify the auditor actually catches regressions)
Take a generated .txt output, delete one of its `##` sections, and re-run.
That page's score must drop below 80% -- if it doesn't, the auditor itself
is broken. (This exact scenario is covered by an automated negative-control
test: `tests/test_llms_generate.py::test_fidelity_negative_control_detects_dropped_section`.)

## Related Skills
- `/llms-generate` -- regenerate to fix a fidelity issue
- `/llms-coverage` -- checks presence, not quality
