"""
lib/example_verification/fixtures.py

CONTRACT: scripts/pipeline/lib/example_verification/fixtures.py
  purpose: MT074 B6b -- a generic, deterministic DEFAULT FIXTURE PRELUDE. Tier-3
           runs of product examples routinely open sample input files
           (`new Document("report.<ext>")`, `File.ReadAllText("in.json")`,
           `open("data.csv")`); without a prelude every such example ends
           FIXTURE-UNAVAILABLE. This module generates MINIMAL VALID sample
           files by extension, with pure stdlib and byte-for-byte
           determinism (no wall clock, no randomness, ZIP_STORED entries with
           a fixed 1980-01-01 timestamp), and maps the INPUT names an example
           reads to those generators.
  inputs:  file names / example source text
  outputs: FixtureSpec, generate(), GENERATORS, input_fixture_names(),
           default_prelude()
  owner_domain: content-quality

Format-generic by design: nothing here knows any product. A name whose
extension has no generator is left UNRESOLVED on purpose -- the runner then
still reports FIXTURE-UNAVAILABLE for it (a disclosed gap, never a silent
pass). OUTPUT names (the example writes them) are never staged:
`input_fixture_names` classifies each quoted file-name literal by the calls
that precede it in its statement and keeps only reads; a literal it cannot
classify is excluded, not guessed.
"""
from __future__ import annotations

import io
import json
import re
import zipfile
from dataclasses import dataclass
from typing import Callable, Iterable, Mapping

# ---------------------------------------------------------------------------
# FixtureSpec (lives here so runners/java.py can import it without a cycle)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FixtureSpec:
    """One deterministic input file a prelude stages into the run's work
    dir. `content` is bytes/str, or a zero-arg callable returning one (kept
    lazy so a generator can be shared). `name` is a relative path; absolute
    paths and `..` segments are rejected by the stager."""

    name: str
    content: "bytes | str | Callable[[], bytes | str]" = b""


# ---------------------------------------------------------------------------
# Generators -- each returns bytes, deterministically
# ---------------------------------------------------------------------------

_ZIP_EPOCH = (1980, 1, 1, 0, 0, 0)


