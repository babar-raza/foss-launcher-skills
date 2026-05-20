#!/usr/bin/env python3
"""Temporary independent scanner for production-closure sprint.
Recursively scans ALL string fields in product page frontmatter.
Fresh implementation -- not based on committed detect_code_block_blanks.py."""
import re
import json
import sys
from pathlib import Path

import yaml

FENCE = re.compile(r"^[ \t]*```")
PRODUCTS = Path("content/products.aspose.org")


def all_strings(obj, path=""):
    if isinstance(obj, str):
        yield path, obj
    elif isinstance(obj, dict):
        for k, v in obj.items():
            yield from all_strings(v, (path + "." + k) if path else k)
    elif isinstance(obj, list):
        for idx, v in enumerate(obj):
            yield from all_strings(v, path + f"[{idx}]")


def scan_code_blocks(text, key_path, is_en):
    """Return (severity, check_id, detail) tuples for code block spacing issues."""
    findings = []
    lines = text.split("\n")
    i, n = 0, len(lines)
    while i < n:
        if FENCE.match(lines[i]):
            j = i + 1
            code = []
            while j < n:
                stripped = lines[j].strip()
                if stripped == "```" or (stripped.startswith("```") and len(stripped) == 3):
                    break
                code.append(lines[j])
                j += 1
            sev = "ERROR" if is_en else "WARN"
            if code and code[0].strip() == "":
                findings.append((sev, "BLANK_AFTER_OPEN_FENCE",
                    f"{key_path}: blank line after opening fence (source line {i + 1})"))
            if code and code[-1].strip() == "":
                findings.append((sev, "BLANK_BEFORE_CLOSE_FENCE",
                    f"{key_path}: blank line before closing fence"))
            non_empty = [ln for ln in code if ln.strip()]
            if len(non_empty) <= 8:
                for k2, line in enumerate(code):
                    if line.strip() == "" and 0 < k2 < len(code) - 1:
                        prev_ok = any(code[p].strip() for p in range(k2))
                        next_ok = any(code[p].strip() for p in range(k2 + 1, len(code)))
                        if prev_ok and next_ok:
                            findings.append((sev, "INTERNAL_BLANK_SHORT_SNIPPET",
                                f"{key_path}: short snippet ({len(non_empty)} non-empty lines)"
                                f" has internal blank near source line {i + 1 + k2}"))
                            break
            i = j + 1
        else:
            i += 1
    return findings


def scan_file(md_path):
    text = md_path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return []
    parts = text.split("---", 2)
    if len(parts) < 3:
        return []
    try:
        fm = yaml.safe_load(parts[1]) or {}
    except yaml.YAMLError as exc:
        return [{"file": str(md_path.relative_to(Path.cwd())),
                 "severity": "ERROR", "check_id": "YAML_ERR", "detail": str(exc)}]

    path_str = str(md_path).replace("\\", "/")
    is_en = ("/en/" in path_str) and ("products.aspose.org" in path_str)

    results = []
    for key_path, value in all_strings(fm):
        if "```" not in value:
            continue
        for sev, cid, detail in scan_code_blocks(value, key_path, is_en):
            results.append({
                "file": str(md_path.relative_to(Path.cwd())).replace("\\", "/"),
                "severity": sev,
                "check_id": cid,
                "detail": detail,
            })
    return results


def main():
    output_path_arg = None
    for idx, arg in enumerate(sys.argv[1:], 1):
        if arg == "--output" and idx < len(sys.argv) - 1:
            output_path_arg = sys.argv[idx + 1]

    all_findings = []
    files_scanned = 0
    for md in sorted(PRODUCTS.rglob("_index.md")):
        all_findings.extend(scan_file(md))
        files_scanned += 1

    en_errors = [f for f in all_findings if f["severity"] == "ERROR"]
    locale_warns = [f for f in all_findings if f["severity"] == "WARN"]

    report = {
        "scanner": "closure_independent_scan_runner.py (fresh, not committed detector)",
        "files_scanned": files_scanned,
        "total_findings": len(all_findings),
        "en_errors": len(en_errors),
        "locale_warns": len(locale_warns),
        "findings": all_findings,
    }

    if output_path_arg:
        out = Path(output_path_arg)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"Report saved to {out}")

    print(f"Files scanned: {files_scanned}")
    print(f"EN errors:     {len(en_errors)}")
    print(f"Locale WARNs:  {len(locale_warns)}")
    print(f"Total:         {len(all_findings)}")
    return 1 if en_errors else 0


if __name__ == "__main__":
    sys.exit(main())
