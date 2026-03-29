---
name: knowledge-bootstrap
description: >
  Shared pre-condition gate for knowledge state
args: "{family} {platform}"
---

# Knowledge Bootstrap

Current chain:

```text
repo-scout -> knowledge-enrich -> truth-merge -> truth-index
```

Do not use `truth-sync`. If knowledge is stale, refresh with the current pipeline.
