#!/usr/bin/env python3
"""
normalize_code_block_blanks.py — Remove spurious blank lines from products page code fences.

Removes spurious blank lines inside code fence regions in product page YAML frontmatter.
Matches the exact same detection logic as detect_code_block_blanks.py / validate_plugin_structure.py.
Covers ALL locales including English (en/).

Three YAML formats are handled, each with different blank-line semantics:

  1. Literal block scalar (content: |)
     - Every blank line in raw source → blank in parsed value (defect)
     - Fix: remove ALL blank lines from code fence regions

  2. Single-quoted multiline (content: '...')
     - 1 blank line in raw → \\n separator in parsed (harmless)
     - 2+ blank lines in raw → \\n\\n in parsed → blank in code (defect)
     - Fix: compress 2+ consecutive blank runs to 0

  3. Double-quoted (content: "...", with \\n encoded as backslash-n)
     - Single physical line OR multi-physical-line with YAML line-fold (trailing \\)
     - 1 \\n\\n (2 backslash-n chars) → 1 blank in parsed (defect)
     - Fix: after splitting on backslash-n, remove ALL empty virtual lines
            inside code fence regions; each physical line processed independently

Rules applied (matching detect_code_block_blanks.py):
  1. BLANK_AFTER_OPEN_FENCE    — blank after opening fence    (all snippet lengths)
  2. BLANK_BEFORE_CLOSE_FENCE  — blank before closing fence   (all snippet lengths)
  3. INTERNAL_BLANK_SHORT_SNIPPET — blank inside short snippet (≤8 non-empty lines only)
  For long snippets (>8 non-empty lines): internal blanks are PRESERVED.

Does NOT use yaml.dump — avoids reformatting locale translations or prose.

Usage:
    python normalize_code_block_blanks.py [--dry-run] [--output REPORT.json] [--path PATH]
"""
import re
import sys
import json
import os
from pathlib import Path

REPO = Path(os.getcwd())
DEFAULT_PRODUCTS = REPO / "content" / "products.aspose.org"

SHORT_SNIPPET_THRESHOLD = 8

# Opening code fence: must have language specifier (```lang)
OPEN_FENCE = re.compile(r"^```\S")
# Closing code fence: ``` alone
CLOSE_FENCE = re.compile(r"^```\s*$")

# Literal 2-char backslash-n sequence as encoded in raw double-quoted YAML
_LNL = "\\n"

# YAML literal block scalar indicator: key: | or key: |-, key: |+, key: >
_LITERAL_BLOCK_RE = re.compile(r"^([ \t]*)[\w][\w_-]*\s*:\s*[|>]")


# ---------------------------------------------------------------------------
# Helpers: normalize a sequence of lines/virtual-lines inside a code block
# ---------------------------------------------------------------------------

def _remove_boundary_blanks(items):
    """Strip leading and trailing blank items from a list (in-place slice)."""
    start = 0
    while start < len(items) and items[start].strip() == "":
        start += 1
    end = len(items)
    while end > start and items[end - 1].strip() == "":
        end -= 1
    return items[start:end]


def _remove_boundary_blanks_sq(lines):
    """Strip leading and trailing 2+-blank RUNS from a list.

    In single-quoted YAML: 1 blank = harmless, 2+ blanks = defect.
    Only strips leading/trailing runs of ≥2 consecutive blank lines.
    """
    # Leading
    start = 0
    while start < len(lines):
        if lines[start].strip() == "":
            run_end = start
            while run_end < len(lines) and lines[run_end].strip() == "":
                run_end += 1
            if run_end - start >= 2:
                start = run_end  # skip 2+ run
            else:
                break  # single blank — keep and stop
        else:
            break
    # Trailing
    end = len(lines)
    while end > start:
        if lines[end - 1].strip() == "":
            run_start = end - 1
            while run_start > start and lines[run_start - 1].strip() == "":
                run_start -= 1
            if end - run_start >= 2:
                end = run_start
            else:
                break
        else:
            break
    return lines[start:end]


