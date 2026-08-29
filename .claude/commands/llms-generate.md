# S-116: LLMs Generate -- Produce LLM-Consumption Text Outputs

**Arguments**: $ARGUMENTS (all optional; default is every site in config.yaml)

## Purpose
Produce plain-text, LLM-friendly renderings of every eligible content page,
plus a per-site index, so an LLM agent (or a crawler serving one) can consume
this repo's content without parsing Hugo templates or shortcodes.

## Pre-conditions
1. `config.yaml` has a non-empty `sites:` block (this repo ships one by default).
2. `CONTENT_REPO_PATH` env var or `config.yaml:content_repo` points at a real
   content repo checkout.

## Steps

1. Run the generator for all configured sites:
   ```bash
   .venv/bin/python scripts/llms_generate.py --output llms-output
   ```
   Or a subset:
   ```bash
   .venv/bin/python scripts/llms_generate.py --output llms-output --sites docs,kb
   ```

2. Spot-check outputs:
   ```bash
   cat llms-output/docs/llms.txt
   ```

3. Follow up with `/llms-coverage` and `/llms-fidelity` to verify the run.

## Output
- `llms-output/{site}/llms.txt` -- per-site index (page list + titles)
- `llms-output/{site}/{mirrored content path}.txt` -- one text file per
  eligible page, with a small header block (Site/Title/Source) followed by
  the page body with Hugo frontmatter stripped

## Idempotency
Running twice with unchanged source content produces byte-identical output
(deterministic sorted file order, no timestamps embedded in bodies).

## Scope cut (stated explicitly, not silently dropped)
This generalized port does **not** implement the upstream source's
nested per-product llms.txt hierarchy, its provenance-hash staleness
manifest (source's `/llms-stale`), or live-HTTP deploy verification
(source's `/llms-verify`). Those are deferred -- see `TASK_BACKLOG.md`
and `docs/parity/source-anchors.yaml`.

## Related Skills
- `/llms-coverage` -- audit coverage gap between content/ and llms-output/
- `/llms-fidelity` -- audit content fidelity (source vs. output comparison)
