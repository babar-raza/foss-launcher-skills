# maintenance/ — One-Off Migration and Recovery Scripts

This directory holds scripts that are run **manually by a human operator** for a specific task (data migration, schema upgrade, disaster recovery). They are **not** called by CI, git hooks, or skill workflows.

## Lifecycle policy

A script belongs here if:
- It performs a one-time or occasional task (not part of the regular pipeline)
- It is **not** referenced by `.github/workflows/`, git hooks, AGENTS.md, or any skill file
- It is idempotent where possible (safe to run more than once)
- It targets a specific historical migration or recovery scenario

A script does **not** belong here if:
- It needs to run on every PR or commit → put it in `scripts/ci/`
- It is invoked by a skill or operator workflow → put it in `scripts/pipeline/`
- It is a general utility used by other scripts → put it in `scripts/pipeline/core/`

## Scripts

| Script | Purpose | Status |
|--------|---------|--------|
| `migrate_model_yaml.py` | Add `repo_url` and `stale_since: null` to all `knowledge/*/merged/model.yaml` files. Idempotent; does not overwrite existing `repo_url`. | Run when: upgrading knowledge schema |
| `rebuild_snippet_index.py` | Reconstruct `snippets_index.json` from orphaned snippet files in `scout/snippets/` when a scout run crashed before writing the index. | Run when: `merge.py` fails due to missing index |
| `generate_reference_pages.py` | Generate missing API reference pages for `slides/java`, `slides/net`, `slides/cpp`. Does not overwrite existing files. Hardcoded platform configs — review before use on new platforms. | Run when: bootstrapping reference pages for slides family |
| `migrate_homepage_platforms.py` | Migrate all `_index.*.md` homepage translation files to use dynamic platform suffixes. Strips hardcoded "Available for..." sentences and adds `platform_suffix`/`platform_conjunction`/`platform_pair` i18n fields. | One-time migration; verify output before committing |

## How to run

Always activate the virtual environment first:

```bash
# Windows
.venv/Scripts/python scripts/maintenance/<script>.py

# Unix/macOS
.venv/bin/python scripts/maintenance/<script>.py
```

Review each script's docstring for required arguments and any pre-conditions before running.
