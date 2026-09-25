"""fence_structure_repair.py -- MT073 TC-09 (LOCALE-CODE-BLOCK-DEFECT-REMEDIATION).

Detects and repairs two distinct locale-page fence-structure corruptions found
by locale_code_block_equivalence.py's LANG_MISMATCH/COUNT_MISMATCH findings
(ST-215 Bucket 3), both diagnosed live against real content this mission:

1. MISSING_OPENER: a section's own `` ```lang `` fence-open (and any leading
   import/using lines) was dropped during translation, so the section's real
   code content starts as bare paragraph text. CommonMark then misreads the
   section's own (still-present) closing fence as an *opening* untagged fence,
   which swallows everything up to the next accidental fence line -- and can
   cascade through the rest of the page. Exemplar:
   content/blog.aspose.org/3d/net/3d-utilities-net/index.tr.md.

2. DUPLICATE_BLOCK: a section's code is present TWICE -- once unfenced and
   missing its leading import line (directly after the heading+prose, where
   the real fenced block should be), and once complete and correctly fenced
   (after a `---` separator that reads as though it starts a new section).
   The next heading then follows with no separator at all (it was consumed by
   the misplaced second copy). Exemplar:
   content/docs.aspose.org/sv/cells/net/developer-guide/features.md.

Code content is never translated in this repo's convention (only prose/
headings/comments may be) -- both detectors exploit this: an English block's
own content (or a suffix of it, tolerating a translated leading comment or a
missing import line) is searched for verbatim in the locale text.

Every repair is mandatorily self-verifying: `repair_file()` re-parses the
repaired text and refuses to report success unless the locale's resulting
block list is an EXACT match (count, canonical language, and content) against
English's own blocks. Callers must never write to disk on a non-OK result --
this module never guesses when a file's real shape doesn't match either
known corruption signature.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from .code_fences import CodeBlock, enumerate_code_blocks

Kind = Literal["missing_opener", "duplicate_block"]


@dataclass(frozen=True)
class FenceRepair:
    kind: Kind
    description: str
    # Applied as: text[:start] + insert + text[end:]  (start==end for a pure insert)
    start: int
    end: int
    insert: str


@dataclass
class RepairResult:
    status: Literal["ok", "no_repair_needed", "unresolved"]
    kind: Kind | None
    repairs: list[FenceRepair]
    new_text: str | None
    detail: str


def _strip_frontmatter(text: str) -> tuple[str, int]:
    if not text.startswith("---"):
        return text, 0
    end = text.find("\n---", 3)
    if end == -1:
        return text, 0
    body = text[end + 4 :]
    offset = text[: end + 4].count("\n")
    return body, offset


def _blocks_of(text: str) -> list[CodeBlock]:
    body, offset = _strip_frontmatter(text)
    return enumerate_code_blocks(body, line_offset=offset)


def _find_unique(text: str, needle: str) -> int | None:
    """Position of `needle` in `text` if it occurs EXACTLY once AND starts at
    a real line boundary (position 0 or right after a "\\n"), else None.

    The line-boundary requirement is load-bearing, not cosmetic: a plain
    substring search can match `needle` starting mid-identifier (e.g. the
    suffix "Vector3 min = ..." matching inside a locale's own, unrelated
    "FVector3 min = ..." line) -- confirmed live on content/blog.aspose.org/
    3d/net/3d-utilities-net/index.tr.md, where this produced a corrupted
    insertion splicing a fence-open literally into the middle of a word.
    """
    if not needle:
        return None
    start = 0
    while True:
        pos = text.find(needle, start)
        if pos == -1:
            return None
        if pos == 0 or text[pos - 1] == "\n":
            break
        start = pos + 1
    if text.find(needle, pos + 1) != -1:
        return None
    return pos


def _longest_unique_suffix(text: str, block_lines: list[str]) -> tuple[int, int] | None:
    """Longest suffix of `block_lines` that occurs exactly once in `text`.

    Returns (k, pos): block_lines[k:] joined by "\\n" is that unique match, at
    character offset `pos`. Returns None if no non-blank suffix matches
    exactly once (ambiguous or absent -- caller must not guess).
    """
    for k in range(len(block_lines)):
        candidate = "\n".join(block_lines[k:])
        if not candidate.strip():
            continue
        pos = _find_unique(text, candidate)
        if pos is not None:
            return k, pos
    return None


def _canonical_separator(locale_text: str, locale_blocks: list[CodeBlock]) -> str | None:
    """The exact blank/---/blank text this locale FILE's own already-intact
    first block uses between its closing fence and the next heading -- reused
    verbatim for any gap this module inserts, rather than assuming a universal
    format. Returns None if it can't be isolated (caller then skips inserting
    a separator rather than guessing one).

    The insertion point this is spliced into (see `detect_duplicate_block`)
    already sits directly before the closing fence line's OWN trailing
    "\\n" (which precedes the next heading in the corrupted text), so the
    result needs a LEADING "\\n" to open a new line after "```" but no
    trailing one -- that existing "\\n" already supplies it. Getting this
    wrong is a real, visible formatting defect this repair must not
    introduce even though it happens to fall outside any fenced block, so
    the mandatory code-block verification gate can't catch it on its own:
    an earlier version of this function produced a doubled blank line
    ("```\\n\\n---\\n\\n\\n### Heading") until this was caught by direct
    inspection of a real repaired file, not just the block-level check."""
    if not locale_blocks:
        return None
    first = locale_blocks[0]
    lines = locale_text.split("\n")
    close_idx = first.end_line - 1  # 0-based index of the closing fence line
    j = close_idx + 1
    while j < len(lines) and not lines[j].lstrip().startswith("#"):
        j += 1
    if j >= len(lines) or j == close_idx + 1:
        return None
    return "\n" + "\n".join(lines[close_idx + 1 : j])


def detect_missing_opener(en_blocks: list[CodeBlock], locale_text: str) -> list[FenceRepair] | None:
    """Detect MISSING_OPENER gaps. Returns None (unresolved) if any English
    block can't be confidently, uniquely located in the locale text -- never
    a partial/best-effort guess."""
    repairs: list[FenceRepair] = []
    for b in en_blocks:
        lang = b.canonical_lang or b.lang
        block_lines = b.content.split("\n")
        match = _longest_unique_suffix(locale_text, block_lines)
        if match is None:
            return None
        k, pos = match
        before = locale_text[:pos].rstrip("\n")
        last_line = before.split("\n")[-1] if before else ""
        if last_line.strip() == f"```{lang}":
            continue  # already correctly fenced
        if last_line.strip().startswith("```"):
            return None  # fenced with a DIFFERENT tag -- not this defect shape
        insert_text = f"```{lang}\n" if k == 0 else f"```{lang}\n" + "\n".join(block_lines[:k]) + "\n"
        repairs.append(FenceRepair("missing_opener", f"missing fence-open before block (lang={lang})", pos, pos, insert_text))
    return repairs


def detect_duplicate_block(en_blocks: list[CodeBlock], locale_text: str) -> list[FenceRepair] | None:
    """Detect DUPLICATE_BLOCK gaps. Returns None (unresolved) if any English
    block can't be confidently matched to its real, correctly-fenced locale
    occurrence, or if a candidate duplicate span looks too short to trust."""
    locale_blocks = _blocks_of(locale_text)
    separator = _canonical_separator(locale_text, locale_blocks)
    repairs: list[FenceRepair] = []
    for b in en_blocks:
        lang = b.canonical_lang or b.lang
        block_lines = b.content.split("\n")
        real = _longest_unique_suffix(locale_text, block_lines)
        if real is None:
            return None
        k_real, pos_real = real
        before_real = locale_text[:pos_real].rstrip("\n")
        last_line_real = before_real.split("\n")[-1] if before_real else ""
        if last_line_real.strip() != f"```{lang}":
            return None  # the "real" occurrence isn't cleanly fenced either

        dup_start = None
        for k2 in range(k_real, len(block_lines)):
            candidate = "\n".join(block_lines[k2:])
            if len(candidate.strip()) <= 40:
                continue
            first = locale_text.find(candidate)
            if first != -1 and first < pos_real:
                dup_start = first
                break
        if dup_start is None:
            continue  # this block has no duplicate -- nothing to repair here

        real_open_pos = pos_real - len(f"```{lang}\n")
        if locale_text[real_open_pos : real_open_pos + len(f"```{lang}\n")] != f"```{lang}\n":
            return None  # position arithmetic didn't land exactly on the fence line
        repairs.append(FenceRepair(
            "duplicate_block",
            f"duplicate unfenced copy of block (lang={lang}) before its real fenced copy",
            dup_start, real_open_pos, "",
        ))

        real_close_end = pos_real + len(b.content) + len("\n```")
        already_separated = locale_text[real_close_end : real_close_end + 2] == "\n\n"
        if not already_separated and separator is not None:
            repairs.append(FenceRepair(
                "duplicate_block", f"missing separator after block (lang={lang})'s real close",
                real_close_end, real_close_end, separator,
            ))
    return repairs


def apply_repairs(text: str, repairs: list[FenceRepair]) -> str:
    """Apply non-overlapping repairs from the END of the text backward so
    earlier character offsets stay valid."""
    ordered = sorted(repairs, key=lambda r: r.start, reverse=True)
    new_text = text
    for r in ordered:
        new_text = new_text[: r.start] + r.insert + new_text[r.end :]
    return new_text


def _blocks_match_exactly(a: list[CodeBlock], b: list[CodeBlock]) -> bool:
    """Compares language tags exactly and content via `sha256_norm` (the
    same CRLF/line-ending/common-indent/trailing-whitespace-normalized hash
    every other locale-equivalence tool in this module family already uses)
    rather than raw `.content` equality -- confirmed live that a byte-exact
    check is too strict even for an UNTOUCHED block: a harmless extra blank
    line before a block's closing fence is a legitimate, pre-existing
    formatting variance this repair must not treat as a verification
    failure."""
    if len(a) != len(b):
        return False
    return all(
        (x.canonical_lang or x.lang) == (y.canonical_lang or y.lang) and x.sha256_norm == y.sha256_norm
        for x, y in zip(a, b)
    )


def _read_normalized(path: "str | Path") -> tuple[str, bool]:
    """Read a file with all line endings normalized to plain "\\n" for
    analysis, reporting whether the ORIGINAL file used CRLF so callers can
    restore that exact convention on write. Reading with `newline=""` (as
    this module's sibling fixers do for surgical single-line edits) would
    silently break every string match in this module against an English
    reference that is always LF -- confirmed live: content/blog.aspose.org/
    3d/net/3d-utilities-net/index.tr.md is CRLF while its English
    counterpart is LF, and every multi-line suffix match failed until this
    normalization was added."""
    raw = Path(path).read_bytes().decode("utf-8")
    crlf = "\r\n" in raw
    return raw.replace("\r\n", "\n").replace("\r", "\n"), crlf


def repair_file(en_path: "str | Path", locale_path: "str | Path") -> RepairResult:
    """Diagnose and (if resolvable) compute a verified repair for one locale
    file against its English counterpart. Never writes to disk -- callers
    write `result.new_text` themselves only when `result.status == "ok"`
    (already restored to the locale file's own original line-ending
    convention)."""
    en_text, _ = _read_normalized(en_path)
    locale_text, locale_is_crlf = _read_normalized(locale_path)
    en_blocks = _blocks_of(en_text)
    locale_blocks = _blocks_of(locale_text)

    if _blocks_match_exactly(locale_blocks, en_blocks):
        return RepairResult("no_repair_needed", None, [], None, "locale already matches English exactly")

    for kind, detector in (("missing_opener", detect_missing_opener), ("duplicate_block", detect_duplicate_block)):
        repairs = detector(en_blocks, locale_text)
        if not repairs:
            continue
        new_text = apply_repairs(locale_text, repairs)
        new_blocks = _blocks_of(new_text)
        if _blocks_match_exactly(new_blocks, en_blocks):
            if locale_is_crlf:
                new_text = new_text.replace("\n", "\r\n")
            return RepairResult("ok", kind, repairs, new_text, f"{len(repairs)} {kind} repair(s), verified against English")

    return RepairResult(
        "unresolved", None, [], None,
        "neither detector produced a verified repair -- this file's real shape doesn't "
        "match either known corruption signature; do not guess, escalate for manual review",
    )
