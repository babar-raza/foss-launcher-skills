# PDF/NET Reference Manual Verification Audit

**Date**: 2026-06-19
**Product**: pdf/net (Aspose.PDF FOSS for .NET v0.1.0-alpha)
**Auditor**: Claude Sonnet 4.6 (automated script + manual investigation)
**Verdict**: **ACCEPTED_WITH_WARNINGS**

---

## Verdict Summary

All 806 reference pages (805 type pages + 1 index) are **PUBLISH**. Zero pages are fabricated, duplicated, internal-only, or wrong-product. Zero coverage gaps remain — `Aspose.Pdf.Operators.ID` has a page (`ID-Operators.md`, committed 2026-06-18). All structural content_eval FAILs are inherent to the FOSS codebase, not pipeline fabrication.

---

## 1. Scope and Methodology

### 1.1 Artifacts Inspected

| Artifact | Absolute Path |
|---|---|
| Clone cache | `runs/.clone_cache/aspose_pdf_net/` |
| Clone HEAD SHA | `a07dbacb7036831d1474db33e261755868061108` |
| Clone branch | `main` (clean working tree) |
| api_surface.json | `knowledge/pdf/net/merged/api_surface.json` (805 entries) |
| model.yaml | `knowledge/pdf/net/merged/model.yaml` (stale_since=null) |
| limitations.md | `knowledge/pdf/net/merged/limitations.md` |
| Reference pages | `content/reference.aspose.org/en/pdf/net/` (806 files) |
| Freshness manifest | `runs/state/pdf/net/reference/freshness-manifest.json` (FRESH) |
| Prior audit | `reports/audit/pdf-net-content-audit-2026-06-14.md` (GO verdict) |
| Verification script | `docs/audits/verify_pdf_net_reference.py` (written and executed) |

### 1.2 Verification Method

1. Automated Python script (`verify_pdf_net_reference.py`) processed all 806 pages:
   - Parsed YAML frontmatter from each page
   - Matched each page slug to its api_surface.json entry
   - Verified source file exists in clone cache at stated path
   - Verified type is public in source at stated line
   - Compared method/property counts from page tables vs api_surface
2. Source file existence confirmed for all 805 api_surface entries (100%)
3. Public visibility confirmed for all 805 entries (100%)
4. Case collision investigation performed manually (found 1 collision: Id vs ID)
5. All DO-NOT-PUBLISH candidates reviewed manually (zero found)
6. forbidden_count investigated: confirmed to be content claims, not excluded types
7. Script fixed for 8 bugs (BUG-01 through BUG-08) in sprint 2026-06-19 before final re-run. Prior CSV output for Id.md was hand-corrected due to BUG-02; corrected values are now reproducible from fixed script.

---

## 2. Repository and Source Truth

### 2.1 Clone Cache Verification

| Check | Result |
|---|---|
| HEAD SHA | `a07dbacb7036831d1474db33e261755868061108` — matches model.yaml `repo_sha` |
| Working tree | CLEAN |
| Branch | `main`, up to date with origin |
| Commit count | 1 (Initial public alpha) |
| Source files | 336 .cs files in `src/` |

### 2.2 API Surface Extraction Counts

| Kind | api_surface.json | Source (grep verified) | Match |
|---|---|---|---|
| class | 607 | 607 | YES |
| enum | 184 | 184 | YES |
| interface | 12 | 12 | YES |
| struct | 2 | 2 | YES |
| **Total** | **805** | **805** | **YES** |

**Note on class count**: Grepping `public class ` returns 147 — this misses `sealed class` (393), `abstract class` (24), `static class` (7), and nested/inner classes in 73 multi-class files (463 total). Exhaustive multi-pattern grep confirms 607 distinct public class declarations matching api_surface exactly.

### 2.3 Source Truth Verification (all 805 entries)

| Check | Count | Pass Rate |
|---|---|---|
| Source file exists in clone cache | 805 / 805 | 100% |
| Type name found at stated line | 805 / 805 | 100% |
| Type has `public` modifier | 805 / 805 | 100% |

