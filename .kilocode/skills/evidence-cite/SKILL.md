---
name: evidence-cite
id: S-24
description: >
  Attach evidence frontmatter to content pages using knowledge artifacts.
args: "{content-file-path}"
---

# S-24: Evidence Cite - Attach Knowledge Citations

Write or update the `evidence:` YAML frontmatter block in a content page.
Do not use inline HTML comments. Use `python scripts/pipeline/attach_evidence.py --files {content-file-path}`
for code pages, and fill `evidence.claims` from `knowledge/{family}/{platform}/merged/claims.json`
for prose-only pages.

The current policy is:
- evidence lives in frontmatter
- `ground_check:` is forbidden
- HTML comment citations are forbidden
- rerunning `attach_evidence.py` must be deterministic
