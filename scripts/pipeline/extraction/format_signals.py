"""extraction/format_signals.py — Identifier-word format recognizer (D-6).

Mission MT040, TC-MT040-45. One place that knows how to split an identifier
into words by its language's case convention (PascalCase/camelCase via
``_split_camel_words``, snake_case via ``_split_snake_words``), classify its
leading verb word(s) against an import/export vocabulary, and pick the first
known file-format token among the remaining words.

This module is the canonical home for ``_KNOWN_FORMAT_TOKENS`` (previously
defined directly in ``extraction/formats.py``) and for the acronym-boundary
word splitter ``_split_pascal_format_token`` that formats.py's Pass 1e
(PascalCase verb+format-token method names, e.g. ``Page.AddSVG``) has used
since ST-022. ``extraction/formats.py`` imports these names back into its own
namespace so existing external references (``extraction.formats.
_KNOWN_FORMAT_TOKENS`` etc.) keep working unchanged.

Two recognizer entry points are exposed, both built on the same word-boundary
primitive (``_split_pascal_format_token`` / ``_split_camel_words``) but with
deliberately different scanning behaviour, because the two call sites need
provably different things:

- ``recognize_pascal_verb_token(verb, remainder)`` — parity mode for Pass 1e.
  Reproduces the pre-refactor behaviour byte-for-byte: only the SINGLE word
  immediately after the verb is considered (no filler-skipping, no scanning
  further into the identifier, original case preserved in the returned
  ``format`` value). This is what makes the Pass-1e refactor a provable
  no-op — see ``scripts/pipeline/tests/extraction/test_format_signals.py``'s
  golden-parity test.
- ``recognize_camel_identifier_format(name, ...)`` — general mode for the new
  TypeScript/JavaScript exported-function pass (Pass 1g, TC-MT040-14). Splits
  the WHOLE identifier into lowercase words via ``_split_camel_words``, then
  scans every word after the verb (skipping known filler words) for the
  first known format token — e.g. ``renderDocumentToDocx`` -> ``docx``/
  ``export``, ``addImagePages`` -> no token found (documented miss: "image"/
  "pages" name neither a filler nor a format).

Collapsing these into a single call with a mode flag was considered and
rejected: Pass 1e's original algorithm only ever looked at the first word of
the remainder in ORIGINAL case, while the TS pass needs a full, lowercase,
filler-aware scan across the whole identifier — implementing that as one
function's "true" branch would make the "false" branch (parity mode) an
unused-looking special case future edits could silently break. Two thin,
well-named entry points sharing one splitter primitive is safer and reads
clearly at each call site.
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# Known short file-format tokens (moved from extraction/formats.py, ST-022).
# Deliberately broad (spans the format vocabulary of the Aspose product
# families this pipeline covers: pdf, cells, slides, words, email, 3d, note,
# page, font, html, barcode, tex) -- a generic fix must not be tuned to any
# one product's shape.
#
# TC-MT040-14 (G-TS-11) addition: "fdf" and "xfdf" (Adobe Forms Data Format /
# XML Forms Data Format) -- pdf/typescript's ``writeFdf``/``readFdf``/
# ``writeXfdf``/``readXfdf`` are real, verified exported functions
# (runs/.clone_cache/aspose_pdf_typescript/src/fdf.ts, src/xfdf.ts) and
# neither token was previously recognized by any pass.
#
# IMPORTANT -- this addition is NOT visible to Pass 1e (see
# `_PASCAL_VERB_KNOWN_TOKENS` below). Golden-parity testing during this same
# change (TC-MT040-14/45) found that pdf/go (`Form.ExportFDF`/`ImportFDF`,
# form_fdf.go) and pdf/net (`Form.ExportFdf`/`ImportFdf`,
# `Annotation.WriteXfdf`/`ImportXfdf`, both real, verified methods) would
# ALSO start producing new fdf/xfdf entries through Pass 1e the moment this
# token was added to a set Pass 1e reads from -- a real, accurate detection,
# but a cross-product behaviour change on two already-launched, non-TS
# products that is out of scope for TC-MT040-14 (pdf/typescript) and
# TC-MT040-45 (the Pass-1e refactor, which is required to be a byte-identical
# no-op). See `_PASCAL_VERB_KNOWN_TOKENS` for how Pass 1e is insulated from
# this and every future addition here. Filed as a follow-up rather than
# silently expanded into this change: pdf/go and pdf/net's FDF/XFDF format
# support is real and currently undetected by Pass 1e.
# ---------------------------------------------------------------------------
_KNOWN_FORMAT_TOKENS: frozenset[str] = frozenset({
    "svg", "pdf", "html", "htm", "xml", "json", "csv", "tsv",
    "xls", "xlsx", "xlsm", "xlsb", "ods", "doc", "docx", "docm", "odt",
    "ppt", "pptx", "pptm", "odp", "rtf", "txt", "md", "yaml", "yml",
    "png", "jpg", "jpeg", "gif", "bmp", "tiff", "tif", "ico", "webp",
    "emf", "wmf", "eps", "ps", "svgz", "cgm", "cdr",
    "zip", "tar", "gz",
    "eml", "msg", "mbox", "vcf", "ics",
    "fbx", "obj", "gltf", "glb", "stl", "dae", "3ds", "u3d", "amf",
    "ply", "x3d", "dxf",
    "mp3", "mp4", "wav", "avi", "mov", "webm",
    "ttf", "otf", "woff", "woff2",
    "cfb", "jbig2", "epub", "mobi", "azw3", "mhtml", "chm", "xps", "djvu",
    "markdown", "latex", "tex",
    "fdf", "xfdf",
})

# Pass-1e parity baseline (TC-MT040-45): the EXACT `_KNOWN_FORMAT_TOKENS`
# contents as of the pre-refactor ST-022 pass (2026-07-30), frozen as its own
# explicit literal rather than derived by subtracting from
# `_KNOWN_FORMAT_TOKENS` above. `recognize_pascal_verb_token` (Pass 1e)
# checks against THIS set, not the growing canonical one, so that adding a
# token here for a new language's pass (fdf/xfdf for TypeScript today; the
# next one tomorrow) can never silently change Pass 1e's output for an
# already-launched Go/Java/C#/C++ product again -- that already happened
# once during this change (see the comment above `_KNOWN_FORMAT_TOKENS`) and
# is exactly the class of regression the golden-parity test exists to catch.
_PASCAL_VERB_KNOWN_TOKENS: frozenset[str] = frozenset({
    "svg", "pdf", "html", "htm", "xml", "json", "csv", "tsv",
    "xls", "xlsx", "xlsm", "xlsb", "ods", "doc", "docx", "docm", "odt",
    "ppt", "pptx", "pptm", "odp", "rtf", "txt", "md", "yaml", "yml",
    "png", "jpg", "jpeg", "gif", "bmp", "tiff", "tif", "ico", "webp",
    "emf", "wmf", "eps", "ps", "svgz", "cgm", "cdr",
    "zip", "tar", "gz",
    "eml", "msg", "mbox", "vcf", "ics",
    "fbx", "obj", "gltf", "glb", "stl", "dae", "3ds", "u3d", "amf",
    "ply", "x3d", "dxf",
    "mp3", "mp4", "wav", "avi", "mov", "webm",
    "ttf", "otf", "woff", "woff2",
    "cfb", "jbig2", "epub", "mobi", "azw3", "mhtml", "chm", "xps", "djvu",
    "markdown", "latex", "tex",
})


# ---------------------------------------------------------------------------
# Verb vocabularies
# ---------------------------------------------------------------------------

# Pascal-verb sets (Go/Java/C# `<Verb><FormatToken>(` identifiers, e.g.
# `Page.AddSVG`) -- IDENTICAL to formats.py's pre-refactor
# `_PASCAL_IMPORT_VERBS` / `_PASCAL_EXPORT_VERBS`. Kept separate from the
# TS-extended sets below so Pass 1e's output stays byte-identical after the
# refactor: widening this set would change which methods Pass 1e matches on
# every already-launched Go/Java/C#/C++ product, not just add TS coverage.
_PASCAL_IMPORT_VERBS: frozenset[str] = frozenset(
    {"add", "insert", "load", "read", "import", "open", "parse"})
_PASCAL_EXPORT_VERBS: frozenset[str] = frozenset(
    {"save", "write", "export", "serialize"})

# TypeScript/JavaScript exported-function verb vocabulary (TC-MT040-14,
# G-TS-11): a superset of the Pascal verbs above. `from`/`to` cover the
# `fromFile`/`fromBuffer`/`fromBytes`/`fromPath` and `toBytes`/`toBuffer`
# shapes (the object-noun half of each compound is itself a filler word, see
# `_FILLER_WORDS`, so e.g. `fromBuffer` classifies as an import verb with no
# format token found -- correctly no match on its own). `render` and a bare
# `export` are TS-specific additions verified against this repo's real shape
# (`renderDocumentToDocx`, `renderEpub`, `renderDocumentToTiff` in
# runs/.clone_cache/aspose_pdf_typescript/src/{docxexport,epubexport,
# raster}.ts).
_TS_IMPORT_VERBS: frozenset[str] = _PASCAL_IMPORT_VERBS | {"from"}
_TS_EXPORT_VERBS: frozenset[str] = _PASCAL_EXPORT_VERBS | {"to", "render"}

# Filler words skipped while scanning for a format token after the verb.
# TS-pass only: Pass 1e's parity path (`recognize_pascal_verb_token`) never
# skips words -- it only ever looks at the single word right after the verb,
# matching the pre-refactor `_split_pascal_format_token(remainder)` contract.
_FILLER_WORDS: frozenset[str] = frozenset({
    "document", "page", "pages", "file", "to", "from", "as", "with",
    "stream", "buffer", "bytes", "path",
})


def _split_pascal_format_token(remainder: str) -> str:
    """Extract the first camelCase/acronym word from a PascalCase identifier
    remainder (the portion of a method name right after its verb prefix).

    Applies the standard acronym-boundary rule used by camelCase splitters: a
    run of leading uppercase letters that is followed by a lowercase letter
    treats the LAST uppercase letter of that run as the start of the next
    word -- the same rule that splits "HTTPServer" into "HTTP" + "Server",
    not "HTTPS" + "erver". This lets a single, simple function correctly
    reduce every one of pdf/go's real SVG method names to the bare token
    "SVG": "AddSVG" (nothing follows -- the whole remainder is the acronym),
    "AddSVGFromStream" / "AddSVGObject" / "LoadSVGFromStream" (the acronym
    run ends because a lowercase letter follows, so the last uppercase
    letter -- "G" -- starts the next word: "SVG" + "FromStream"/"Object").
    Ordinary single-capital words (e.g. "Watermark" in "AddWatermark") take
    the other branch: consume the trailing lowercase/digit run as-is.

    Moved verbatim from extraction/formats.py (ST-022, 2026-07-30) as part of
    the TC-MT040-45 refactor -- unchanged, since `recognize_pascal_verb_token`
    depends on it for Pass 1e's byte-identical parity.
    """
    if not remainder:
        return ""
    j = 1
    while j < len(remainder) and remainder[j].isupper():
        j += 1
    if j == 1:
        # Ordinary capitalized word (Svg, Watermark, ...).
        k = 1
        while k < len(remainder) and (remainder[k].islower() or remainder[k].isdigit()):
            k += 1
        return remainder[:k]
    if j == len(remainder):
        # Whole remainder is one acronym run (AddSVG -> "SVG").
        return remainder
    # Acronym run ends because a lowercase letter follows -- the last
    # uppercase letter belongs to the next word (AddSVGFromStream -> "SVG").
    return remainder[: j - 1]


def _split_camel_words(name: str) -> list[str]:
    """Split a camelCase/PascalCase identifier into LOWERCASE words.

    Built on the same acronym-boundary rule as `_split_pascal_format_token`
    (a run of uppercase letters followed by a lowercase letter treats the
    LAST uppercase letter of the run as the start of the next word), applied
    repeatedly across the WHOLE identifier instead of once at its head --
    an uppercase-starting run delegates to `_split_pascal_format_token` for
    exactly this reason, so the two functions can never disagree about where
    a word boundary falls.

    A leading `$`/`_` (valid TS/JS identifier characters that are never part
    of a word) is stripped first. Digits attach to the preceding
    lowercase/digit run (`renderTo3ds` -> ["render", "to3ds"] is the accepted
    shape here -- no fixture or real-world identifier this pass needs to
    recognize splits a digit away from its adjacent letters).

    Examples: `_split_camel_words("renderDocumentToDocx") ==
    ["render", "document", "to", "docx"]`; `_split_camel_words("AddSVG") ==
    ["add", "svg"]`; `_split_camel_words("addImagePages") ==
    ["add", "image", "pages"]`.
    """
    ident = name.lstrip("_$")
    words: list[str] = []
    i = 0
    n = len(ident)
    while i < n:
        ch = ident[i]
        if ch.islower() or ch.isdigit():
            j = i + 1
            while j < n and (ident[j].islower() or ident[j].isdigit()):
                j += 1
            words.append(ident[i:j].lower())
            i = j
        elif ch.isupper():
            token = _split_pascal_format_token(ident[i:])
            if not token:
                # Defensive: _split_pascal_format_token only returns "" for
                # an empty input, which can't happen here since ch exists --
                # kept so a future change to that function can't loop forever.
                i += 1
                continue
            words.append(token.lower())
            i += len(token)
        else:
            # Non-alnum char (shouldn't occur in a valid TS/JS identifier
            # once a leading _/$ is stripped) -- skip it rather than crash.
            i += 1
    return words


def _split_snake_words(name: str) -> list[str]:
    """Split a snake_case identifier into lowercase words.

    Not currently wired into any caller in formats.py (Pass 2's snake_case
    scanning stays its own independent regex, out of scope for TC-MT040-14/
    45) -- provided so `format_signals.py` covers all three case styles the
    D-6 design calls for, ready for the next language that needs it.
    """
    return [w.lower() for w in name.strip("_").split("_") if w]


def recognize_pascal_verb_token(verb: str, remainder: str) -> dict | None:
    """Pass-1e parity recognizer.

    `verb` and `remainder` are the two groups already captured by formats.py's
    `_PASCAL_IO_VERB_RE` (e.g. `verb="Add"`, `remainder="SVGFromStream"` for
    `AddSVGFromStream(`). Classifies `verb` against the Pascal import/export
    vocabularies and extracts the token via `_split_pascal_format_token`
    (single word, ORIGINAL CASE preserved, no filler-skipping, no scanning
    past the first word) -- reproducing `_scan_pascal_verb_format_methods`'s
    pre-refactor behaviour exactly, including the returned `format` value's
    casing (e.g. "SVG", not "svg").

    Returns `{"format": <original-case token>, "direction": "import"|
    "export", "evidence_kind": "pascal_verb_token"}` or `None`.
    """
    verb_lower = verb.lower()
    if verb_lower in _PASCAL_IMPORT_VERBS:
        direction = "import"
    elif verb_lower in _PASCAL_EXPORT_VERBS:
        direction = "export"
    else:
        return None
    token = _split_pascal_format_token(remainder)
    if token.lower() not in _PASCAL_VERB_KNOWN_TOKENS:
        return None
    return {
        "format": token,
        "direction": direction,
        "evidence_kind": "pascal_verb_token",
    }


def recognize_camel_identifier_format(
    name: str,
    *,
    import_verbs: frozenset[str] = _TS_IMPORT_VERBS,
    export_verbs: frozenset[str] = _TS_EXPORT_VERBS,
    filler_words: frozenset[str] = _FILLER_WORDS,
    known_tokens: frozenset[str] = _KNOWN_FORMAT_TOKENS,
    evidence_kind: str = "ts_io_identifier",
) -> dict | None:
    """General recognizer for the TypeScript/JavaScript exported-function
    pass (Pass 1g, TC-MT040-14, G-TS-11).

    Splits `name` (camelCase or PascalCase) into lowercase words via
    `_split_camel_words`. The FIRST word must classify as an import or
    export verb, or this returns `None` immediately. Every word after it is
    then scanned in order (skipping filler words) for the first word that is
    a known format token; the scan does NOT stop on a non-filler,
    non-matching word -- it keeps going, which is what lets
    `renderDocumentToDocx` reach "docx" past "document"/"to", while
    `addImagePages` correctly finds nothing ("image" is neither filler nor a
    token; "pages" is filler; no format word exists in the identifier at
    all -- a documented, accepted miss, not a bug).

    Returns `{"format": <lowercase token>, "direction": "import"|"export",
    "evidence_kind": evidence_kind}` or `None`.
    """
    words = _split_camel_words(name)
    if len(words) < 2:
        return None
    verb = words[0]
    if verb in import_verbs:
        direction = "import"
    elif verb in export_verbs:
        direction = "export"
    else:
        return None
    for word in words[1:]:
        if word in filler_words:
            continue
        if word in known_tokens:
            return {
                "format": word,
                "direction": direction,
                "evidence_kind": evidence_kind,
            }
    return None
