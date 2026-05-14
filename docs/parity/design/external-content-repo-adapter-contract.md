# External Content Repo Adapter Contract

Status: Phase 7 foundation artifact

Implementation status: initial helper implemented in `scripts/content_repo_adapter.py` with tests in `tests/test_content_repo_adapter.py`.

## Purpose

Standalone skills must operate against an external content repository without assuming the skills repo itself is the Hugo website repo. This contract defines the shared adapter behavior for content paths, output paths, clone-cache paths, dry-run execution, and metrics handling.

## Required Inputs

- `CONTENT_REPO_PATH`: optional environment variable pointing to the external content repo.
- `config.yaml:content_root`: optional config fallback when `CONTENT_REPO_PATH` is not set.
- `--output-root`: preferred CLI override for generated reports, dry-run outputs, and shadow writes.
- `ASPOSE_CLONE_CACHE`: optional clone-cache override. It must not point to an obsolete `foss-launcher` clone-cache path.
- `AGENT_METRICS_ENDPOINT` and `AGENT_METRICS_TOKEN`: production metrics submission settings. They must never be required for dry-run verification.

## Resolution Order

1. For content reads, resolve content root from `CONTENT_REPO_PATH`, then `config.yaml:content_root`.
2. For content writes, require one of:
   - explicit dry-run mode,
   - explicit redirected `--output-root`,
   - a taskcard-approved external content root that is not `D:/onedrive/Documents/GitHub/aspose.org/content`.
3. For reports and evidence, prefer `--output-root`; otherwise use local standalone `reports/` or `docs/parity/evidence/`.
4. For clone cache, resolve `ASPOSE_CLONE_CACHE` first, then the configured content repo cache, then standalone `runs/.clone_cache/`.

## Fail-Closed Rules

- If a skill needs content and no content root can be resolved, it must fail before doing work.
- If a resolved write target is under `D:/onedrive/Documents/GitHub/aspose.org/content`, it must fail unless a future taskcard explicitly authorizes a sandboxed fixture path under a temporary copy.
- Missing metrics credentials must not fail a dry-run or local verification command.
- A production metrics submission path must require explicit owner approval and must not print tokens.

## Adapter API Shape

Future implementation should expose a single helper, not repeated path logic:

```text
resolve_content_root(config, env) -> Path
resolve_output_root(args, default) -> Path
resolve_clone_cache(config, env) -> Path
assert_write_allowed(path, mode, taskcard_context) -> None
metrics_mode(env, args) -> dry-run | disabled | submit
```

## Non-Destructive Verification

Every content-affecting skill must support at least one of:

- `--dry-run`
- `--output-root <temp-dir>`
- fixture repo execution
- no-op manifest generation

Verification must record:

- resolved content root
- resolved output root
- whether dry-run/no-op mode was active
- list of attempted write targets
- proof that no write target is under `D:/onedrive/Documents/GitHub/aspose.org/content`

## Done Criteria For Implementations

- Config resolution is centralized.
- Content writes are blocked unless explicitly dry-run, redirected, or taskcard-approved.
- Tests cover missing content root, redirected output root, forbidden aspose.org content writes, and metrics dry-run behavior.
