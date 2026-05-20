<!-- Adapted from aspose.org docs/workflows/ for standalone use -->

# Mental Model Refresh Protocol

Before editing any content page for family/platform X:

1. Read `knowledge/{family}/{platform}/merged/model.yaml`
2. If `stale_since` is not null -> the knowledge model is outdated; do not edit content until
   a knowledge-diff and knowledge-update have been run
3. Read `claims.json` and `api_surface.md` in `knowledge/{family}/{platform}/merged/`
4. Only then proceed to content tasks
5. If resuming a plan last modified >7 days ago, or any plan with archive/postmortem/sprint sections -> run `/plan-normalize {plan-file}` before executing it

## Platform Folder Naming

The `{platform}` segment in all content and knowledge paths must use the short name:

| Platform | Folder name | **Never** use |
|----------|-------------|---------------|
| .NET / C# | `net` | `dotnet` |
| Python | `python` | -- |
| Java | `java` | -- |
| C++ | `cpp` | -- |
| TypeScript | `typescript` | `ts` |

## `plugin_platform` Display Name (product pages)

The `plugin_platform` frontmatter field on product pages names the **platform**, not the implementation language. Use exactly these values -- never append the primary language (C#, JS, etc.):

| Platform | `plugin_platform` value |
|----------|------------------------|
| .NET     | `.NET`                 |
| Python   | `Python`               |
| Java     | `Java`                 |
| C++      | `C++`                  |
| TypeScript | `TypeScript`         |

**Wrong**: `plugin_platform: .NET (C#)` -- "(C#)" belongs in prose, not in this metadata field.