def _compress_2plus_blanks(lines):
    """Compress runs of 2+ consecutive blank lines to 0. Preserve single blanks.

    Single-quoted YAML: 1 blank → \\n (harmless), 2+ blanks → \\n\\n (defect).
    """
    result = []
    i = 0
    while i < len(lines):
        if lines[i].strip() == "":
            run_start = i
            while i < len(lines) and lines[i].strip() == "":
                i += 1
            run_len = i - run_start
            if run_len == 1:
                result.append(lines[run_start])  # single blank → keep
            # 2+ blanks → discard (defect)
        else:
            result.append(lines[i])
            i += 1
    return result


def _remove_all_blanks(items):
    """Remove ALL blank items. Used for literal | blocks and double-quoted strings."""
    return [x for x in items if x.strip() != ""]


# ---------------------------------------------------------------------------
# Normalize a code block's content: chooses strategy based on YAML format
# ---------------------------------------------------------------------------

def _normalize_block_literal(block_lines, is_short):
    """Literal block (|): every blank = defect. Remove boundary blanks always;
    remove ALL internal blanks for short snippets."""
    middle = _remove_boundary_blanks(block_lines)
    if is_short:
        return _remove_all_blanks(middle)
    return middle


def _normalize_block_single_quoted(block_lines, is_short):
    """Single-quoted: 1 blank harmless, 2+ blanks = defect. Compress 2+ runs."""
    middle = _remove_boundary_blanks_sq(block_lines)
    if is_short:
        return _compress_2plus_blanks(middle)
    return middle


def _normalize_dq_block(vparts, is_short):
    """Double-quoted (virtual lines split on backslash-n): 1 empty = 1 blank in parsed.
    Remove boundary empties always; remove ALL internal empties for short snippets."""
    middle = _remove_boundary_blanks(vparts)
    if is_short:
        return _remove_all_blanks(middle)
    return middle


# ---------------------------------------------------------------------------
# Double-quoted single-line handler
# ---------------------------------------------------------------------------

def _fix_dq_value(raw_line):
    """Fix blank lines inside code fences in a double-quoted YAML string line.

    Splits on the literal 2-char backslash-n sequence, processes virtual lines,
    and rejoins.
    """
    if _LNL not in raw_line or "```" not in raw_line:
        return raw_line

    parts = raw_line.split(_LNL)
    result = []
    i = 0

    while i < len(parts):
        vl = parts[i]
        vs = vl.strip()

        if OPEN_FENCE.match(vs):
            open_vl = vl
            i += 1
            block_parts = []

            while i < len(parts):
                bv = parts[i]
                if CLOSE_FENCE.match(bv.strip()):
                    close_vl = bv
                    i += 1
                    break
                block_parts.append(bv)
                i += 1
            else:
                result.append(open_vl)
                result.extend(block_parts)
                continue

            non_empty = sum(1 for p in block_parts if p.strip())
            is_short = non_empty <= SHORT_SNIPPET_THRESHOLD
            result.append(open_vl)
            result.extend(_normalize_dq_block(block_parts, is_short))
            result.append(close_vl)
        else:
            result.append(vl)
            i += 1

    return _LNL.join(result)


# ---------------------------------------------------------------------------
# Helpers: multi-physical-line double-quoted YAML scalar handling (GAP-CSSP-R09)
# ---------------------------------------------------------------------------

def _has_unescaped_quote(s):
    """Return True if s contains a double-quote not immediately preceded by backslash.

    Used to detect whether a double-quoted YAML scalar has been closed on the
    current physical line or continues to the next via a line-fold backslash.
    """
    j = 0
    while j < len(s):
        if s[j] == '\\':
            j += 2  # skip escape pair (e.g. \" or \\)
        elif s[j] == '"':
            return True
        else:
            j += 1
    return False


