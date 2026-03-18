---
name: path-guard
id: S-01
description: >
  Validate that a file path is an allowed write target before any content
  modification. Prevents accidental writes to protected files and directories.
args: "{file-path}"
---

# S-01: Path Guard — Enforce Allowed Write Paths

**Arguments**: $ARGUMENTS
Expected format: `{file-path}`

## Purpose
Validate that a file path is an allowed write target before any content modification. Prevents accidental writes to protected files and directories.

> **Configuration**: The allowed and forbidden path lists below are defaults for the aspose.org repo. See `config.yaml` in foss-launcher-skills for your project's path configuration.

## Forbidden paths (NEVER writable)
- `themes/` — Hugo theme files
- `layouts/` — Hugo layout templates
- `configs/` — Hugo configuration files
- `AGENTS.md` — Governance file
- `CLAUDE.md` — Agent instructions (Claude Code)
- `CODEX.md` — Agent instructions (Codex)
- `.claude/` — Claude Code config
- `.agents/` — Codex config
- `.kilocode/` — Kilo Code config
- `skills/` — Canonical skill source
- `scripts/` — Extraction scripts (except by explicit human override)
- `knowledge/*/scout/` — Scout output (only written by S-34)
- `knowledge/*/external/` — External knowledge import (only written by S-30)

## Allowed paths
- `content/docs.aspose.org/en/{family}/{platform}/**` — Docs pages
- `content/blog.aspose.org/{family}/{platform}/**` — Blog posts
- `content/kb.aspose.org/en/{family}/{platform}/**` — KB articles
- `content/products.aspose.org/en/{family}/**` — Product pages
- `content/reference.aspose.org/en/{family}/{platform}/**` — API reference
- `knowledge/{family}/{platform}/merged/**` — Merged knowledge (only by S-35)
- `reports/**` — Audit reports

## Steps

1. **Normalize path**: Convert to forward slashes, make relative to repo root
2. **Check forbidden list**: If path matches any forbidden pattern, DENY with explanation
3. **Check allowed list**: If path matches an allowed pattern, ALLOW
4. **Default**: DENY with message "Path not in allowed write list"

## Output
- `ALLOW: {path}` or `DENY: {path} — {reason}`
