# Vector Regeneration Procedure

## Overview

The gap-eval Tier 2 vector search (`knowledge/_vectors/`) and the claim/API
embedding stores (`knowledge/{family}/{platform}/merged/`) require periodic
regeneration when:

1. The embedding model changes (model drift)
2. Knowledge artifacts are updated (new claims extracted)
3. The vector directory is corrupted or missing
4. A new product is launched and has no vectors

Vectors are gitignored (`knowledge/_vectors/` is listed in `.gitignore`).
They are local-only pipeline state and must be regenerated on each new clone
or after a forced wipe.

---

## Embedding Models (from `scripts/pipeline/config/llm_registry.yaml`)

| Tier | Provider | Model | Use |
|------|----------|-------|-----|
| Tier 1 | llm.professionalize.com | `qwen3-embedding-8b` | Gap-eval API surface vectors |
| Tier 2 | llm.professionalize.com | `nomic-embed-text` | Fallback embeddings |

**Model pinning**: The model used for generation must match the model used for
queries. If you change the model in `llm_registry.yaml`, ALL existing vectors
must be regenerated before gap-eval Tier 2 searches will work correctly.

To document the current model used for a vector set, record it in
`knowledge/_vectors/config.json` (created automatically by `embed.py`).

---

## Quick Reference

### Bootstrap vectors for all launched products

```bash
.venv/Scripts/python -m scripts.pipeline.commands.knowledge.embed gap-index all
```

### Bootstrap vectors for a single product

```bash
.venv/Scripts/python -m scripts.pipeline.commands.knowledge.embed gap-index {family} {platform}
# Example:
.venv/Scripts/python -m scripts.pipeline.commands.knowledge.embed gap-index pdf java
```

### Re-embed knowledge claims after knowledge update

```bash
# After running /knowledge-update {family} {platform}:
.venv/Scripts/python -m scripts.pipeline.commands.knowledge.embed {family} {platform}
# Example:
.venv/Scripts/python -m scripts.pipeline.commands.knowledge.embed cells net
```

### Re-embed all products

```bash
.venv/Scripts/python -m scripts.pipeline.commands.knowledge.embed all
```

---

## When Vectors Are Stale

Symptoms of stale or missing vectors:
- Gap-eval Tier 2 returns 0 results for all queries
- `knowledge/_vectors/` directory is empty or missing
- Config in `knowledge/_vectors/config.json` shows a different model than
  what is in `llm_registry.yaml`

**To check**:

```bash
ls knowledge/_vectors/
cat knowledge/_vectors/config.json  # if it exists
```

**To fix**: Run the bootstrap command above for affected products. For a full
wipe and regeneration:

```bash
rm -rf knowledge/_vectors/
.venv/Scripts/python -m scripts.pipeline.commands.knowledge.embed gap-index all
```

---

## Model Change Procedure

When upgrading embedding models (e.g. qwen3-embedding-8b -> new-model):

1. Update `llm_registry.yaml` with new model name
2. Wipe all existing vectors: `rm -rf knowledge/_vectors/`
3. Regenerate: `.venv/Scripts/python -m scripts.pipeline.commands.knowledge.embed gap-index all`
4. Verify: run gap-eval on one product and confirm Tier 2 returns cosine scores
5. Update the calibration history in `docs/pipeline/tfidf-threshold-calibration.md`
   (embedding-based similarity thresholds may need recalibration with the new model)

---

## Launched Products Reference

As of 2026-06-11, the 21 launched products requiring vectors:

| Family | Platform |
|--------|----------|
| 3d | net, java, python, typescript |
| cells | net, java, python, typescript |
| email | net, java, cpp, python |
| font | net, java, python |
| note | net, java |
| pdf | net, java, go, python |
| slides | net, java, cpp, python |
| words | net, java, python |
| page | python |
| tex | python |

Use `embed gap-index all` to discover and embed all of these automatically.