def _zip(entries: "list[tuple[str, str]]") -> bytes:
    """ZIP_STORED (no compressor => identical bytes on any zlib), fixed
    timestamps and attributes, entries in the given order."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as zf:
        for name, text in entries:
            info = zipfile.ZipInfo(name, date_time=_ZIP_EPOCH)
            info.compress_type = zipfile.ZIP_STORED
            info.external_attr = 0o600 << 16
            info.create_system = 0
            zf.writestr(info, text.encode("utf-8"))
    return buf.getvalue()


def _xml_escape(text: str) -> str:
    return (text.replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


_PDF_DEFAULT_LINES = (
    "Sample Document",
    "This is a minimal, valid, deterministic one-page PDF.",
    "It contains a few lines of text for example code to read.",
)
_PDF_TABLE = (
    ("Item", "Qty", "Price"),
    ("Widget", "2", "3.50"),
    ("Gadget", "4", "2.25"),
)


def _pdf_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def make_pdf(lines: "Iterable[str] | None" = None, *, table: bool = True) -> bytes:
    """A valid 1-page PDF 1.4 (Letter, Helvetica) with a few text lines and
    an optional small table-like text layout (fixed column positions). The
    xref table offsets are computed, not hard-coded; no /Info (no dates)."""
    text_lines = list(lines) if lines is not None else list(_PDF_DEFAULT_LINES)
    ops: list[str] = ["BT", "/F1 16 Tf", "72 720 Td", "18 TL"]
    for i, line in enumerate(text_lines):
        ops.append(f"({_pdf_escape(line)}) Tj")
        if i != len(text_lines) - 1:
            ops.append("T*")
    ops.append("ET")
    if table:
        ops.extend(["BT", "/F1 12 Tf"])
        y = 600
        for row in _PDF_TABLE:
            for x, cell in zip((72, 200, 280), row):
                ops.append(f"1 0 0 1 {x} {y} Tm ({_pdf_escape(cell)}) Tj")
            y -= 18
        ops.append("ET")
    stream = "\n".join(ops).encode("latin-1")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets: list[int] = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode() + body + b"\nendobj\n"
    xref_at = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode()
    out += b"0000000000 65535 f \n"
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += (f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref_at}\n%%EOF\n").encode()
    return bytes(out)


def make_xlsx() -> bytes:
    """Valid minimal OOXML workbook: strings (shared), numbers, a date-
    formatted number (builtin numFmt 14), a boolean, formula cells with
    cached values (=B2*C2, =B3*C3) and one merged range (A5:D5)."""
    ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    rel_ns = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    strings = ["Item", "Qty", "Price", "Total", "Date", "Active", "Widget", "Gadget", "Summary"]
    sst = {s: i for i, s in enumerate(strings)}

    def s_cell(ref: str, text: str) -> str:
        return f'<c r="{ref}" t="s"><v>{sst[text]}</v></c>'

    rows = [
        '<row r="1">' + "".join(s_cell(f"{c}1", t) for c, t in zip("ABCDEF", strings[:6])) + "</row>",
        '<row r="2">' + s_cell("A2", "Widget")
        + '<c r="B2"><v>2</v></c><c r="C2"><v>3.5</v></c>'
        + '<c r="D2"><f>B2*C2</f><v>7</v></c>'
        + '<c r="E2" s="1"><v>45292</v></c><c r="F2" t="b"><v>1</v></c></row>',
        '<row r="3">' + s_cell("A3", "Gadget")
        + '<c r="B3"><v>4</v></c><c r="C3"><v>2.25</v></c>'
        + '<c r="D3"><f>B3*C3</f><v>9</v></c>'
        + '<c r="E3" s="1"><v>45293</v></c><c r="F3" t="b"><v>0</v></c></row>',
        '<row r="5">' + s_cell("A5", "Summary") + "</row>",
    ]
    sheet = (
        f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<worksheet xmlns="{ns}">'
        '<dimension ref="A1:F5"/><sheetData>' + "".join(rows) + "</sheetData>"
        '<mergeCells count="1"><mergeCell ref="A5:D5"/></mergeCells></worksheet>'
    )
    sst_xml = (
        f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<sst xmlns="{ns}" '
        f'count="{len(strings)}" uniqueCount="{len(strings)}">'
        + "".join(f"<si><t>{_xml_escape(s)}</t></si>" for s in strings) + "</sst>"
    )
    styles = (
        f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<styleSheet xmlns="{ns}">'
        '<fonts count="1"><font><sz val="11"/><name val="Calibri"/></font></fonts>'
        '<fills count="2"><fill><patternFill patternType="none"/></fill>'
        '<fill><patternFill patternType="gray125"/></fill></fills>'
        '<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>'
        '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
        '<cellXfs count="2"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
        '<xf numFmtId="14" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/></cellXfs>'
        '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>'
        "</styleSheet>"
    )
    workbook = (
        f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<workbook xmlns="{ns}" '
        f'xmlns:r="{rel_ns}"><sheets><sheet name="Sheet1" sheetId="1" r:id="rId1"/></sheets></workbook>'
    )
    pkg = "http://schemas.openxmlformats.org/package/2006/relationships"
    return _zip([
        ("[Content_Types].xml",
         '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
         '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
         '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
         '<Default Extension="xml" ContentType="application/xml"/>'
         '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
         '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
         '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
         '<Override PartName="/xl/sharedStrings.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml"/>'
         "</Types>"),
        ("_rels/.rels",
         f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<Relationships xmlns="{pkg}">'
         f'<Relationship Id="rId1" Type="{rel_ns}/officeDocument" Target="xl/workbook.xml"/></Relationships>'),
        ("xl/workbook.xml", workbook),
        ("xl/_rels/workbook.xml.rels",
         f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<Relationships xmlns="{pkg}">'
         f'<Relationship Id="rId1" Type="{rel_ns}/worksheet" Target="worksheets/sheet1.xml"/>'
         f'<Relationship Id="rId2" Type="{rel_ns}/styles" Target="styles.xml"/>'
         f'<Relationship Id="rId3" Type="{rel_ns}/sharedStrings" Target="sharedStrings.xml"/></Relationships>'),
        ("xl/worksheets/sheet1.xml", sheet),
        ("xl/styles.xml", styles),
        ("xl/sharedStrings.xml", sst_xml),
    ])


def make_docx() -> bytes:
    """Valid minimal WordprocessingML: Heading1, a paragraph, a 2x2 table."""
    w = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    rel_ns = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    pkg = "http://schemas.openxmlformats.org/package/2006/relationships"

    def cell(text: str) -> str:
        return f"<w:tc><w:tcPr><w:tcW w:w=\"2400\" w:type=\"dxa\"/></w:tcPr><w:p><w:r><w:t>{text}</w:t></w:r></w:p></w:tc>"

    body = (
        '<w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>Sample Document</w:t></w:r></w:p>'
        "<w:p><w:r><w:t>A minimal, valid, deterministic paragraph.</w:t></w:r></w:p>"
        '<w:tbl><w:tblPr><w:tblW w:w="4800" w:type="dxa"/></w:tblPr>'
        '<w:tblGrid><w:gridCol w:w="2400"/><w:gridCol w:w="2400"/></w:tblGrid>'
        f"<w:tr>{cell('A1')}{cell('B1')}</w:tr><w:tr>{cell('A2')}{cell('B2')}</w:tr></w:tbl>"
        '<w:sectPr><w:pgSz w:w="12240" w:h="15840"/></w:sectPr>'
    )
    styles = (
        f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<w:styles xmlns:w="{w}">'
        '<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/></w:style>'
        '<w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/>'
        '<w:basedOn w:val="Normal"/><w:pPr><w:keepNext/></w:pPr>'
        '<w:rPr><w:b/><w:sz w:val="32"/></w:rPr></w:style></w:styles>'
    )
    return _zip([
        ("[Content_Types].xml",
         '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
         '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
         '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
         '<Default Extension="xml" ContentType="application/xml"/>'
         '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
         '<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>'
         "</Types>"),
        ("_rels/.rels",
         f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<Relationships xmlns="{pkg}">'
         f'<Relationship Id="rId1" Type="{rel_ns}/officeDocument" Target="word/document.xml"/></Relationships>'),
        ("word/document.xml",
         f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<w:document xmlns:w="{w}"><w:body>{body}</w:body></w:document>'),
        ("word/_rels/document.xml.rels",
         f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<Relationships xmlns="{pkg}">'
         f'<Relationship Id="rId1" Type="{rel_ns}/styles" Target="styles.xml"/></Relationships>'),
        ("word/styles.xml", styles),
    ])


def make_html() -> bytes:
    return (
        "<!DOCTYPE html>\n<html lang=\"en\">\n<head>\n<meta charset=\"utf-8\">\n"
        "<title>Sample Page</title>\n</head>\n<body>\n<h1>Sample Page</h1>\n"
        "<p>A small, deterministic page.</p>\n<ul>\n<li>First</li>\n<li>Second</li>\n</ul>\n"
        "<table>\n<tr><th>Item</th><th>Qty</th></tr>\n<tr><td>Widget</td><td>2</td></tr>\n"
        "<tr><td>Gadget</td><td>4</td></tr>\n</table>\n</body>\n</html>\n"
    ).encode("utf-8")


def make_md() -> bytes:
    return (
        "# Sample Document\n\nA short, deterministic paragraph with a "
        "[link](https://example.com/).\n\n- First item\n- Second item\n\n"
        "| Item | Qty |\n| --- | --- |\n| Widget | 2 |\n| Gadget | 4 |\n\n"
        "```text\nsample code\n```\n"
    ).encode("utf-8")


def make_txt() -> bytes:
    return b"Sample text.\nSecond line.\nThird line.\n"


def make_json() -> bytes:
    data = {"items": [{"name": "Widget", "qty": 2}, {"name": "Gadget", "qty": 4}], "title": "Sample"}
    return (json.dumps(data, sort_keys=True, indent=2) + "\n").encode("utf-8")


def make_csv() -> bytes:
    return b"Item,Qty,Price\nWidget,2,3.50\nGadget,4,2.25\n"


GENERATORS: "dict[str, Callable[[], bytes]]" = {
    ".pdf": make_pdf, ".xlsx": make_xlsx, ".docx": make_docx, ".html": make_html,
    ".htm": make_html, ".md": make_md, ".txt": make_txt, ".json": make_json, ".csv": make_csv,
}


def _ext(name: str) -> str:
    base = name.replace("\\", "/").rsplit("/", 1)[-1]
    return ("." + base.rsplit(".", 1)[-1].lower()) if "." in base else ""


def generate(name: str) -> "bytes | None":
    """Generated sample bytes for `name`'s extension, or None if unknown."""
    gen = GENERATORS.get(_ext(name))
    return gen() if gen else None


