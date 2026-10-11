# TC-MT070-06: Targeted cross-surface semantic spot-check

**Scope**: every imaging/net page across products.aspose.org (2 files),
docs.aspose.org (8 files), kb.aspose.org (3 files), and the English blog post (1
file) — 14 files total. reference.aspose.org already covered independently by
TC-MT070-01. Method: read every page's prose and code blocks, cross-checked against
`runs/.clone_cache/aspose_imaging_net/README.md`, every `Formats/*.cs` handler
source file, `ImageProbe.cs`/`ImageInfo.cs`/`ImageFormat.cs`, and
`data/package_registry.json`.

**Result: CLEAN — 0 findings across 14 files.**

Verified in depth, including unusually granular per-format implementation claims
checked against actual handler source (not just the README's summary table): PNG's
hardcoded `FrameCount=1` (`PngFormatHandler.cs:33`), ICO's 0-byte-means-256px
dimension mapping (`IcoFormatHandler.cs:31-32`), TIFF's bounded IFD-chain walk,
WMF's placeable-vs-non-placeable dimension handling and 96 DPI conversion, EMF's
`rclBounds`-derived dimensions, DICOM's transfer-syntax/undefined-length-sequence
handling, and BMP's negative-height normalization. All matched exactly.

Cross-cutting checks, all clean:
- No commercial-capability leakage (no "convert"/"edit"/"resize"/"transform"/
  "render"/"manipulate"/"write" applied to image content anywhere); every page that
  could invite confusion correctly redirects decode/edit/convert needs to the
  commercial Aspose.Imaging SDK.
- No fabricated formats or API members — every code block uses only the 5 real
  `ImageProbe` methods and 5 real `ImageInfo` properties.
- Format list is exactly the real 11 everywhere, no fabrications (no SVG/HEIC/AVIF).
- Install/publication: all pages use the shared `package-install` shortcode rather
  than hand-written prose; verified against `data/package_registry.json`
  (`imaging/net`: `registry_type: nuget`, `verification.published: false`) — the
  shortcode's documented behavior for an unpublished package renders a
  GitHub-source install command, never a publication-status disclosure, correctly
  implementing the no-publication-disclosure policy (ST-054/TC-13,
  [[feedback_readme_no_publication_disclosure]]).
- License (MIT) and zero-NuGet-dependency claims correct everywhere.

**One open, non-blocking item carried forward (not a finding)**: `faq.md`,
`how-to-work-with-imaging-core-api-dotnet.md`, and the blog post each carry a
pre-existing `prose_truth` WARN flag in `reports/grade_manifest.json` (2, 1, and 1
occurrences respectively) that did not block grade A. The underlying flagged-sentence
text could not be recovered from any artifact in the repo
(`reports/audit/imaging-net-truth-20260912.json` has zero recorded findings for these
files). Independent manual line-by-line comparison against source found no factual
errors in any of the three files. Recorded for the paper trail per this mission's own
evidence-completeness standard, not escalated further — not imaging/net-specific, not
blocking, and out of this mission's scope (would require reconstructing which
`content_eval` run produced the flag, a different investigation).

**Skill context**: none required (read-only investigation, no content edits made).