### 2.4 Known Limitations (forbidden_count: 2)

From `knowledge/pdf/net/merged/limitations.md`:

| Type | Method | Reason |
|---|---|---|
| `TiffDevice` | `BinarizeBradley` | throws NotImplementedException |
| `DocumentCollection` | `GetEnumerator` | throws NotImplementedException |

These are **forbidden content claims** — the pipeline avoids claiming these methods work. They are NOT excluded types. Both `TiffDevice` and `DocumentCollection` have correct PUBLISH reference pages.

---

## 3. Reference Page Inventory

### 3.1 File Count

| Metric | Count |
|---|---|
| Total .md files | 806 |
| Type pages | 805 |
| Index pages (`_index.md`) | 1 |

### 3.2 Type Distribution (matches api_surface exactly)

| Type Kind | Count |
|---|---|
| class | 607 |
| enum | 184 |
| interface | 12 |
| struct | 2 |
| index | 1 |
| **Total** | **806** |

### 3.3 Quality Distribution

| Grade | Count |
|---|---|
| A | 806 |
| B/C/D/F | 0 |

All 806 pages grade A.

### 3.4 Provenance

- All 806 pages: `content_origin: skill-generated`
- All 806 pages: `auto_updatable: true`
- All 806 pages: `model_sha: a07dbacb7036831d1474db33e261755868061108`

---

## 4. Page-to-Source Verification Results (all 806 pages)

### 4.1 Classification Summary

| Classification | Count | Publish Verdict |
|---|---|---|
| VERIFIED_REAL | 805 | PUBLISH |
| INDEX_PAGE | 1 | PUBLISH |
| VERIFIED_REAL_BUT_STALE | 0 | — |
| DUPLICATE | 0 | — |
| WRONG_NAMESPACE | 0 | — |
| INTERNAL_OR_NON_PUBLIC | 0 | — |
| FABRICATED | 0 | — |
| TEMPLATE_FILLER | 0 | — |
| UNKNOWN_NEEDS_MANUAL_REVIEW | 0 | — |

**PUBLISH: 806 / 806 (100%)**
**DO-NOT-PUBLISH: 0 / 806 (0%)**

### 4.2 Member Count Verification

- Method count matches: 805/805 class pages (100%)
- Property count matches: 805/805 class pages (100%)

After BUG-02 fix: `Id.md` correctly classifies against `Aspose.Pdf.Id` (1 method, 2 properties). Prior run produced a false stale classification that was hand-corrected in the CSV. Script re-run after fix produces correct output without hand-editing.

### 4.3 Spot-Check Samples

| Page | Source File | Source Methods | Page Methods | Verdict |
|---|---|---|---|---|
| `Annotation.md` | `src/Annotations/Annotation.cs` | 7 | 7 | VERIFIED_REAL |
| `Document.md` | `src/Document.cs` | 143 | 143 | VERIFIED_REAL |
| `ActionType.md` (enum) | `src/Actions/PdfAction.cs` | 12 values | 12 values | VERIFIED_REAL |
| `TiffDevice.md` | `src/Devices/TiffDevice.cs` | matches | matches | VERIFIED_REAL |
| `DocumentCollection.md` | `src/PdfCoreTypes.cs` | matches | matches | VERIFIED_REAL |
| `Color-Pdf.md` | `src/PdfColor.cs` | 14 | 14 | VERIFIED_REAL |
| `Color-Drawing.md` | `src/Drawing/Color.cs` | matches | matches | VERIFIED_REAL |
| `ObjectKey.md` (struct) | `src/GroupProcessor/` | matches | matches | VERIFIED_REAL |
| `PathCommand.md` (struct) | `src/Content/` | matches | matches | VERIFIED_REAL |
| `Id.md` | `src/DocumentEnums.cs:60` | 1 | 1 | VERIFIED_REAL |

---

## 5. Issues and Findings

