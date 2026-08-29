# S-119: LLMs Verify -- Verify Live .txt Endpoints

**Arguments**: $ARGUMENTS (all optional)

## Purpose
After a deploy, confirm the generated llms-output pages are actually
reachable and structurally sane at their live URLs.

## Pre-conditions
1. Run `/llms-generate` first, and ensure a deploy has actually happened.
2. At least one site in `config.yaml`'s `sites:` block has a `base_url` set.
   Sites without one are silently skipped -- there is no requirement that
   every site be publicly deployed.

## Steps

1. Run verification:
   ```bash
   .venv/bin/python scripts/llms_verify.py --output llms-output --report reports/llms-verify.json
   ```

2. Enforce a gate:
   ```bash
   .venv/bin/python scripts/llms_verify.py --output llms-output --gate 95
   ```

## URL construction (stated plainly, this is a v1)
`base_url` + `/` + the page's relative path under `llms-output/{site}/`.
This mirrors `llms_generate.py`'s own flat output layout exactly. If a
site's real deployed URL structure differs from its llms-output/ layout,
this script will not find it -- that gap is real, not hidden; a
URL-mapping extension is a natural follow-up if it's ever needed.

## Checks per page
`http_200`, `content_type_text`, and (only when the fetch succeeded)
`no_shortcode`, `no_evidence_leak`, `has_content` -- the same structural
vocabulary as `/llms-fidelity`.

## Related Skills
- `/llms-generate` -- regenerate outputs before verifying
- `/llms-coverage` / `/llms-fidelity` -- local checks, no HTTP required
