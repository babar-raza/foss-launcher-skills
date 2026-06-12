# ADR-005: Content Repository Separation

**Date:** 2026-04-27
**Status:** Accepted
**Deciders:** @prora

## Context

The original Aspose documentation system had skills, knowledge, and generated content all in a single monolithic repository. This created several problems:

1. **Commit noise**: Automated content generation produced large commits that obscured governance changes
2. **Access control**: Content editors and skills developers have different permission needs
3. **Deploy coupling**: Deploying new skills required re-deploying the content publishing pipeline
4. **Knowledge portability**: Knowledge artifacts could not be shared across multiple content repos

## Decision

We separate the system into two repositories:

1. **Skills repo** (this repo, `foss-launcher-skills-gitlab`): Contains skills definitions, Python scripts, CI/CD governance, tests, and knowledge artifacts. No generated content lives here.

2. **Content repo** (external, configured via `$CONTENT_REPO_PATH`): Contains all Hugo content (`content/docs.aspose.org/`, `content/blog.aspose.org/`, etc.), themes, layouts, and configs.

The skills repo references the content repo via the `CONTENT_REPO_PATH` environment variable or `config.yaml:content_root`. All content-writing skills write to the content repo's path, not to this repo.

## Separation Invariants

- The skills repo NEVER commits content pages
- The content repo NEVER contains skill definitions or Python scripts
- Knowledge artifacts live in the skills repo (`knowledge/`), read by skills when generating content for the content repo
- The CI for this repo validates skills, tests, and governance only — never content quality directly

## Alternatives Considered

- **Monorepo with subdirectory isolation**: Rejected — CODEOWNERS and CI triggers become complex; content commits still pollute the skills history.
- **Database-backed content store**: Rejected — adds infrastructure dependency; git-based content stores are standard for Hugo/static sites.

## Consequences

- Operators must set `CONTENT_REPO_PATH` before running any content-writing skill
- `config.yaml:content_root` provides a persistent override for local development
- The pre-write gate (`scripts/pre_write.py`) validates paths within the content repo, not this repo
- Tests use `tests/fixtures/content/` as a mock content repo (set via `CONTENT_REPO_PATH=tests/fixtures`)

## Implementation

- Config loader: [`scripts/config_loader.py`](../../scripts/config_loader.py)
- Content repo adapter: [`scripts/content_repo_adapter.py`](../../scripts/content_repo_adapter.py)
- Environment setup: [`.env.example`](../../.env.example)
- CLAUDE.md rule: [`CLAUDE.md`](../../CLAUDE.md) "Configure content root"
- CI test fixtures: [`tests/fixtures/`](../../tests/fixtures/)
