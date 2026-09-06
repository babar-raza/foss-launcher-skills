# Upstream issues — Aspose.Words FOSS for Python

Verified: 2026-08-16 (this pass, MT052) against `runs/.clone_cache/aspose_words_python` -- `LICENSE`
(repo root) confirmed via `git ls-files` as the sole license path git tracks; a same-content,
lowercase `license` file also exists on disk but is not git-tracked, so it is never cited as
evidence. Originally verified 2026-08-13 against repo_sha `d051a96a7417149e816a8f862d45a5b769bc5fad`,
https://github.com/aspose-words-foss/Aspose.Words-FOSS-for-Python.

## Old README's LICENSE link is broken
- **Severity**: MINOR
- **Evidence**: the repo's own root `README.md` links the license as `[LICENSE](License/license.txt)`. The real, git-tracked license file is at `LICENSE` (repo root) — a different directory (none) and a different filename (`LICENSE`, not `license.txt`) than the old README's own link target. No `License/` directory and no `license.txt` file exist anywhere in the repo.
- **Impact**: a reader clicking the old README's LICENSE link on GitHub gets a 404. The new candidate links `LICENSE` (the real, git-tracked, root-level path) in both the badge row and the License section. (Correction, this pass: an earlier version of this finding and of the candidate itself cited `license/LICENSE` as the real path; re-verified live via `git ls-files` and found wrong -- corrected to the real root-level `LICENSE` path everywhere in the candidate and its disposition files.)
- **Not fixable here because**: the broken link lives in the upstream repo's own `README.md`, which this candidate replaces — the fix ships as part of this candidate rather than as a separate upstream patch.

## `SaveFormat.DOC` is defined but not a usable save target
- **Severity**: MINOR
- **Evidence**: `aspose/words_foss/document.py`'s `SaveFormat` class defines `DOC = "doc"` alongside `MARKDOWN`, `DOCX`, `TEXT`, and `PDF`. `Document.save()`'s own dispatch chain only branches on `MARKDOWN`, `TEXT`, `PDF`, and `DOCX` (each checked against both the enum constant and the output-path suffix); there is no `DOC`/`.doc` branch. Any other value falls through to the final `else`, which raises `ValueError` with the message `Unsupported save format: ... Supported formats: Markdown, Text, PDF, DOCX.` — a message that itself confirms `DOC` was deliberately left out of the writer, not merely unhandled by omission.
- **Impact**: a caller who sees `SaveFormat.DOC` exported from the top-level `aspose.words_foss` namespace and reasonably assumes it works with `save()` (the same way `SaveFormat.MARKDOWN`/`PDF`/`DOCX`/`TEXT` do) will hit a runtime `ValueError` instead. `.doc` files can be *read* (via `DocFileReader`) but never *written* by this edition.
- **Not fixable here because**: whether to implement a DOC writer, or instead drop the unusable `DOC` constant from the public `SaveFormat` class, is an upstream API-design decision. The new candidate documents the real, current behavior in its Scope and Limitations section instead of presenting `SaveFormat.DOC` as a working save target.

## `MarkdownSaveOptions.image_resolution` is dead code — assigned but never consumed anywhere
- **Severity**: INFORMATIONAL
- **Evidence**: `MarkdownSaveOptions` (`aspose/words_foss/saving.py`) declares 13 real properties.
  `Document._save_as_markdown` (`aspose/words_foss/document.py`) is the sole real consumer of a
  `MarkdownSaveOptions` instance, and it copies 11 of the 13 properties into the internal
  `ConversionOptions` object (or, for `encoding`, uses it directly) that `LdmMarkdownWriter`
  reads. `image_resolution` is never read anywhere outside its own `__init__` assignment —
  confirmed by a full-repository grep finding exactly one reference to the attribute (the
  assignment itself) and zero reads. `save_format` is likewise never consumed by the writer (it
  functions only as an identity tag for dispatch, not a behavior toggle read by the writer
  itself), though that one is more clearly self-explanatory from its own name/role than
  `image_resolution` is.
- **Impact**: a caller who sets `MarkdownSaveOptions(image_resolution=...)` expecting it to affect
  embedded/exported image quality or sizing during Markdown export gets no error and no effect —
  the value is silently accepted and silently ignored. This is structurally identical to the
  already-documented case of `PdfSaveOptions`'s 8 unused properties (`text_compression`,
  `embed_full_fonts`, `use_core_fonts`, `font_embedding_mode`, `page_mode`, `color_mode`,
  `preserve_form_fields`, `memory_optimization`, each confirmed via the same grep methodology to
  have zero references outside their own definition) — the same class of defect recurring in a
  second save-options class for this product.
- **Not fixable here because**: this is real, current behavior in the library's own source
  (`MarkdownSaveOptions`'s definition vs. `Document._save_as_markdown`'s actual field usage); no
  README wording can make the writer start reading a field it currently ignores. This candidate's
  own Scope and Limitations section did not carry a blanket "all properties are consumed" claim
  for `MarkdownSaveOptions` (avoiding the false claim the previously-shipped candidate made), but
  had not yet positively disclosed this specific dead-property finding until this verification
  pass — now recorded here for completeness, matching the level of detail already given for the
  analogous `PdfSaveOptions` case.
