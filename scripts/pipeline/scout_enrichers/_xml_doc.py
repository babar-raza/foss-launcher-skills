"""XML doc comment enricher — extracts ``/// <summary>`` comments for .NET/C# classes."""

from __future__ import annotations

import re
from pathlib import Path

# Matches /// lines
_XML_DOC_RE = re.compile(r"^\s*///\s?(.*)")

# [Obsolete(...)] / [Obsolete] attribute line (Task 15, §9.10, closes G9).
# Previously these lines were silently allowed to pass through the backward
# scan (treated like a blank line) without their text ever being captured.
# group(1) is the quoted reason argument if present (e.g. [Obsolete("Use Bar
# instead")] -> "Use Bar instead"); may be None for a bare [Obsolete].
_OBSOLETE_ATTR_RE = re.compile(r'^\s*\[\s*(?:System\.)?Obsolete(?:\s*\(\s*"([^"]*)")?')

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


def _extract_xml_doc_comment(lines: list[str], declaration_line_idx: int) -> tuple[str, "str | None"]:
    """Extract ``/// <summary>`` XML doc comment preceding a declaration.

    Walks backwards collecting consecutive ``///`` lines, strips XML tags,
    and returns clean plain text.

    Returns (doc_text, deprecated_reason). Task 15 (§9.10, closes G9): an
    ``[Obsolete(...)]``/``[Obsolete]`` attribute line encountered during the
    same backward scan was previously just skipped over identically to a
    blank line; its own text (specifically the reason argument, when present)
    is now captured instead of discarded. *doc_text* itself is unaffected.
    *deprecated_reason* is ``None`` when no ``[Obsolete]`` attribute was seen
    at all, or ``""`` when one was seen but carried no reason argument (a bare
    ``[Obsolete]``) -- callers must distinguish these two cases (the former
    means "no signal", the latter still means "deprecated: True").
    """
    if declaration_line_idx <= 0:
        return "", None

    collected: list[str] = []
    deprecated_reason: str | None = None
    scan_limit = max(0, declaration_line_idx - 30)

    for i in range(declaration_line_idx - 1, scan_limit - 1, -1):
        m = _XML_DOC_RE.match(lines[i])
        if m:
            collected.append(m.group(1))
        else:
            stripped = lines[i].strip()
            if stripped == "":
                continue
            obs_match = _OBSOLETE_ATTR_RE.match(lines[i])
            if obs_match:
                deprecated_reason = obs_match.group(1) or ""
                continue
            # Allow other attribute lines between doc comment blocks
            if stripped.startswith("["):
                continue
            break

    if not collected:
        return "", deprecated_reason

    collected.reverse()
    raw = " ".join(collected)

    # Strip XML tags: <summary>, </summary>, <para>, <see cref="..."/>, etc.
    raw = re.sub(r"<[^>]+>", " ", raw)
    doc_text = re.sub(r"\s+", " ", raw).strip()
    return doc_text, deprecated_reason


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

            # Task 15 (§9.10, closes G9): the [Obsolete] check must run even
            # when "doc" was already populated by an earlier pass -- mirrors
            # _javadoc.py's identical rationale (see its own comment).
            if name:
                line_idx = name_to_line.get(name)
                if line_idx is not None:
                    doc, dep_reason = _extract_xml_doc_comment(lines, line_idx)
                    if doc and not cls.get("doc"):
                        cls["doc"] = doc
                        enriched += 1
                    if dep_reason is not None:
                        cls["deprecated"] = True
                        if dep_reason:
                            cls["deprecated_reason"] = dep_reason

            for md in cls.get("methods", []):
                already_documented = bool(md.get("doc"))
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
                        doc, dep_reason = _extract_xml_doc_comment(lines, idx)
                        if doc and not already_documented:
                            md["doc"] = doc
                            enriched += 1
                        if dep_reason is not None:
                            md["deprecated"] = True
                            if dep_reason:
                                md["deprecated_reason"] = dep_reason
                    continue
                # Fallback for records without line info (legacy). Cannot skip
                # this whole block just because doc is already set -- that
                # would also skip the [Obsolete] capture, the same bug shape
                # the md_line branch above was fixed for.
                for ml in method_lines.get(mname, []):
                    doc, dep_reason = _extract_xml_doc_comment(lines, ml)
                    if not doc and dep_reason is None:
                        continue  # this candidate line has no doc comment at all
                    if dep_reason is not None:
                        md["deprecated"] = True
                        if dep_reason:
                            md["deprecated_reason"] = dep_reason
                    if doc and not already_documented:
                        md["doc"] = doc
                        enriched += 1
                    break

    return enriched