def _join_dq_fold(physical_lines):
    """Join physical lines of a multi-line DQ YAML scalar into one raw YAML line.

    Applies YAML double-quoted scalar line-fold rules:
      - Trailing \\ on a physical line = fold: remove it and strip leading whitespace
        on the next physical line before joining.
      - \\ followed by a space at the start of a continuation (after lstrip) = literal
        space in the parsed value; replace with a single space.

    The result is a single (possibly long) physical line containing the full raw
    YAML double-quoted scalar: key: "...full content...".
    """
    parts = []
    for idx, line in enumerate(physical_lines):
        if idx == 0:
            s = line.rstrip()
            parts.append(s[:-1] if s.endswith('\\') else line)
        else:
            content = line.lstrip()
            if content.startswith('\\ '):
                content = ' ' + content[2:]
            s = content.rstrip()
            parts.append(s[:-1] if s.endswith('\\') else content)
    return ''.join(parts)


def _fix_dq_multiline_value(physical_lines):
    """Fix blank lines in code fences within a multi-physical-line DQ YAML scalar.

    Joins all physical lines into a single logical raw YAML line (via
    _join_dq_fold), applies _fix_dq_value to remove blank lines inside code
    fences, then returns either [fixed_single_line] (if changed) or the
    original physical_lines list (if unchanged).
    """
    joined = _join_dq_fold(physical_lines)
    fixed = _fix_dq_value(joined)
    if fixed == joined:
        return physical_lines
    return [fixed]


# ---------------------------------------------------------------------------
# Raw frontmatter normalization with YAML context tracking
# ---------------------------------------------------------------------------

def _normalize_fm_lines(fm_text):
    """Normalize code block blank lines in raw YAML frontmatter.

    Tracks the current YAML scalar format (literal | vs single-quoted vs
    multi-physical-line double-quoted) to apply the correct blank-line removal
    strategy for each code fence region found.

    Multi-physical-line double-quoted scalars (GAP-CSSP-R09):
      content: "prose...\\
        \\n\\n```csharp\\nusing Aspose.Pdf;\\n\\n\\
        var input = ...
    All physical lines are buffered, joined via _join_dq_fold into a single
    logical line, then fixed by _fix_dq_value and written back (as one line
    if changed, or as original physical lines if unchanged).
    """
    lines = fm_text.split("\n")
    result = []

    literal_block_mode = False   # True when inside a | or > block scalar
    literal_base_indent = 0      # indentation level of the literal block's key
    in_dq_multiline = False      # True when buffering a multi-physical-line DQ scalar
    dq_buffer = []               # accumulated physical lines of the current DQ value

    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.rstrip()

        # --- Multi-physical-line DQ scalar: buffer continuation lines ---
        if in_dq_multiline:
            dq_buffer.append(line)
            if not stripped.endswith('\\'):
                # Last physical line of the DQ value — flush and fix
                in_dq_multiline = False
                result.extend(_fix_dq_multiline_value(dq_buffer))
                dq_buffer = []
            i += 1
            continue

        # --- Double-quoted key line: detect single-line vs start of multi-line ---
        if (not literal_block_mode
                and '"' in line
                and re.match(r"^[ \t]*[\w][\w_-]*\s*:", line)):
            m = re.match(r'^[ \t]*[\w][\w_-]*\s*:\s*"', line)
            if m and stripped.endswith('\\') and not _has_unescaped_quote(line[m.end():]):
                # Start of multi-physical-line DQ value: begin buffering
                in_dq_multiline = True
                dq_buffer = [line]
            else:
                # Single-line DQ value: apply fix immediately
                if _LNL in line and "```" in line:
                    result.append(_fix_dq_value(line))
                else:
                    result.append(line)
            i += 1
            continue

        # --- Detect literal block scalar start ---
        m_lit = _LITERAL_BLOCK_RE.match(line)
        if m_lit:
            literal_block_mode = True
            literal_base_indent = len(m_lit.group(1))
            result.append(line)
            i += 1
            continue

        # --- Check if we have exited the literal block ---
        if literal_block_mode and line.strip():
            curr_indent = len(line) - len(line.lstrip())
            if curr_indent <= literal_base_indent:
                literal_block_mode = False

        ls = line.strip()

        if OPEN_FENCE.match(ls):
            # Opening fence: collect the full code block content
            open_line = line
            i += 1
            block_lines = []
            is_lit = literal_block_mode  # capture mode at fence-open time

            while i < len(lines):
                bl = lines[i]
                if CLOSE_FENCE.match(bl.strip()):
                    close_line = bl
                    i += 1
                    break
                block_lines.append(bl)
                i += 1
            else:
                # No closing fence found — emit as-is
                result.append(open_line)
                result.extend(block_lines)
                continue

            non_empty = sum(1 for bl in block_lines if bl.strip())
            is_short = non_empty <= SHORT_SNIPPET_THRESHOLD

            result.append(open_line)
            if is_lit:
                result.extend(_normalize_block_literal(block_lines, is_short))
            else:
                result.extend(_normalize_block_single_quoted(block_lines, is_short))
            result.append(close_line)
        else:
            result.append(line)
            i += 1

    return "\n".join(result)


