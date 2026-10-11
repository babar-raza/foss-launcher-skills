# PDF/NET Reference Rectification Plan

**Audit source**: `docs/audits/pdf-net-reference-manual-verification.md`
**Date**: 2026-06-19
**Overall verdict**: ACCEPTED_WITH_WARNINGS
**Immediate action**: Proceed — all 806 existing pages are publication-safe

---

## Acceptance Summary

All 806 pdf/net reference pages have been individually verified against the cloned source repository (commit `a07dbacb7036831d1474db33e261755868061108`). Every page maps to a real, public API. Zero fabricated, duplicate, or internal-only pages found. All 7 verification gates pass.

No pages should be removed or unpublished. The two taskcards below are improvements, not blockers.

---

## Taskcards

---

### RC-001: Add Reference Page for Aspose.Pdf.Operators.ID

**ID**: RC-001
**Title**: Generate missing reference page for Aspose.Pdf.Operators.ID
**Priority**: MEDIUM
**Status**: DONE — page committed 2026-06-18 (commit `249c5d5e0c`); residual: update _index.md link text

**Objective**:
Create a reference page for the `Aspose.Pdf.Operators.ID` class (PDF "ID" operator — begins inline image data). This class exists in the source (`src/Content/Operators.cs:1167`) with 5 public methods (ToPdf, Accept, ToString, IsTextShowOperator, ValueEquals) but has no reference page because its slug `ID.md` collides with `Id.md` (`Aspose.Pdf.Id`) on Windows filesystem.

**Root cause**:
`batch_reference.py` preserves original case in slug generation. On Windows (case-insensitive FS), `Id.md` and `ID.md` are the same file. Only `Id.md` survived in git. No case-collision detection exists in the pipeline.

**Files likely affected**:
- `scripts/pipeline/commands/content/batch_reference.py` — add case-collision detection
- `content/reference.aspose.org/en/pdf/net/ID-Operators.md` — new page (or `Id-Pdf.md` + `ID-Operators.md` disambiguation)
- `content/reference.aspose.org/en/pdf/net/_index.md` — update Operators section link

**Implementation approach**:

Step 1 — Detect case collisions in `batch_reference.py`:
```python
# In _generate_pages() or equivalent, after building the slug list:
# Build a map of lower(slug) -> [entries]
# For any group where lower(slug) has multiple entries (even if same slug length but different case):
#   Apply _slug_suffix disambiguation using namespace segment
```

Step 2 — Disambiguate the collision:
- Current: `Id.md` (Aspose.Pdf.Id) and `ID.md` (Aspose.Pdf.Operators.ID) collide
- New: `Id-Pdf.md` (Aspose.Pdf.Id) and `ID-Operators.md` (Aspose.Pdf.Operators.ID)
- OR only rename the conflicting one: `ID-Operators.md` leaving `Id.md` unchanged
- Update `_index.md` to use the new slugs

Step 3 — Run `batch_reference.py pdf net` to regenerate both pages

Step 4 — Verify both pages exist as separate git-tracked files

**Risks**:
- Renaming `Id.md` to `Id-Pdf.md` would break any existing bookmarks or links to `/en/pdf/net/Id`
- Safer approach: keep `Id.md` as-is, add only `ID-Operators.md` as the new disambiguated page
- If the existing `Id` entry in `_index.md` already links correctly, no change needed there

**Rollback plan**:
Delete `ID-Operators.md`; revert any `_index.md` changes; revert any `batch_reference.py` changes.

**Verification commands**:
```bash
# After generation, confirm both slugs exist as separate files:
git ls-files content/reference.aspose.org/en/pdf/net/Id.md
git ls-files content/reference.aspose.org/en/pdf/net/ID-Operators.md

# Verify ID-Operators.md content:
head -10 content/reference.aspose.org/en/pdf/net/ID-Operators.md
# Should show: title: ID, namespace: Aspose.Pdf.Operators, 5 methods

# Run content-eval:
PYTHONPATH=scripts/pipeline .venv/Scripts/python -m content_eval evaluate pdf net --files content/reference.aspose.org/en/pdf/net/ID-Operators.md
```

