# Naming Conventions — foss-launcher Governance

**Source**: Adapted from aspose.org `docs/governance/naming-conventions.md`
**Adapted**: 2026-05-15 (PAR-013 GV-004)

---

## Platform Folder Naming

The `{platform}` segment in all content and knowledge paths must use the short name:

| Platform | Folder name | **Never** use |
|----------|-------------|---------------|
| .NET / C# | `net` | `dotnet` |
| Python | `python` | — |
| Java | `java` | — |
| C++ | `cpp` | — |
| TypeScript | `typescript` | `ts` |

## Product Page Display Names

The `plugin_platform` frontmatter field on product pages names the **platform**, not the
implementation language. Use exactly these values:

| Platform | `plugin_platform` value |
|----------|------------------------|
| .NET | `.NET` |
| Python | `Python` |
| Java | `Java` |
| C++ | `C++` |
| TypeScript | `TypeScript` |

**Wrong**: `plugin_platform: .NET (C#)` — "(C#)" belongs in prose, not in this metadata field.

## Family Root Display Names

Family-level `_index.md` files must follow:

| Field | Rule |
|-------|------|
| `title` | `{Product} FOSS` — canonical product name + " FOSS" suffix |
| `linkTitle` | **Must not exist** — causes sidebar to show bare slug |

## Reference Page Slug Sanitization

Class names are sanitized to filesystem-safe slugs:

| Character(s) | Example input | Sanitized output |
|-------------|--------------|-----------------|
| `.` (dot) | `Outer.Inner` | `Outer_Inner` |
| `::` (namespace) | `ns::Class` | `ns_Class` |
| `[]` (brackets) | `List[int]` | `List_int_` |
| `/` `\` (path sep) | `path/to/Class` | `path_to_Class` |
| `<>` (angle) | `Generic<T>` | `Generic_T_` |

PEP 8 Python names (letters, digits, underscore) pass through unchanged.
Consecutive unsafe characters collapse to a single `_`.

**Implementation**: `_sanitize_slug()` in `batch_reference.py`.

## Skill and Script Naming

| Artifact | Convention | Example |
|----------|-----------|---------|
| Skill slug | `kebab-case` | `gap-eval`, `page-draft` |
| Skill ID | `S-NN` (registry order) | `S-23`, `S-62` |
| Script name | `snake_case.py` | `audit.py`, `remediate.py` |
| Test file | `test_{module_name}.py` | `test_audit.py` |
| Gap escalation report | `{YYYY-MM-DD}-{task-slug}.md` | `2026-05-15-missing-gap-eval.md` |
| Skill breakage report | `{YYYY-MM-DD}-{skill-id}.md` | `2026-05-15-S-62.md` |