# ---------------------------------------------------------------------------
# File-level processing
# ---------------------------------------------------------------------------

def normalize_file(md_path, dry_run=False):
    """Normalize a single product page. Returns (changed, old_len, new_len)."""
    text = md_path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return False, 0, 0
    parts = text.split("---", 2)
    if len(parts) < 3:
        return False, 0, 0

    fm_orig = parts[1]
    fm_new = _normalize_fm_lines(fm_orig)

    if fm_new == fm_orig:
        return False, len(fm_orig), len(fm_orig)

    if not dry_run:
        new_text = "---" + fm_new + "---" + parts[2]
        md_path.write_text(new_text, encoding="utf-8")

    return True, len(fm_orig), len(fm_new)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    dry_run = "--dry-run" in sys.argv
    scan_path = DEFAULT_PRODUCTS
    output_path = None

    args = sys.argv[1:]
    idx = 0
    while idx < len(args):
        if args[idx] == "--output" and idx + 1 < len(args):
            output_path = args[idx + 1]
            idx += 2
        elif args[idx] == "--path" and idx + 1 < len(args):
            scan_path = Path(args[idx + 1])
            idx += 2
        else:
            idx += 1

    changed_files = []
    unchanged_files = []
    error_files = []

    for md in sorted(scan_path.rglob("_index.md")):
        rel = str(md.relative_to(REPO)).replace("\\", "/")
        try:
            changed, old_len, new_len = normalize_file(md, dry_run=dry_run)
            if changed:
                changed_files.append({"file": rel, "old_len": old_len, "new_len": new_len})
            else:
                unchanged_files.append(rel)
        except Exception as exc:
            error_files.append({"file": rel, "error": str(exc)})

    mode = "DRY-RUN" if dry_run else "APPLY"
    print(f"Mode:      {mode}")
    print(f"Changed:   {len(changed_files)}")
    print(f"Unchanged: {len(unchanged_files)}")
    print(f"Errors:    {len(error_files)}")

    if error_files:
        print("\nERRORS:")
        for e in error_files:
            print(f"  {e['file']}: {e['error']}")

    if changed_files:
        limit = 30
        print(f"\nFiles {'that would change' if dry_run else 'changed'} ({len(changed_files)}):")
        for f in changed_files[:limit]:
            delta = f["new_len"] - f["old_len"]
            print(f"  {f['file']}  ({delta:+d} chars)")
        if len(changed_files) > limit:
            print(f"  ... and {len(changed_files) - limit} more")

    report = {
        "mode": mode,
        "changed": len(changed_files),
        "unchanged": len(unchanged_files),
        "errors": len(error_files),
        "changed_files": changed_files,
        "unchanged_files": unchanged_files,
        "error_files": error_files,
    }

    if output_path:
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"\nReport: {output_path}")

    return 1 if error_files else 0


if __name__ == "__main__":
    sys.exit(main())
