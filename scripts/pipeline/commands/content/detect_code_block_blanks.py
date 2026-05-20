#!/usr/bin/env python3
# Adapted from aspose.org
"""detect_code_block_blanks.py — Diagnostic scanner for spurious blank lines
inside YAML-embedded fenced code blocks in products.aspose.org pages.

Scans content/products/ for layout:plugin pages and detects blank
lines immediately after opening code fences or immediately before closing code
fences inside YAML frontmatter string fields.

Usage
-----
    python scripts/pipeline/commands/content/detect_code_block_blanks.py
    python scripts/pipeline/commands/content/detect_code_block_blanks.py \\
        --path content/products/ \\
        --output reports/code-snippet-spacing-plan-repair-20260515/affected-pages.json

Exit codes
----------
    0 — Scan complete (even if findings exist)
    1 — Internal error
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import yaml



def _resolve_repo_root() -> Path:
    """Return the repo root via $CONTENT_REPO_PATH or config_loader."""
    import os as _os
    env = _os.environ.get("CONTENT_REPO_PATH")
    if env:
        return Path(env).resolve()
    try:
        return resolve_content_repo()
    except Exception:
        return _HERE.parents[3]

_REPO_ROOT = _resolve_repo_root()
_DEFAULT_PATH = _REPO_ROOT / "content" / "products"

# Fields to scan (key_path -> how to extract from parsed frontmatter)
_FENCE_RE = re.compile(r"^\s*```(\w*)")
_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def _walk_all_strings(obj: object, path: str = "") -> list[tuple[str, str]]:
    """Recursively yield (key_path, value) for every string in a YAML object.

    Replaces the prior targeted-field list to ensure no code-bearing field is
    missed if the product page schema evolves.  All findings are still severity-
    stratified by locale (EN → ERROR, other → WARN) in the caller.
    """
    results: list[tuple[str, str]] = []
    if isinstance(obj, str):
        results.append((path, obj))
    elif isinstance(obj, dict):
        for k, v in obj.items():
            child_path = f"{path}.{k}" if path else k
            results.extend(_walk_all_strings(v, child_path))
    elif isinstance(obj, list):
        for idx, v in enumerate(obj):
            results.extend(_walk_all_strings(v, f"{path}[{idx}]"))
    return results


def _extract_yaml_string_fields(fm: dict) -> list[tuple[str, str]]:
    """Return (key_path, value) pairs for all string fields in the frontmatter.

    Uses recursive walking (_walk_all_strings) so that code blocks in any YAML
    string field are detected, regardless of schema layout.
    """
    return _walk_all_strings(fm)


def _scan_code_fences(
    text: str,
    key_path: str,
    filepath: Path,
    locale: str,
) -> list[dict]:
    """Scan a single string value for blank-line fence boundary defects."""
    findings: list[dict] = []
    lines = text.splitlines()
    n = len(lines)
    i = 0
    while i < n:
        m = _FENCE_RE.match(lines[i])
        if m and lines[i].strip().startswith("```") and len(lines[i].strip()) >= 3:
            lang = m.group(1)
            # Look for matching closing fence
            j = i + 1
            code_lines: list[str] = []
            while j < n:
                stripped_j = lines[j].strip()
                if stripped_j == "```" or stripped_j.startswith("```") and len(stripped_j) == 3:
                    # Closing fence
                    break
                code_lines.append(lines[j])
                j += 1
            closing_idx = j  # may equal n if no closing fence found

            # Count non-empty code lines
            non_empty_code = [ln for ln in code_lines if ln.strip()]

            # Check blank line immediately after opening fence
            if code_lines and code_lines[0].strip() == "":
                severity = "ERROR" if locale == "en" else "WARN"
                findings.append({
                    "file": str(filepath),
                    "locale": locale,
                    "family_platform": _derive_family_platform(filepath),
                    "key_path": key_path,
                    "fence_language": lang or "unknown",
                    "defect_type": "BLANK_AFTER_OPENING_FENCE",
                    "severity": severity,
                    "field_line_approx": i + 1,
                    "snippet": f"[opening fence] -> [BLANK] -> [{code_lines[1].strip()[:40] if len(code_lines) > 1 else ''}...]",
                    "non_empty_code_lines": len(non_empty_code),
                })

            # Check blank line immediately before closing fence
            if code_lines and code_lines[-1].strip() == "":
                severity = "ERROR" if locale == "en" else "WARN"
                findings.append({
                    "file": str(filepath),
                    "locale": locale,
                    "family_platform": _derive_family_platform(filepath),
                    "key_path": key_path,
                    "fence_language": lang or "unknown",
                    "defect_type": "BLANK_BEFORE_CLOSING_FENCE",
                    "severity": severity,
                    "field_line_approx": closing_idx,
                    "snippet": f"[...{code_lines[-2].strip()[:40] if len(code_lines) > 1 else ''}] -> [BLANK] -> [closing fence]",
                    "non_empty_code_lines": len(non_empty_code),
                })

            # For short snippets (<=8 non-empty code lines), flag internal blank lines
            if len(non_empty_code) <= 8:
                for k, line in enumerate(code_lines):
                    if line.strip() == "" and k > 0 and k < len(code_lines) - 1:
                        # Already flagged edges above; only flag internal blanks here
                        prev_nonempty = any(code_lines[p].strip() for p in range(k))
                        next_nonempty = any(code_lines[p].strip() for p in range(k + 1, len(code_lines)))
                        if prev_nonempty and next_nonempty:
                            severity = "ERROR" if locale == "en" else "WARN"
                            findings.append({
                                "file": str(filepath),
                                "locale": locale,
                                "family_platform": _derive_family_platform(filepath),
                                "key_path": key_path,
                                "fence_language": lang or "unknown",
                                "defect_type": "INTERNAL_BLANK_IN_SHORT_SNIPPET",
                                "severity": severity,
                                "field_line_approx": i + 1 + k,
                                "snippet": f"short snippet ({len(non_empty_code)} code lines) has internal blank near field line {i+1+k}",
                                "non_empty_code_lines": len(non_empty_code),
                            })
                            break  # one finding per fence for internal blanks

            i = closing_idx + 1
        else:
            i += 1
    return findings


def _derive_family_platform(filepath: Path) -> str:
    """Try to derive family/platform from path like .../en/words/python/_index.md."""
    parts = filepath.parts
    try:
        # Find 'products.aspose.org' in path
        idx = next(i for i, p in enumerate(parts) if "products" in p)
        # parts after: locale/family/platform/_index.md
        after = parts[idx + 1:]
        if len(after) >= 3:
            return f"{after[1]}/{after[2]}"
        elif len(after) >= 2:
            return after[1]
    except StopIteration:
        pass
    return "unknown"


def _derive_locale(filepath: Path) -> str:
    """Try to derive locale from path."""
    parts = filepath.parts
    try:
        idx = next(i for i, p in enumerate(parts) if "products" in p)
        after = parts[idx + 1:]
        if after:
            return after[0]
    except StopIteration:
        pass
    return "unknown"


def scan_file(filepath: Path) -> list[dict]:
    """Scan a single markdown file for code-block blank-line defects."""
    try:
        raw = filepath.read_text(encoding="utf-8")
    except Exception as exc:
        return [{"file": str(filepath), "error": str(exc)}]

    m = _FRONTMATTER_RE.match(raw)
    if not m:
        return []

    try:
        fm = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError:
        return []

    if not isinstance(fm, dict) or fm.get("layout") != "plugin":
        return []

    locale = _derive_locale(filepath)
    fields = _extract_yaml_string_fields(fm)
    findings: list[dict] = []
    for key_path, value in fields:
        findings.extend(_scan_code_fences(value, key_path, filepath, locale))
    return findings


def scan_directory(root: Path) -> list[dict]:
    """Scan all _index.md files under root."""
    findings: list[dict] = []
    for md_file in sorted(root.rglob("_index.md")):
        findings.extend(scan_file(md_file))
    return findings


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Detect spurious blank lines in YAML-embedded code fences."
    )
    p.add_argument(
        "--path",
        type=Path,
        default=_DEFAULT_PATH,
        help="Root directory to scan (default: content/products/)",
    )
    p.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Write JSON findings to this file.",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    root = args.path.resolve() if not args.path.is_absolute() else args.path
    if not root.is_absolute():
        root = (_REPO_ROOT / args.path).resolve()

    print(f"Scanning: {root}")
    findings = scan_directory(root)

    # Summary stats
    error_findings = [f for f in findings if f.get("severity") == "ERROR"]
    warn_findings = [f for f in findings if f.get("severity") == "WARN"]
    info_findings = [f for f in findings if f.get("severity") == "INFO"]
    affected_files = sorted({f["file"] for f in findings if "error" not in f})

    print(f"\n=== Code-Block Blank-Line Scan Results ===")
    print(f"Total findings: {len(findings)}")
    print(f"  ERROR:  {len(error_findings)}")
    print(f"  WARN:   {len(warn_findings)}")
    print(f"  INFO:   {len(info_findings)}")
    print(f"Affected files: {len(affected_files)}")
    print()

    # Group by file
    from collections import defaultdict
    by_file: dict[str, list[dict]] = defaultdict(list)
    for f in findings:
        by_file[f["file"]].append(f)

    for fpath in sorted(by_file.keys()):
        file_findings = by_file[fpath]
        errors = sum(1 for ff in file_findings if ff.get("severity") == "ERROR")
        warns = sum(1 for ff in file_findings if ff.get("severity") in ("WARN", "INFO"))
        fp = Path(fpath)
        rel = fp.relative_to(_REPO_ROOT) if fp.is_relative_to(_REPO_ROOT) else fp
        print(f"  {rel}  [{errors} ERROR, {warns} WARN/INFO]")
        for ff in file_findings:
            if ff.get("severity") in ("ERROR", "WARN"):
                print(f"    [{ff['severity']}] {ff['key_path']} — {ff['defect_type']}")

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps({"findings": findings, "affected_files": affected_files}, indent=2),
            encoding="utf-8",
        )
        print(f"\nJSON written to: {args.output}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
