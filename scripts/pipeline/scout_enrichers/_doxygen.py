"""Doxygen enricher — extracts ``///`` and ``/** ... */`` comments for C++ classes/methods."""

from __future__ import annotations

import re
from pathlib import Path

# Triple-slash Doxygen lines: /// text
_DOXYGEN_TRIPLE_RE = re.compile(r"^\s*///\s?(.*)")

# Doxygen command tags to strip
_DOXYGEN_TAG_RE = re.compile(
    r"^\s*[@\\](?:param|return|returns|throws|exception|see|since|deprecated|"
    r"note|warning|author|version|details|remark|sa|retval|tparam)\b"
)

# C++ class/struct/enum declaration
_DECL_RE = re.compile(r'(?:class|struct|enum\s+class|enum)\s+([A-Z]\w*)')

# C++ method declaration (simplified)
_METHOD_RE = re.compile(
    r'(?:virtual\s+|static\s+|inline\s+|constexpr\s+)*'
    r'(?:[\w:*&<>\s]+?)\s+(\w+)\s*\('
)


def _extract_doxygen_comment(lines: list[str], declaration_line_idx: int) -> str:
    """Extract Doxygen comment (``///`` or ``/** */``) preceding a declaration.

    Handles both triple-slash and block-style Doxygen comments.
    """
    if declaration_line_idx <= 0:
        return ""

    scan_limit = max(0, declaration_line_idx - 30)

    # Try triple-slash (///) first
    triple_collected: list[str] = []
    for i in range(declaration_line_idx - 1, scan_limit - 1, -1):
        m = _DOXYGEN_TRIPLE_RE.match(lines[i])
        if m:
            triple_collected.append(m.group(1))
        else:
            stripped = lines[i].strip()
            if stripped == "":
                continue
            break

    if triple_collected:
        triple_collected.reverse()
        cleaned: list[str] = []
        for line in triple_collected:
            s = line.strip()
            if _DOXYGEN_TAG_RE.match(s):
                continue
            s = re.sub(r"^[@\\]brief\s+", "", s)
            if s:
                cleaned.append(s)
        if cleaned:
            raw = " ".join(cleaned)
            raw = re.sub(r"<[^>]+>", " ", raw)
            return re.sub(r"\s+", " ", raw).strip()

    # Try block-style (/** ... */)
    block_end_idx = -1
    for i in range(declaration_line_idx - 1, scan_limit - 1, -1):
        stripped = lines[i].strip()
        if stripped == "":
            continue
        if stripped.endswith("*/"):
            block_end_idx = i
            break
        return ""

    if block_end_idx < 0:
        return ""

    collected: list[str] = []
    found_start = False
    for i in range(block_end_idx, scan_limit - 1, -1):
        collected.append(lines[i])
        if "/**" in lines[i]:
            found_start = True
            break

    if not found_start:
        return ""

    collected.reverse()
    cleaned_block: list[str] = []
    for line in collected:
        s = line.strip()
        if s.startswith("/**"):
            s = s[3:]
        if s.endswith("*/"):
            s = s[:-2]
        if s.startswith("*"):
            s = s[1:]
        s = s.strip()
        if _DOXYGEN_TAG_RE.match(s):
            continue
        s = re.sub(r"^[@\\]brief\s+", "", s)
        if s:
            cleaned_block.append(s)

    if not cleaned_block:
        return ""

    raw = " ".join(cleaned_block)
    raw = re.sub(r"<[^>]+>", " ", raw)
    return re.sub(r"\s+", " ", raw).strip()


def enrich_doxygen(classes: list[dict], repo_dir: Path) -> int:
    """Enrich class and method records with Doxygen docstrings.

    Returns the number of items enriched.
    """
    by_file: dict[str, list[dict]] = {}
    for cls in classes:
        fp = cls.get("file", "")
        if fp:
            by_file.setdefault(fp, []).append(cls)

    enriched = 0

    for rel_path, file_classes in by_file.items():
        abs_path = repo_dir / rel_path
        if not abs_path.exists():
            continue

        try:
            content = abs_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        lines = content.splitlines()

        name_to_line: dict[str, int] = {}
        for i, line in enumerate(lines):
            m = _DECL_RE.search(line)
            if m and m.group(1) not in name_to_line:
                name_to_line[m.group(1)] = i

        method_lines: dict[str, list[int]] = {}
        for i, line in enumerate(lines):
            m = _METHOD_RE.search(line)
            if m:
                method_lines.setdefault(m.group(1), []).append(i)

        for cls in file_classes:
            name = cls.get("name", "")

            if name and not cls.get("doc"):
                line_idx = name_to_line.get(name)
                if line_idx is not None:
                    doc = _extract_doxygen_comment(lines, line_idx)
                    if doc:
                        cls["doc"] = doc
                        enriched += 1

            for md in cls.get("methods", []):
                if md.get("doc"):
                    continue
                mname = md.get("name", "")
                if not mname:
                    continue
                # Prefer the method's own line number to avoid cross-overload
                # doc leaking (same overload-name, different signatures).
                md_line = md.get("line")
                if md_line is not None:
                    idx = md_line - 1  # 1-based → 0-based
                    if 0 <= idx < len(lines):
                        doc = _extract_doxygen_comment(lines, idx)
                        if doc:
                            md["doc"] = doc
                            enriched += 1
                    continue
                # Fallback for records without line info (legacy)
                for ml in method_lines.get(mname, []):
                    doc = _extract_doxygen_comment(lines, ml)
                    if doc:
                        md["doc"] = doc
                        enriched += 1
                        break

    return enriched
