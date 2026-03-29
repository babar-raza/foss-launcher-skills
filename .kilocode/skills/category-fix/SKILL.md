---
name: category-fix
id: S-42
description: >
  Run a specific fixer on targeted files by category code.
args: "{category} {file-or-directory}"
---

# S-42: Category Fix

Mirror of the canonical contract in `skills/category-fix.md`.

Use `python -m scripts.pipeline.content_eval evaluate --files {files...} --evaluators {evaluator} --format json`
followed by `python scripts/pipeline/remediate.py fix {report-path} --categories {category}`.
