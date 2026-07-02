---
name: frontmatter-body-consistency
id: S-108
description: >
  Skill description pending
---

> Cross-skill references like `/knowledge-bootstrap` refer to sibling skills in this directory.

# S-108: Frontmatter Body Consistency

Checks for contradictions between frontmatter evidence fields and body prose:
format claims, package names, removed API references, version compatibility.
Findings are WARNING-level and do not abort the chain.

**CLI:**
```bash
PYTHONPATH=scripts/pipeline .venv/Scripts/python -m commands.content.frontmatter_body_consistency \
    {family} {platform}
```
