# PDF/.NET Reference — Rectification Plan

**Audit source:** `docs/audits/pdf-net-reference-manual-verification.md`
**Date:** 2026-06-18
**Overall verdict:** ACCEPTED_WITH_WARNINGS

Two taskcards require action. The remaining 802 pages are accepted with no changes needed.

---

## TC-AUDIT-001 — Generate Missing `ID-Operators.md` for `Aspose.Pdf.Operators.ID`

- **Objective:** Create a reference page for the `ID` class in `Aspose.Pdf.Operators` namespace, which is missing due to a Windows case-insensitive filesystem collision with `Id.md` (Aspose.Pdf.Id).
- **Files affected:**
  - `content/reference.aspose.org/en/pdf/net/ID-Operators.md` (to be created)
  - `scripts/pipeline/commands/content/batch_reference.py` — investigate case-collision detection
- **Source evidence:**
  - `runs/.clone_cache/aspose_pdf_net/src/Content/Operators.cs:1167` — `public sealed class ID : Operator`
  - api_surface.json entry: class `ID`, namespace `Aspose.Pdf.Operators`, kind `class`
- **Manual fix steps:**
  1. Locate the api_surface.json entry for `ID` (Aspose.Pdf.Operators) — confirm the entry exists with `canonical_namespace: Aspose.Pdf.Operators`
  2. The slug should be `ID-Operators` (applying the `_entry_slug` suffix rule used for all other name-collision pairs)
  3. Run targeted single-page generation via `batch_reference.py` with `--rebuild-all` on a case-sensitive filesystem (Linux/WSL), or manually construct the page from the api_surface entry
  4. Verify the generated file: `content/reference.aspose.org/en/pdf/net/ID-Operators.md`
  5. Run `/content-check` on the new file
  6. Confirm `Id.md` (Aspose.Pdf.Id) is untouched
  7. **Root cause fix (pipeline hardening):** In `_entry_slug()` in `api_surface.py`, add a post-generation collision check that detects case-insensitive slug pairs and forces the disambiguation suffix on both entries regardless of uniqueness at the name level
- **Risks:**
  - Generating on Windows may silently fail again — must use case-sensitive environment or explicitly use `ID-Operators` as slug
  - Over-correcting `Id.md` to `Id-Pdf.md` would rename a live page (avoid; only the missing page needs fixing)
- **Rollback:** `git checkout -- content/reference.aspose.org/en/pdf/net/` (delete the new file only)
- **Verification:**
  - Both `Id.md` and `ID-Operators.md` exist
  - `Id.md` title = `Id`, namespace = `Aspose.Pdf`
  - `ID-Operators.md` title = `ID`, namespace = `Aspose.Pdf.Operators`
  - Content describes the PDF Begin Image Data operator
- **Evidence required:** `evidence.apis: [ID, ID.Id]` (constructor), correct model_sha
- **Status:** COMPLETED_VERIFIED — 2026-06-18. `ID-Operators.md` created at `content/reference.aspose.org/en/pdf/net/ID-Operators.md`, grade A, 0 FAILs/0 WARNs. `Id.md` confirmed untouched.

---

## TC-AUDIT-002 — Add NotImplementedException Disclaimer to Forbidden Methods

- **Objective:** Prevent users from calling `TiffDevice.BinarizeBradley` and `DocumentCollection.GetEnumerator` under the false impression they are implemented. Both throw `NotImplementedException` at runtime.
- **Files affected:**
  - `content/reference.aspose.org/en/pdf/net/TiffDevice.md`
  - `content/reference.aspose.org/en/pdf/net/DocumentCollection.md`
- **Source evidence:**
  - `src/Devices/TiffDevice.cs:176` — `throw new NotImplementedException(`
  - `src/PdfCoreTypes.cs:12` — `public IEnumerator GetEnumerator() => throw new NotImplementedException();`
  - `knowledge/pdf/net/merged/limitations.md` — both entries recorded
- **Manual fix steps:**
  1. Activate S-73 (manual-edit) for `TiffDevice.md`
  2. In the Methods table row for `BinarizeBradley`, update the description cell to: `Not implemented in this version. Throws NotImplementedException.`
  3. Deactivate S-73 scope; activate for `DocumentCollection.md`
  4. In the Methods table row for `GetEnumerator`, update the description cell to: `Not implemented in this version. Throws NotImplementedException.`
  5. Run `/content-check` on both files
  6. Verify grade does not drop below C (content change is factually accurate and improves honesty)
- **Risks:**
  - Minor grade impact possible (evaluator may flag the disclaimer text as unusual for a method description)
  - If `batch_reference.py` regenerates these pages in future, the disclaimer will be overwritten — also fix the `limitations.md` → page generation pipeline to inject disclaimers automatically
- **Rollback:** `git checkout -- content/reference.aspose.org/en/pdf/net/TiffDevice.md content/reference.aspose.org/en/pdf/net/DocumentCollection.md`
- **Verification:**
  - `TiffDevice.md` method row for `BinarizeBradley` contains "NotImplementedException"
  - `DocumentCollection.md` method row for `GetEnumerator` contains "NotImplementedException"
  - Both pages pass `/content-check` (no new FAIL findings)
- **Evidence required:** No change to evidence frontmatter needed (fact correction, not new API claim)
- **Status:** COMPLETED_VERIFIED — 2026-06-18. Both method rows updated with "Not implemented in this version — throws NotImplementedException at runtime." Audit: 0 FAILs, 0 WARNs.

---

## No Further Rectification Required

All other 802 pages in `content/reference.aspose.org/en/pdf/net/` are:
- Truthful: content matches clone source
- Complete: no missing members beyond the forbidden-claims case
- Non-duplicate: all disambiguated pairs are genuinely distinct classes
- Current: all pages carry `model_sha: a07dbacb7036831d1474db33e261755868061108` (2026-06-17 promotion)
- Structurally valid: all have correct layout, category, and `auto_updatable: true`

The 10 grade C pages (AnnotationSelector, BmpDevice, BorderInfo, CertificateEncryptionOptions, HtmlSaveOptions, IOperatorSelector, PdfViewer, SoundSampleData, TextEditOptions, TextState) are low-quality due to sparse upstream XML documentation. This is a knowledge-gap issue, not a page error. Remediation via `/page-enhance` is optional and deferred.
