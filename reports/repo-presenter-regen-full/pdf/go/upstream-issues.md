# Upstream issues — Aspose.PDF FOSS for Go

Verified: 2026-08-13 against https://github.com/aspose-pdf-foss/aspose-pdf-foss-for-go
(clone-cache HEAD `0fd5a52fc89b8fc745b98c9adc2547bfaed16314`).

No BLOCKING or FUNCTIONAL-DEFECT upstream issues were found. Two informational documentation
inconsistencies in the upstream repository's own `README.md` were found and are recorded below —
neither affects the library's real behavior.

## Stale "Out of Scope" Note in the Digital Signatures Section

- **Severity**: INFORMATIONAL
- **Evidence**: The upstream `README.md`'s Digital Signatures prose closes with "Out of scope for
  now: PAdES/timestamps/LTV, visible signature appearances, certification, and multiple/
  incremental signatures" — directly contradicted by the same file's own `**Digital signatures**`
  Features-list bullet a few paragraphs earlier, which already describes PAdES, a DocMDP
  certification signature, an RFC 3161 trusted timestamp, and multiple/incremental signatures as
  implemented, and by the real, current source at `sign.go` (`SignOptions.PAdES`,
  `SignOptions.Certify`, `SignOptions.TimestampURL`, `SignOptions.Incremental`),
  `pkcs7_timestamp.go`, and `sign_incremental.go`.
- **Impact**: A reader who reaches this closing sentence after the earlier, accurate bullet may
  wrongly conclude these capabilities were removed or never shipped. No functional impact on the
  library — every capability the closing sentence disclaims is real and currently implemented.
- **Not fixable here because**: This candidate is a README-only artifact for this repository's
  own presentation of the product; the fix belongs in the upstream repository's own `README.md`.

## Stale "Out of Scope" Note in the Forms Section

- **Severity**: INFORMATIONAL
- **Evidence**: The upstream `README.md`'s Forms (AcroForm) prose closes with "Out of scope for
  this release: form flattening, and the richer push-button appearance surface (rollover/down
  captions, icon images)" — contradicted by the same file's own `**Flatten**` Features-list
  bullet, and by real, current source: `flatten.go` (`Document.Flatten()`, `Form.Flatten()`,
  `Field.Flatten()`, `Annotation.Flatten()` and `AnnotationCollection.Flatten()`) and
  `form_button.go` (`(*ButtonField).SetAppearance(ButtonAppearance)` with `RolloverText`/
  `DownText`/`IconPath`, baked into `/AP/N`/`/AP/R`/`/AP/D`).
- **Impact**: Same as above — a documentation-only inconsistency confined to the upstream
  `README.md`'s own prose; no functional impact on the library.
- **Not fixable here because**: Same as above — the fix belongs in the upstream repository's own
  `README.md`.
