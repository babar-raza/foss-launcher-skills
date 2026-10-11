# Upstream issues — Aspose.Note FOSS for Python

Verified: 2026-08-13, re-verified 2026-08-15 against
https://github.com/aspose-note-foss/Aspose.Note-FOSS-for-Python (repo_sha
`6d97a522a9ed24708687911f1aabb76e2dea2da7` — clone cache confirmed current against
`origin/main` on 2026-08-15, no new commits). No install/build-blocking issue was found —
`pip install -e ".[pdf,test-pdf]"` installs cleanly from declared, real PyPI dependencies
(`reportlab`, `pypdf`, `Pillow`, `PyMuPDF`), and every command in `.github/workflows/ci.yml`
matches real, present test modules.

## `Document.FileFormat` always reports `OneNote2010`, regardless of the real source format
- **Severity**: FUNCTIONAL-DEFECT
- **Evidence**: `src/aspose/note/model.py`'s `Document.FileFormat` property is `return
  FileFormat.OneNote2010` unconditionally — it never inspects the parsed `OneStoreFile`/
  `LoadedOneNoteDocument` to determine whether the source was actually a OneNote 2007, 2010, or
  Online file, even though the `FileFormat` enum itself declares all three values
  (`OneNote2007`, `OneNote2010`, `OneNoteOnline`).
- **Impact**: code that branches on `Document.FileFormat` to distinguish real OneNote format
  variants always sees `OneNote2010`, regardless of the file's actual format. Content extraction
  itself (pages, rich text, images, tables, tags) is unaffected — only this one property's
  value.
- **Not fixable here because**: this is upstream source behavior, not a documentation defect.
  The README's Scope and Limitations section discloses this plainly instead.

## `License.SetLicense()` and `Metered.SetMeteredKey()` are silent no-ops in this edition, undisclosed by their own docstrings
- **Severity**: INFORMATIONAL — almost certainly intentional (this is the FOSS/community edition,
  which needs no license), but recorded because a caller has no way to learn this from the
  methods themselves.
- **Evidence**: `License.SetLicense(license_path_or_stream)` and
  `Metered.SetMeteredKey(public_key, private_key)` (`src/aspose/note/`) both accept real
  arguments, validate nothing, and unconditionally `return None` with no side effect — confirmed
  by reading both method bodies in full. Neither method's own docstring states that it is a no-op
  or explains why; both read as if they perform real license/metered-key registration, matching
  the equivalent, functional methods on the commercial (non-FOSS) product line.
- **Impact**: a caller migrating code from the commercial edition, or someone who copies a
  licensing snippet from Aspose's general documentation without knowing this is the FOSS build,
  would reasonably believe calling `SetLicense()` is doing something — it silently does nothing.
  No error, no warning. In practice this is harmless (no license is actually required to use this
  library), but the silence itself is the issue: nothing in the method or its documentation says
  so.
- **Not fixable here because**: the method bodies and their docstrings are upstream source; a
  README edit cannot make either method self-document its own no-op behavior. This candidate's
  API Reference and Scope and Limitations sections state plainly that both methods exist only for
  API-shape compatibility with the commercial product and are no-ops here.

## `AsposeNoteError` is not re-exported from the top-level `aspose.note` package
- **Severity**: INFORMATIONAL
- **Evidence**: `src/aspose/note/exceptions.py` defines `AsposeNoteError` as the base class every
  other exception (`FileCorruptedException`, `IncorrectDocumentStructureException`,
  `IncorrectPasswordException`, `UnsupportedFileFormatException`,
  `UnsupportedSaveFormatException`) inherits from. `src/aspose/note/__init__.py`'s own import
  list and `__all__` re-export all five subclasses from the top-level `aspose.note` package, but
  never `AsposeNoteError` itself — confirmed by reading the full file.
- **Impact**: `from aspose.note import AsposeNoteError` raises `ImportError`; a caller who wants
  the common base class (e.g. to catch every library exception in one `except` clause) must
  import it from `aspose.note.exceptions` instead, an inconsistency with every one of its own
  subclasses.
- **Not fixable here because**: `__init__.py`'s export list is upstream source, not a
  documentation defect. This candidate's API Reference states the correct import path directly.

## `examples/README.md` links to a stale GitHub org
- **Severity**: INFORMATIONAL
- **Evidence**: `examples/README.md`'s THIRD_PARTY_NOTICES.md link points to
  `https://github.com/aspose-note/aspose-note-python/blob/main/THIRD_PARTY_NOTICES.md`, but this
  repository's real, current origin is `aspose-note-foss/Aspose.Note-FOSS-for-Python` (confirmed
  via `pyproject.toml`'s `[project.urls]` and this knowledge base's own `model.yaml`).
- **Impact**: none for installed-package users; a contributor following that specific link from
  `examples/README.md` lands on a different (renamed/archived) GitHub location.
- **Not fixable here because**: this link lives inside the upstream repo's own
  `examples/README.md`, not this top-level README.
