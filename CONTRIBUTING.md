# Contributing

## Prerequisites

- Python 3.11+
- Virtual environment

## Development Setup

1. Clone the repository
2. Create and activate a virtual environment
3. Install with dev dependencies: .venv/Scripts/pip install -e ".[dev]"

## Running Tests

- Full test suite: .venv/Scripts/pytest tests/ -v -m "not scout" --ignore=tests/test_e2e_pipeline.py
- With coverage: .venv/Scripts/pytest tests/ --cov=scripts --cov-report=term-missing -m "not scout" --ignore=tests/test_e2e_pipeline.py
- Local quality gate: .venv/Scripts/python scripts/local_gate.py

## Code Style

- Follow existing patterns in scripts/ and scripts/ci/checks/
- Use from __future__ import annotations for type hints
- CI check scripts: main() -> int returning 0 (pass) or 1 (fail), with PASS:/FAIL: output prefix
- New modules under scripts/pipeline/commands/ops/ follow the ops pattern (see skill_run_manager.py)

## Pull Request Process

1. Create a feature branch from main
2. Make focused, scoped changes
3. Add tests for new behavior in tests/
4. Run pytest and verify all tests pass
5. Run validate_skills.py if skills or registry changed
6. Commit with conventional commit format: feat(scope):, fix(scope):, test(scope):
7. Open PR -- CI will run skill-governance and pipeline-tests workflows

## Skill Development

For adding or modifying skills:
- See OPERATORS_GUIDE.md for the operator workflow
- Skills are registered in skills/registry.yaml
- Each skill has a markdown definition in skills/<slug>.md
- Skill IDs follow S-NNN format (see registry for next available)

## Release Process

This project uses [Semantic Versioning](https://semver.org/) and the
[Keep a Changelog](https://keepachangelog.com/en/1.0.0/) format.

**Before releasing a new version:**

1. Update `CHANGELOG.md` — move items from `[Unreleased]` to a new version section
   with the date: `## [X.Y.Z] — YYYY-MM-DD`
2. Bump the version in `pyproject.toml`: `version = "X.Y.Z"`
3. Run the local quality gate: `.venv/Scripts/python scripts/local_gate.py`
   - This checks: registry integrity, sync, schema, tests
4. Run the full test suite with coverage: `.venv/Scripts/pytest tests/ --cov=scripts --cov-fail-under=70 -m "not scout" --ignore=tests/test_e2e_pipeline.py`
5. Create a git tag: `git tag v X.Y.Z`
6. Push the tag: `git push origin vX.Y.Z`

**Version bump policy:**

- `MAJOR` (X.0.0): breaking changes to skill IDs, API contracts, or governance model
- `MINOR` (0.Y.0): new skills, new operational modules, backward-compatible features
- `PATCH` (0.0.Z): bug fixes, CI fixes, documentation corrections

## Governance

This project follows strict governance rules defined in AGENTS.md. Key rules:
- Never modify AGENTS.md, CLAUDE.md, or skills/ without human override
- All content changes require evidence from the knowledge model
- Commit messages for content-touching changes must include Skills invoked: S-XX
