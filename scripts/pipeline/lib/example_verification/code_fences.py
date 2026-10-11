"""
lib/example_verification/code_fences.py

CONTRACT: scripts/pipeline/lib/example_verification/code_fences.py
  purpose: ONE canonical CommonMark-conformant fenced-code-block tokenizer.
           Rounds 3 (RC6) and 4 (RC19) of the governing plan found ~40
           independent regex fence parsers across this pipeline, several of
           which (`_CODE_FENCE_RE`/`_ANY_LANG_CODE_BLOCK_RE`, both `^```(\\w*)`)
           cannot match a `c#` or `c++` info string at all -- `\\w*` stops at
           the `#`/`+` -- so those blocks are silently invisible to whichever
           subsystem is asking. Every new consumer should call
           enumerate_code_blocks()/block_spans() from here instead of writing
           another regex; existing regex-based parsers migrate behind an
           explicit, evidence-recorded parity check (see
           test_example_verification_code_fences.py), not silently.
  inputs:  markdown text (str)
  outputs: list[CodeBlock]
  owner_domain: content-quality
  stdlib only -- zero repo imports, so content_eval/models.py (which must not
  pull in tree-sitter or any other heavier example_verification dependency)
  can import this one file directly.

CommonMark fence rules implemented (spec §4.5, the practical subset this
repo's content actually needs):
  - Fence character is backtick or tilde; opening run length >= 3.
  - A backtick-fenced opening line's info string may not itself contain a
    backtick (tildes have no such restriction).
  - The closing fence must use the SAME character and a run length >= the
    opening run's length -- a run of the same character shorter than the
    opening is literal content, not a close (this is what lets a ````
    (4-backtick) block safely contain a literal ``` (3-backtick) example).
  - Up to 3 leading spaces are permitted on the opening fence; that many
    leading spaces are stripped from every content line and are also
    tolerated (independently) on the closing fence.
  - An unterminated fence runs to end-of-document (CommonMark still counts
    it as a code block) -- the previous per-consumer regex toggles instead
    silently absorbed the remainder of the file as prose and never emitted
    a block; recorded as an explained parity difference, not a bug ported
    forward.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

# Real-world info-string "lang" token: a leading run of word characters plus
# the handful of symbols actual fence tags use (c++, c#, f#, objective-c).
# `\w` already covers underscores/digits/letters; the previous per-consumer
# `\w*` regexes could not match `#`/`+` at all, which is exactly RC6/RC19.
_LANG_TOKEN_RE = re.compile(r"^[\w+#.\-]*")

_OPEN_FENCE_RE = re.compile(r"^( {0,3})(`{3,}|~{3,})[ \t]*(.*?)[ \t]*$")

# Canonical language-tag aliasing so callers keyed on one spelling (e.g. the
# runner registry, the platform_capabilities.yaml site) don't need to know
# every fence-tag spelling a README might use.
_CANONICAL_LANG_MAP = {
    "c#": "csharp",
    "cs": "csharp",
    "csharp": "csharp",
    "c++": "cpp",
    "cpp": "cpp",
    "cplusplus": "cpp",
    "ts": "typescript",
    "typescript": "typescript",
    "rs": "rust",
    "rust": "rust",
    "golang": "go",
    "go": "go",
}


def canonicalize_lang(lang: str) -> str:
    """Map a raw fence-tag spelling to its canonical form (lowercase key)."""
    key = (lang or "").strip().lower()
    return _CANONICAL_LANG_MAP.get(key, key)


def normalize_content(content: str) -> str:
    """CRLF -> LF, dedent common leading whitespace, rstrip each line, strip
    blank edge lines. Used to compute `sha256_norm` so cosmetic differences
    (line endings, a copy-pasted extra indent level, trailing whitespace)
    don't defeat content-keyed identity (governing plan's Round 3 item C)."""
    text = content.replace("\r\n", "\n").replace("\r", "\n")
    lines = [ln.rstrip() for ln in text.split("\n")]
    while lines and lines[0] == "":
        lines.pop(0)
    while lines and lines[-1] == "":
        lines.pop()
    if not lines:
        return ""
    indents = [len(ln) - len(ln.lstrip(" ")) for ln in lines if ln.strip()]
    common = min(indents) if indents else 0
    if common:
        lines = [ln[common:] if len(ln) >= common else ln.lstrip(" ") for ln in lines]
    return "\n".join(lines)


@dataclass(slots=True)
class CodeBlock:
    """A fenced code block extracted from markdown.

    Keeps content_eval.models.CodeBlock's four required fields (lang,
    content, start_line, end_line) in the same order so that dataclass's
    positional construction stays compatible with the 24 existing
    `Page.code_blocks` consumers; every field after end_line is additive
    and defaulted, computed in __post_init__ when not supplied.
    """

    lang: str
    content: str
    start_line: int
    end_line: int
    index: int = 0
    info: str = ""
    fence_char: str = "`"
    fence_len: int = 3
    indent: int = 0
    sha256_exact: str = ""
    sha256_norm: str = ""
    canonical_lang: str = ""

    def __post_init__(self) -> None:
        if not self.sha256_exact:
            self.sha256_exact = hashlib.sha256(self.content.encode("utf-8")).hexdigest()
        if not self.sha256_norm:
            self.sha256_norm = hashlib.sha256(
                normalize_content(self.content).encode("utf-8")
            ).hexdigest()
        if not self.canonical_lang:
            self.canonical_lang = canonicalize_lang(self.lang)


def enumerate_code_blocks(text: str, line_offset: int = 0) -> list[CodeBlock]:
    """Tokenize `text` into fenced code blocks per the CommonMark fence rules
    described in this module's docstring. `line_offset` shifts every
    reported line number (used by callers like content_eval's Page, which
    parses only the body after a stripped-off frontmatter block)."""
    lines = text.splitlines()
    blocks: list[CodeBlock] = []
    n = len(lines)
    i = 0
    index = 0
    while i < n:
        m = _OPEN_FENCE_RE.match(lines[i])
        if not m:
            i += 1
            continue
        indent, fence, info = m.group(1), m.group(2), m.group(3)
        fence_char = fence[0]
        fence_len = len(fence)
        if fence_char == "`" and "`" in info:
            # Not a valid opening fence per CommonMark -- a backtick info
            # string may not itself contain a backtick.
            i += 1
            continue
        indent_len = len(indent)
        start_line_no = i + line_offset + 1
        close_re = re.compile(
            r"^ {0,3}" + re.escape(fence_char) + "{" + str(fence_len) + ",}[ \t]*$"
        )
        content_lines: list[str] = []
        j = i + 1
        end_line_no = None
        while j < n:
            if close_re.match(lines[j]):
                end_line_no = j + line_offset + 1
                j += 1
                break
            candidate = lines[j]
            stripped_prefix = 0
            while (
                stripped_prefix < indent_len
                and stripped_prefix < len(candidate)
                and candidate[stripped_prefix] == " "
            ):
                stripped_prefix += 1
            content_lines.append(candidate[stripped_prefix:])
            j += 1
        if end_line_no is None:
            # Unterminated fence: CommonMark still counts it, running to EOF.
            end_line_no = n + line_offset
        lang_match = _LANG_TOKEN_RE.match(info.strip())
        lang = lang_match.group(0) if lang_match else ""
        blocks.append(
            CodeBlock(
                lang=lang,
                content="\n".join(content_lines),
                start_line=start_line_no,
                end_line=end_line_no,
                index=index,
                info=info,
                fence_char=fence_char,
                fence_len=fence_len,
                indent=indent_len,
            )
        )
        index += 1
        i = j
    return blocks


def block_spans(text: str) -> list[tuple[int, int]]:
    """Return only (start_line, end_line) 1-based spans, for callers (e.g.
    body_refresh's fence-span consumer) that need fence locations without
    materializing block content."""
    return [(b.start_line, b.end_line) for b in enumerate_code_blocks(text)]