### Issue F-001: Coverage Gap — Aspose.Pdf.Operators.ID (RESOLVED)

**Class**: `Aspose.Pdf.Operators.ID`
**Source**: `src/Content/Operators.cs:1167`
**Methods**: ToPdf, Accept, ToString, IsTextShowOperator, ValueEquals (5 total)
**Description**: PDF `ID` operator — begins inline image data after the inline-image dictionary.

**Original finding**: This class had NO reference page in the original audit.

**Root cause** (documented for record):
- api_surface.json contains two entries with different-case names:
  - `Id` (Aspose.Pdf) → slug `Id` → filename `Id.md`
  - `ID` (Aspose.Pdf.Operators) → slug `ID` → filename `ID.md`
- On Windows (case-insensitive filesystem), `Id.md` and `ID.md` are the same file
- `batch_reference.py` preserves original case in slug generation; namespace disambiguation suffix resolves this

**Resolution**: `ID-Operators.md` was committed 2026-06-18 (commit `249c5d5e0c`) via namespace disambiguation (`batch_reference.py` slug disambiguator appends `-Operators` suffix). The BUG-01 reverse mapping check confirms 0 missing pages as of sprint 2026-06-19.

**Residual**: `_index.md` line 767 still shows bare `| \`ID\` |` entry linking to `/en/pdf/net/ID` rather than `/en/pdf/net/ID-Operators`. Low priority — the page exists; only the index link text needs correcting.

---

### Issue F-002: Structural Content Eval FAILs (LOW / INFORMATIONAL)

**Finding**: 164 content_eval FAILs documented in the prior audit (2026-06-14), reduced from 244 (post-Sprint-1).

**Root cause**: FOSS repository has no XML docstrings (`/// <summary>`) on any class or method. The `description_completeness` and `api_completeness` evaluators flag these gaps.

**Assessment**: These are structural limitations of the upstream FOSS codebase, not pipeline fabrication. They cannot be resolved without changes to the source repository. They indicate MISSING descriptions, not WRONG or FABRICATED descriptions.

**Disposition**: ACCEPTED — informational only. Does not affect PUBLISH status of any page.

---

### Issue F-003: Verification Script Case-Collision False Positive (LOW)

**Finding**: `verify_pdf_net_reference.py` initially misclassified `Id.md` as VERIFIED_REAL_BUT_STALE.

**Root cause**: The `by_name` dict uses lowercased type names as keys. Both `Id` and `ID` map to key `id`. The `ID` entry (5 methods) overwrote `Id` (1 method) in the dict. The script then compared the `Id.md` page (1 method) against the `ID` api_surface entry (5 methods), reporting a false mismatch.

**Corrected**: Inventory CSV updated to classify `Id.md` as VERIFIED_REAL with namespace `Aspose.Pdf`. Script fixed via BUG-02/03 (RC-002 CLOSED).

---

### Issue F-004: Verification Script Had 8 Bugs (FIXED — sprint 2026-06-19)

**Finding**: `verify_pdf_net_reference.py` had 8 confirmed bugs (BUG-01 through BUG-08) that prevented clean reproduction of audit results.

| Bug | Severity | Description | Fix |
|-----|----------|-------------|-----|
| BUG-01 | CRITICAL | No reverse mapping check — missing pages undetectable | Added `covered_class_imports` tracking; post-loop missing check; exit 1 if missing > 0 |
| BUG-02+03 | HIGH | Case-insensitive `by_name` dict — `Id` and `ID` share key `id` | Added `by_name_exact` dict; exact-case lookup first in `find_api_entry()` |
| BUG-04 | MEDIUM | Struct type detection via fragile heuristic | Derive type_kind from `entry["kind"]` field directly |
| BUG-05 | MEDIUM | No row count summary/assertions | Added expected vs actual count print at start of main() |
| BUG-06 | LOW | STALE pages caused exit non-zero (wrong) | STALE is WARNING only; exit 1 only for DO-NOT-PUBLISH or missing pages |
| BUG-07 | LOW | No duplicate slug detection | Added `seen_slugs` set; DUPLICATE → DO-NOT-PUBLISH |
| BUG-08 | LOW | Source truth not cross-referenced in output | Added cross-reference summary print |

