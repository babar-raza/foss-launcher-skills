---
# Governance child document — extracted from AGENTS.md
# Source: AGENTS.md §3, §3a, §3b
# Plan: delightful-wondering-hartmanis (TC-04)
# Extracted: 2026-04-28
---

# Mental Model Refresh Protocol

Before editing any content page for family/platform X:

1. Read `knowledge/{family}/{platform}/merged/model.yaml`
2. If `stale_since` is not null → the knowledge model is outdated; do not edit content until
   a knowledge-diff (S-12) and knowledge-update (S-14) have been run
3. Read `claims.json` and `api_surface.md` in `knowledge/{family}/{platform}/merged/`
4. Only then proceed to content tasks
5. If resuming a plan last modified >7 days ago, or any plan with archive/postmortem/sprint sections → run `/plan-normalize {plan-file}` (S-91) before executing it

## Platform Folder Naming

The `{platform}` segment in all content and knowledge paths must use the short name:

| Platform | Folder name | **Never** use |
|----------|-------------|---------------|
| .NET / C# | `net` | `dotnet` |
| Python | `python` | — |
| Java | `java` | — |
| C++ | `cpp` | — |
| TypeScript | `typescript` | `ts` |

## `plugin_platform` Display Name (products.aspose.org)

The `plugin_platform` frontmatter field on product pages names the **platform**, not the implementation language. Use exactly these values — never append the primary language (C#, JS, etc.):

| Platform | `plugin_platform` value |
|----------|------------------------|
| .NET     | `.NET`                 |
| Python   | `Python`               |
| Java     | `Java`                 |
| C++      | `C++`                  |
| TypeScript | `TypeScript`         |

**Wrong**: `plugin_platform: .NET (C#)` — "(C#)" belongs in prose, not in this metadata field.
