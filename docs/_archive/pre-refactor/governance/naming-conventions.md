# Archived Document

Archived: 2026-05-30

Reason: Superseded by the docs architecture refactor. This file is retained for history only; do not use it as current operating guidance.

Successor: See docs/README.md for the current documentation map and canonical references.

Original path: docs/_archive/pre-refactor/governance/naming-conventions.md

---

---
# Governance child document — extracted from AGENTS.md
# Source: AGENTS.md §3a, §3b
# Plan: delightful-wondering-hartmanis (TC-03)
# Extracted: 2026-04-28
---

## 3a. Platform Folder Naming

The `{platform}` segment in all content and knowledge paths must use the short name:

| Platform | Folder name | **Never** use |
|----------|-------------|---------------|
| .NET / C# | `net` | `dotnet` |
| Python | `python` | — |
| Java | `java` | — |
| C++ | `cpp` | — |
| TypeScript | `typescript` | `ts` |
| Rust | `rust` | `rs` |

## 3b. `plugin_platform` Display Name (products.aspose.org)

The `plugin_platform` frontmatter field on product pages names the **platform**, not the implementation language. Use exactly these values — never append the primary language (C#, JS, etc.):

| Platform | `plugin_platform` value |
|----------|------------------------|
| .NET     | `.NET`                 |
| Python   | `Python`               |
| Java     | `Java`                 |
| C++      | `C++`                  |
| TypeScript | `TypeScript`         |
| Rust     | `Rust`                 |

**Wrong**: `plugin_platform: .NET (C#)` — "(C#)" belongs in prose, not in this metadata field.

## 3c. Family Root Display Names (reference, docs, kb)

Family-level `_index.md` files (one level below `en/` in reference, docs, and kb sites) must follow these rules:

| Field | Rule | Rationale |
|-------|------|-----------|
| `title` | `{Product} FOSS` | Canonical product name from `metrics_taxonomy.yaml` + " FOSS" suffix |
| `linkTitle` | **Must not exist** | Hugo sidebar prioritizes `linkTitle` over `title`; having it causes sidebar to show bare slug |

The canonical product display name is sourced from `scripts/pipeline/config/metrics_taxonomy.yaml` under the `products:` key. Special cases (3D, PDF, CAD, etc.) are handled by the taxonomy — do not derive from slug capitalization.

**Enforcement**: `scripts/ci/checks/check_family_display_names.py` (CI check), `launch_gate.py` L-11 (launch gate).

---

## 3d. Reference Page Slug Sanitization

Class names are sanitized to filesystem-safe slugs before being used as page filenames.
The sanitization regex replaces all unsafe characters with `_`:

| Character(s) | Example input | Sanitized output |
|-------------|--------------|-----------------|
| `.` (dot) | `Outer.Inner` | `Outer_Inner` |
| `::` (namespace) | `ns::Class` | `ns_Class` |
| `[]` (brackets) | `List[int]` | `List_int_` |
| `/` `\` (path sep) | `path/to/Class` | `path_to_Class` |
| `<>` (angle) | `Generic<T>` | `Generic_T_` |
| `?` `*` `\|` `"` | `Nullable?` | `Nullable_` |

PEP 8 Python names (letters, digits, underscore) pass through unchanged.
Consecutive unsafe characters collapse to a single `_`.

**Implementation**: `_sanitize_slug()` in `batch_reference.py`.
**Enforcement**: `test_slug_sanitization.py` (19 test cases).

---

## Metrics Naming Conventions

| Identifier | Convention |
|------------|-----------|
| `agent_name` | `aspose-org-{component}` (kebab-case, from `metrics_taxonomy.yaml`) |
| `job_type` | snake_case: `knowledge_enrichment`, `gap_evaluation`, `content_translation`, etc. |
| `run_id` | UUID v4 generated per work-slice |
| `call_site_id` | `CS-{NNN}` registered in `metrics_callsite_registry.yaml` |
| `agent_owner` | Always `"Babar Raza"` (from taxonomy) |
| Test rows | `item_name` must start with `[TEST]`, `job_type` must be `"test"` |

See `AGENTS.md §15` for the full metrics obligation.
