---
name: rubric-align
id: S-17
description: >
  Assess a content page against the quality rubric using content_eval.
args: "{relative-file-path}"
---

# S-17: Rubric Align

Mirror of the canonical contract in `skills/rubric-align.md`.

Run:
```bash
cd scripts/pipeline
python -m content_eval evaluate --files ../../{relative-file-path} --format json
```
