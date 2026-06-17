"""Javadoc enricher — extracts ``/** ... */`` comments for Java classes/methods."""

from __future__ import annotations

import re
from pathlib import Path

# Java annotation line (not Javadoc tags inside comment blocks)
_JAVA_ANNOTATION_RE = re.compile(r"^\s*@[A-Z]")

# Javadoc tag lines to strip from extracted text
_JAVADOC_TAG_RE = re.compile(
    r"^\s*@(?:param|return|returns|throws|exception|see|since|"
    r"deprecated|author|version|serial|link)\b"
)

# Java class/interface/enum declaration
_DECL_RE = re.compile(
    r'(?:public|protected|private)\s+'
    r'(?:(?:static|final|abstract|strictfp)\s+)*'
    r'(?:class|interface|enum)\s+([A-Z]\w*)'
)

# Java method declaration
_METHOD_RE = re.compile(
    r'(?:public|protected|private)\s+'
    r'(?:(?:static|final|abstract|synchronized|native)\s+)*'
    r'(?:[\w<>\[\],\s]+?)\s+(\w+)\s*\('
)


def _extract_javadoc_comment(lines: list[str], declaration_line_idx: int) -> str:
    """Extract ``/** ... */`` Javadoc comment preceding a declaration.

    Walks backwards from *declaration_line_idx - 1*, skipping blank lines
    and annotation lines, looking for a ``*/`` ... ``/**`` block.
    """
    if declaration_line_idx <= 0:
        return ""

    scan_limit = max(0, declaration_line_idx - 30)

    # Phase 1: skip annotations and blank lines to find closing */
    block_end_idx = -1
    for i in range(declaration_line_idx - 1, scan_limit - 1, -1):
        stripped = lines[i].strip()
        if stripped == "" or _JAVA_ANNOTATION_RE.match(lines[i]):
            continue
        if stripped.endswith("*/"):
            block_end_idx = i
            break
        return ""

    if block_end_idx < 0:
        return ""

    # Phase 2: collect lines backward until /**
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

    # Phase 3: strip delimiters and clean up
    cleaned: list[str] = []
    for line in collected:
        s = line.strip()
        if s.startswith("/**"):
            s = s[3:]
        if s.endswith("*/"):
            s = s[:-2]
        if s.startswith("*"):
            s = s[1:]
        s = s.strip()
        if _JAVADOC_TAG_RE.match(s):
            continue
        if s:
            cleaned.append(s)

    if not cleaned:
        return ""

    raw = " ".join(cleaned)
    return re.sub(r"\s+", " ", raw).strip()


def enrich_javadoc(classes: list[dict], repo_dir: Path) -> int:
    """Enrich class and method records with Javadoc docstrings.

    Returns the number of items enriched.
    """
    # Group classes by source file
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

        # Map class names → declaration line indices
        name_to_line: dict[str, int] = {}
        for i, line in enumerate(lines):
            m = _DECL_RE.search(line)
            if m and m.group(1) not in name_to_line:
                name_to_line[m.group(1)] = i

        # Map method names → line indices
        method_lines: dict[str, list[int]] = {}
        for i, line in enumerate(lines):
            m = _METHOD_RE.search(line)
            if m:
                method_lines.setdefault(m.group(1), []).append(i)

        for cls in file_classes:
            name = cls.get("name", "")

            # Enrich class docstring
            if name and not cls.get("doc"):
                line_idx = name_to_line.get(name)
                if line_idx is not None:
                    doc = _extract_javadoc_comment(lines, line_idx)
                    if doc:
                        cls["doc"] = doc
                        enriched += 1

            # Enrich method docstrings
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
                        doc = _extract_javadoc_comment(lines, idx)
                        if doc:
                            md["doc"] = doc
                            enriched += 1
                    continue
                # Fallback for records without line info (legacy)
                for ml in method_lines.get(mname, []):
                    doc = _extract_javadoc_comment(lines, ml)
                    if doc:
                        md["doc"] = doc
                        enriched += 1
                        break

    return enriched