# ---------------------------------------------------------------------------
# Input-vs-output classification and the default prelude
# ---------------------------------------------------------------------------

_QUOTED_FILE_RE = re.compile(
    r"""["']((?:[A-Za-z0-9_][A-Za-z0-9_.,+ -]*/)*[A-Za-z0-9_][A-Za-z0-9_.,+ -]*\.[A-Za-z0-9]{1,6})["']""")
_IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
# WHOLE WORDS of a call/constructor/variable name (camelCase / PascalCase /
# snake_case split) that mean "this literal is WRITTEN" -- matched as words,
# never as substrings, so `target`, `address`, `profile`, `prefix` do not
# accidentally hit `get`/`add`/`file`/`fix`.
_OUTPUT_WORDS = frozenset({"save", "write", "export", "output", "dump", "store"})
# ... and READ. `new X("f")` (a constructor taking a file literal) also counts.
_INPUT_WORDS = frozenset({"open", "load", "read", "parse", "from", "input", "source", "import",
                          "merge", "append", "attach", "embed", "get", "add", "with", "file"})
_WORD_RE = re.compile(r"[A-Z]+(?![a-z])|[A-Z]?[a-z]+|[0-9]+")


def _words(ident: str) -> "set[str]":
    return {w.lower() for w in _WORD_RE.findall(ident.replace("_", " "))}