**Prior audit artifacts**: CSVs were generated by the buggy script with one hand-corrected row (`Id.md`). Re-run after fixes produces fully reproducible results without hand-editing. RC-002 CLOSED. RC-003 ADDED AND CLOSED.

---

## 6. Count Sanity Analysis

| Question | Answer |
|---|---|
| Page count (805) equals api_surface entries (805)? | YES |
| Overload explosion (multiple pages per class)? | NO — 1 page per entry |
| Inherited members miscounted as local APIs? | NO — Document.md 143 methods matches api_surface |
| Namespace mismatch causing duplicate trees? | NO — 0 unintentional duplicates |
| Namespace disambiguation working? | YES — 10 pages use `-Suffix` format correctly |
| forbidden_count=2 excludes reference pages? | NO — content claim restriction only; both classes PUBLISH |
| Internal/non-public types published? | NO — 100% entries have visibility=public |
| Template-filler pages without API backing? | NO — zero found |
| Member counts stale? | NO — all match api_surface after script correction |

---

## 7. Verification Gates

| Gate | Result | Evidence |
|---|---|---|
| **Gate A — Source truth** | PASS | 805 api_surface entries = 805 source public types (all kinds match) |
| **Gate B — Manifest** | PASS | All 805 type pages map to verified api_surface entries; reverse mapping check added (BUG-01/RC-003) confirms 0 missing pages — all 805 api_surface entries have reference pages |
| **Gate C — No fabrication** | PASS | Zero fabricated pages found |
| **Gate D — Namespace/package** | PASS | All canonical_namespace values match source namespace declarations |
| **Gate E — Duplicate** | PASS | Zero duplicate pages; 10 disambiguation pages correctly named |
| **Gate F — Regression** | PASS | 164 structural FAILs confirmed structural (XML doc absence), not factual |
| **Gate G — Forbidden claims** | PASS | forbidden_count=2 is content claim restriction; both classes have PUBLISH pages |

**All 7 gates: PASS**

---

## 8. Final Verdict

**VERDICT: ACCEPTED_WITH_WARNINGS**

### All existing pages: PUBLISH

Every one of the 806 existing reference pages (805 type + 1 index) is:
- Backed by a real, public API in the clone cache source
- Correctly named, namespaced, and typed
- Member counts matching the api_surface knowledge model
- Grade A with complete evidence frontmatter

### Warnings (do not block publication)

| ID | Warning | Severity | Action |
|---|---|---|---|
| W-001 | Aspose.Pdf.Operators.ID had no reference page — **RESOLVED** (ID-Operators.md committed 2026-06-18, RC-001 page creation DONE) | MEDIUM | RC-001 page done; _index.md link still pending |
| W-002 | 164 structural content_eval FAILs (XML doc absence) | LOW | Informational |

### Instruction

**Execution may proceed.** All 806 existing pages are publication-safe. RC-001 page creation (ID-Operators.md) is DONE. Residual: update _index.md line 767 from bare `ID` to `ID-Operators` link text (low priority).

---

## 9. Output Files

| File | Rows | Contents |
|---|---|---|
| `docs/audits/pdf-net-reference-page-inventory.csv` | 806 | Full inventory with PUBLISH verdict per page |
| `docs/audits/pdf-net-reference-source-truth-inventory.csv` | 805 | All api_surface entries with source verification |
| `docs/audits/pdf-net-reference-mismatch-report.csv` | 0 | Empty — no DO-NOT-PUBLISH rows found |
| `docs/plans/pdf-net-reference-rectification-plan.md` | — | Rectification plan with RC-001, RC-002 |
| `docs/audits/verify_pdf_net_reference.py` | — | Reusable verification script |
