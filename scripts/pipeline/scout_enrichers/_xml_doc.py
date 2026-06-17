"""XML doc comment enricher — extracts ``/// <summary>`` comments for .NET/C# classes."""

from __future__ import annotations

import re
from pathlib import Path

# Matches /// lines
_XML_DOC_RE = re.compile(r"^\s*///\s?(.*)")

# C# class/interface/struct/enum/record declaration
_DECL_RE = re.compile(
    r'(?:public|internal|protected|private)\s+'
    r'(?:(?:partial|static|sealed|abstract)\s+)*'
    r'(?:class|interface|struct|enum|record)\s+([A-Z]\w*)'
)

# C# method declaration
_METHOD_RE = re.compile(
    r'(?:public|internal|protected|private)\s+'
    r'(?:(?:static|virtual|override|abstract|sealed|async|new)\s+)*'
    r'(?:[\w<>\[\],\s?]+?)\s+(\w+)\s*\('
)


def _extract_xml_doc_comment(lines: list[str], declaration_line_idx: int) -> str:
    """Extract ``/// <summary>`` XML doc comment preceding a declaration.

    Walks backwards collecting consecutive ``///`` lines, strips XML tags,
    and returns clean plain text.
    """
    if declaration_line_idx <= 0:
        return ""

    collected: list[str] = []
    scan_limit = max(0, declaration_line_idx - 30)

    for i in range(declaration_line_idx - 1, scan_limit - 1, -1):
        m = _XML_DOC_RE.match(lines[i])
        if m:
            collected.append(m.group(1))
        else:
            stripped = lines[i].strip()
            # Allow blank lines or attribute lines between doc comment blocks
            if stripped.startswith("[") or stripped == "":
                continue
            break

    if not collected:
        return ""

    collected.reverse()
    raw = " ".join(collected)

    # Strip XML tags: <summary>, </summary>, <para>, <see cref="..."/>, etc.
    raw = re.sub(r"<[^>]+>", " ", raw)
    return re.sub(r"\s+", " ", raw).strip()


def enrich_xml_doc(classes: list[dict], repo_dir: Path) -> int:
    """Enrich class and method records with XML doc comment docstrings.

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
                    doc = _extract_xml_doc_comment(lines, line_idx)
                    if doc:
                        cls["doc"] = doc
                        enriched += 1

            for md in cls.get("methods", []):
                if md.get("doc"):
                    continue
                mname = md.get("name", "")
                if not mname:
                    continue
                # Use the method's own line number (0-based in source)
                # to extract the doc comment for THIS specific overload,
                # not the first overload that happens to have a comment.
                md_line = md.get("line")
                if md_line is not None:
                    idx = md_line - 1  # 1-based → 0-based
                    if 0 <= idx < len(lines):
                        doc = _extract_xml_doc_comment(lines, idx)
                        if doc:
                            md["doc"] = doc
                            enriched += 1
                    continue
                # Fallback for records without line info (legacy)
                for ml in method_lines.get(mname, []):
                    doc = _extract_xml_doc_comment(lines, ml)
                    if doc:
                        md["doc"] = doc
                        enriched += 1
                        break

    return enriched