**Evidence required for closeout**:
- `git ls-files` shows `ID-Operators.md` as a tracked file
- `ID-Operators.md` frontmatter shows correct namespace (Aspose.Pdf.Operators), 5 methods
- `_index.md` Operators section links to `ID-Operators.md` (or `ID-Operators`)
- content-eval passes on the new page

---

### RC-002: Harden verify_pdf_net_reference.py for Case-Sensitive Name Matching

**ID**: RC-002
**Title**: Fix case-insensitive key collision in verification script
**Priority**: LOW
**Status**: DONE — implemented 2026-06-19

**Objective**:
Fix `docs/audits/verify_pdf_net_reference.py` so it correctly matches pages to api_surface entries when two entries share the same lowercased name (e.g., `Id` and `ID`).

**Root cause**:
The `by_name` dict uses `name.lower()` as key. Both `Id` and `ID` map to key `id`. The second entry's data overwrites the first. When looking up the `Id.md` page, the script finds the `ID` entry (5 methods) instead of the `Id` entry (1 method).

**Implementation approach**:

```python
# In load_api_surface(), change:
#   by_name.setdefault(nm, []).append(e)  # where nm = name.lower()
# To use the ORIGINAL name (case-preserved) as additional key:
by_name_exact = {}   # exact case match: {original_name -> [entry]}
by_name_lower = {}   # case-insensitive: {name.lower() -> [entry]}
for e in entries:
    nm_orig = e.get("name") or ""
    nm_lower = nm_orig.lower()
    by_name_exact.setdefault(nm_orig, []).append(e)
    by_name_lower.setdefault(nm_lower, []).append(e)

# In find_api_entry(), try exact case match first:
candidates = by_name_exact.get(slug, [])   # exact match (e.g. "Id" only finds Id)
if not candidates:
    candidates = by_name_lower.get(slug.lower(), [])  # fallback case-insensitive
```

**Files affected**:
- `docs/audits/verify_pdf_net_reference.py`

**Risks**: None — this is a diagnostic script, not production code.

**Verification**: Re-run script against pdf/net; confirm `Id.md` is classified as VERIFIED_REAL with `Aspose.Pdf` namespace (not Aspose.Pdf.Operators). Confirmed as of sprint 2026-06-19: `Id.md` → VERIFIED_REAL, namespace=Aspose.Pdf.

---

### RC-003: Add Reverse Mapping Check to Verification Script

**ID**: RC-003
**Title**: Detect api_surface entries with no reference page
**Priority**: HIGH
**Status**: DONE — implemented 2026-06-19

**Objective**: The verification script only checked that pages have api_surface entries. It did not check that all api_surface entries have pages. This allowed the Aspose.Pdf.Operators.ID missing page to go undetected in the original audit.

**Implementation**: BUG-01 fix in `verify_pdf_net_reference.py`:
- `covered_class_imports: set[str]` tracking during page loop (keyed by `class_import`, lowercased)
- Post-loop missing-page check comparing all api_surface entries against covered set
- Exit non-zero if missing > 0

**Evidence**: Script re-run (2026-06-19) shows 0 MISSING pages — all 805 api_surface entries have reference pages including `Aspose.Pdf.Operators.ID` (covered by `ID-Operators.md`). Script exits 0.

**Verification**: After any future api_surface update, re-run `verify_pdf_net_reference.py`. Script must exit 0. If exit 1, inspect MISSING PAGE lines in stdout.

---

## Gates Summary

| Gate | Result |
|---|---|
| Gate A — Source truth | PASS |
| Gate B — Manifest | PASS |
| Gate C — No fabrication | PASS |
| Gate D — Namespace/package | PASS |
| Gate E — Duplicate | PASS |
| Gate F — Regression | PASS |
| Gate G — Forbidden claims | PASS |

---

## Next Steps

1. **Proceed with publication** — all 806 existing pages are safe to publish
2. **RC-001** (DONE): `ID-Operators.md` committed 2026-06-18. Residual: update `_index.md` line 767 link text from bare `ID` to `ID-Operators`
3. **RC-002** (DONE): Script hardened for case-sensitive name matching — 2026-06-19
4. **RC-003** (DONE): Reverse mapping check added — 0 missing pages confirmed — 2026-06-19
5. **Monitor**: On any future api_surface update, re-run `verify_pdf_net_reference.py` — must exit 0
