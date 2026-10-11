# Upstream issues — Aspose.Slides FOSS for Python

Verified: 2026-08-13 against https://github.com/aspose-slides-foss/Aspose.Slides-FOSS-for-Python
(clone cache pinned at commit `6ca17fd6593e0f31ed5e6fb53eb4c5896b7a6525`, v26.4.0)

## SaveFormat enum declares formats with no registered exporter

- **Severity**: INFORMATIONAL
- **Evidence**: `aspose/slides_foss/export/SaveFormat.py` declares 21 values (`Ppt`, `Pdf`,
  `Xps`, `Pptx`, `Ppsx`, `Tiff`, `Odp`, `Pptm`, `Ppsm`, `Potx`, `Potm`, `Html`, `Swf`, `Otp`,
  `Pps`, `Pot`, `Fodp`, `Gif`, `Html5`, `Md`, `Xml`), but `_internal/export/exporter_registry.py`
  only ever calls `ExporterRegistry.register(PptxExporter)`, and
  `PptxExporter.get_supported_formats()` returns exactly six values (`Pptx`, `Pptm`, `Ppsx`,
  `Ppsm`, `Potx`, `Potm`). Calling `Presentation.save(path, SaveFormat.PDF)` (or any of the other
  15 declared-but-unregistered values, including `SaveFormat.MD` — despite its docstring "Save
  presentation in Markdown format") raises `ValueError: Export format 'Pdf' is not supported` at
  runtime — nothing in the enum's own definition signals that those values aren't usable.
- **Impact**: a developer discovering `SaveFormat` through autocomplete would reasonably expect
  `SaveFormat.PDF` / `SaveFormat.HTML` / etc. to work, since the enum gives no static indication
  that most of its own members are unimplemented.
- **Not fixable here because**: this is the real, current shape of the upstream package's own
  export registry, not a README wording issue. This candidate's Scope and Limitations section
  discloses exactly which `SaveFormat` values have a registered exporter.

## Previous README's transition-type count ("60+") overstates the real enum size

- **Severity**: INFORMATIONAL
- **Evidence**: the previous README's Features section claimed "60+ transition types."
  `aspose/slides_foss/slideshow/TransitionType.py` defines exactly 57 members (verified by direct
  count), one of which (`NONE`) is not itself a transition effect.
- **Impact**: minor — a reader relying on "60+" would over-estimate the real transition catalog
  by a handful of types.
- **Not fixable here because**: this was the previous README's own claim, not this candidate's.
  This candidate states the verified count (57) directly instead of carrying the inflated figure
  forward.

No blocking defects were found. Every API identifier, save-format value, and code path referenced
in this candidate resolves to real, on-disk source in the pinned clone cache.

Note: an earlier draft of this file incorrectly flagged the previous README's "Color schemes,
font schemes, format schemes, master/override themes" Themes bullet as an overclaim, based on an
incomplete check of `aspose/slides_foss/theme/FormatScheme.py` alone. A full directory listing of
`theme/` (done during the Step 4 blind comparison against the existing shipped candidate) found
real, fully-functional `ColorScheme.py` (dark1/light1/dark2/light2/accent1-6/hyperlink/
followed_hyperlink color slots) and `FontScheme.py` (major/minor font collections) classes, both
reachable via `Theme.color_scheme` / `Theme.font_scheme` (`Theme` itself reached via
`Presentation.master_theme`). The original claim was accurate; this candidate's Key Capabilities
section and Detailed Member Reference have been corrected to restore it.