def _statement_prefix(code: str, start: int) -> str:
    """Text of the current statement before `start` (since the last `;`,
    `{`, `}` or newline)."""
    cut = max(code.rfind(c, 0, start) for c in (";", "{", "}", "\n"))
    return code[cut + 1:start]


def _classify(prefix: str) -> str:
    idents = _IDENT_RE.findall(prefix)
    words: set[str] = set()
    for ident in idents:
        words |= _words(ident)
    if words & _OUTPUT_WORDS or any(i.lower().startswith("to_") for i in idents):
        return "output"
    if "new" in {i.lower() for i in idents} or words & _INPUT_WORDS:
        return "input"
    return "unknown"


def input_fixture_names(code: str) -> "list[str]":
    """Quoted, extension-bearing file names the example READS: a literal is
    kept only when every occurrence of it is classified as an input by the
    calls preceding it in its statement. A name that is ever an output, or
    cannot be classified, is excluded. Relative paths only (absolute and
    `..` names dropped). First-seen order, de-duplicated."""
    verdicts: dict[str, set[str]] = {}
    order: list[str] = []
    for m in _QUOTED_FILE_RE.finditer(code):
        name = m.group(1).replace("\\", "/")
        if name.startswith("/") or ".." in name.split("/"):
            continue
        verdicts.setdefault(name, set()).add(_classify(_statement_prefix(code, m.start())))
        if name not in order:
            order.append(name)
    return [n for n in order if verdicts[n] == {"input"}]


def default_prelude(
    names: "Iterable[str]", *, extensions: "Iterable[str] | Mapping[str, object] | None" = None,
) -> "list[FixtureSpec]":
    """FixtureSpecs for the given INPUT `names` whose extension has a
    generator (and, when `extensions` is given, is in it -- entries with or
    without the leading dot). Unknown extensions are simply not returned, so
    the runner still reports FIXTURE-UNAVAILABLE for them. Callers pass only
    inputs (see `input_fixture_names`); order and de-duplication follow
    `names`."""
    allowed = None
    if extensions is not None:
        allowed = {("." + e.lstrip(".")).lower() for e in extensions}
    specs: list[FixtureSpec] = []
    seen: set[str] = set()
    for name in names:
        if name in seen:
            continue
        seen.add(name)
        ext = _ext(name)
        if ext not in GENERATORS or (allowed is not None and ext not in allowed):
            continue
        specs.append(FixtureSpec(name, GENERATORS[ext]))
    return specs


def generators_fingerprint() -> str:
    """Stable fingerprint of what `default_prelude` can stage: sha256 over
    every (extension, sha256(generated bytes)). Changes whenever a generator
    changes, so a cached verification proven against old sample files is
    never served for new ones."""
    import hashlib
    h = hashlib.sha256()
    for ext in sorted(GENERATORS):
        h.update(ext.encode("utf-8") + b"=" + hashlib.sha256(GENERATORS[ext]()).digest())
    return h.hexdigest()[:16]
