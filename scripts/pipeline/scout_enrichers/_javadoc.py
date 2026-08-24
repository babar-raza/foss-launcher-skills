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

# @deprecated tag specifically -- captured separately (Task 15, §9.10, closes
# G9) instead of only being discarded like the other tags above. group(1) is
# the reason text following the tag, e.g. "@deprecated Use newMethod() instead"
# -> "Use newMethod() instead" (may be empty for a bare "@deprecated").
_JAVADOC_DEPRECATED_RE = re.compile(r"^\s*@deprecated\b\s*(.*)$")

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


def _extract_javadoc_comment(lines: list[str], declaration_line_idx: int) -> tuple[str, "str | None"]:
    """Extract ``/** ... */`` Javadoc comment preceding a declaration.

    Walks backwards from *declaration_line_idx - 1*, skipping blank lines
    and annotation lines, looking for a ``*/`` ... ``/**`` block.

    Returns (doc_text, deprecated_reason). Task 15 (§9.10, closes G9): this
    tag's line was previously discarded identically to every other Javadoc
    tag (@param, @return, ...) -- it is still excluded from *doc_text*
    (unchanged behavior for that field), but its own text is no longer thrown
    away. *deprecated_reason* is ``None`` when no ``@deprecated`` tag was seen
    at all, or ``""`` when one was seen with no reason text following it --
    callers must distinguish these two cases (the former means "no signal",
    the latter still means "deprecated: True").
    """
    if declaration_line_idx <= 0:
        return "", None

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
        return "", None

    if block_end_idx < 0:
        return "", None

    # Phase 2: collect lines backward until /**
    collected: list[str] = []
    found_start = False
    for i in range(block_end_idx, scan_limit - 1, -1):
        collected.append(lines[i])
        if "/**" in lines[i]:
            found_start = True
            break

    if not found_start:
        return "", None

    collected.reverse()

    # Phase 3: strip delimiters and clean up
    cleaned: list[str] = []
    deprecated_reason: str | None = None
    for line in collected:
        s = line.strip()
        if s.startswith("/**"):
            s = s[3:]
        if s.endswith("*/"):
            s = s[:-2]
        if s.startswith("*"):
            s = s[1:]
        s = s.strip()
        dep_match = _JAVADOC_DEPRECATED_RE.match(s)
        if dep_match:
            deprecated_reason = dep_match.group(1).strip()
            continue
        if _JAVADOC_TAG_RE.match(s):
            continue
        if s:
            cleaned.append(s)

    doc_text = re.sub(r"\s+", " ", " ".join(cleaned)).strip() if cleaned else ""
    return doc_text, deprecated_reason


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

            # Enrich class docstring. Task 15 (§9.10, closes G9): the deprecated-
            # tag check must run even when "doc" was already populated by an
            # earlier pass -- only the doc TEXT is guarded against overwrite,
            # not the deprecated-reason capture, or a class whose doc was set
            # before this fix shipped would never pick up its @deprecated tag
            # on a later re-scout.
            if name:
                line_idx = name_to_line.get(name)
                if line_idx is not None:
                    doc, dep_reason = _extract_javadoc_comment(lines, line_idx)
                    if doc and not cls.get("doc"):
                        cls["doc"] = doc
                        enriched += 1
                    if dep_reason is not None:
                        cls["deprecated"] = True
                        if dep_reason:
                            cls["deprecated_reason"] = dep_reason

            # Enrich method docstrings
            for md in cls.get("methods", []):
                already_documented = bool(md.get("doc"))
                mname = md.get("name", "")
                if not mname:
                    continue
                # Prefer the method's own line number to avoid cross-overload
                # doc leaking (same overload-name, different signatures).
                md_line = md.get("line")
                if md_line is not None:
                    idx = md_line - 1  # 1-based → 0-based
                    if 0 <= idx < len(lines):
                        doc, dep_reason = _extract_javadoc_comment(lines, idx)
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
                # would also skip the deprecated-tag capture, the same bug
                # shape the md_line branch above was fixed for.
                for ml in method_lines.get(mname, []):
                    doc, dep_reason = _extract_javadoc_comment(lines, ml)
                    if not doc and dep_reason is None:
                        continue  # this candidate line has no javadoc block at all
                    if dep_reason is not None:
                        md["deprecated"] = True
                        if dep_reason:
                            md["deprecated_reason"] = dep_reason
                    if doc and not already_documented:
                        md["doc"] = doc
                        enriched += 1
                    break

    return enriched
