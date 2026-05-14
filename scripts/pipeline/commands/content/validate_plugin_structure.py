#!/usr/bin/env python3
"""Validate layout: plugin product-page structure."""
from __future__ import annotations

import argparse
import re
from pathlib import Path

import yaml

_FRONTMATTER_RE = re.compile(r"^(---\s*\n)(.*?)(\n---\s*(?:\n|$))", re.DOTALL)
_BODY_LEAK_PATTERNS = re.compile(
    r"^(overview|content|single|faq|supportandlearning|more_formats|back_to_top):",
    re.MULTILINE,
)
_REQUIRED_TOP_KEYS = [
    "layout",
    "family_name",
    "plugin_description",
    "plugin_platform",
    "head_title",
    "head_description",
    "title",
    "description",
    "github_url",
]
_REQUIRED_SECTIONS_WITH_ENABLE = ["submenu", "overview", "content", "single"]
_DISPLAY_SECTIONS_WITH_ENABLE = ["supportandlearning", "more_formats", "back_to_top"]
_SECTIONS_WITH_CONTENT = {
    "overview": ["title", "content"],
    "content": ["block"],
    "single": ["block"],
}


class Finding:
    __slots__ = ("severity", "check_id", "message")

    def __init__(self, severity: str, check_id: str, message: str):
        self.severity = severity
        self.check_id = check_id
        self.message = message

    def __str__(self) -> str:
        return f"  {self.severity}: [{self.check_id}] {self.message}"


def _split_frontmatter(text: str) -> tuple[str, str] | None:
    match = _FRONTMATTER_RE.match(text)
    if not match:
        return None
    return match.group(2), text[match.end():]


def _is_english_page(filepath: Path) -> bool:
    parts = filepath.parts
    for index, part in enumerate(parts):
        if part == "products.aspose.org" and index + 1 < len(parts):
            return parts[index + 1] == "en"
    return False


def check_file(filepath: Path) -> list[Finding]:
    try:
        text = filepath.read_text(encoding="utf-8")
    except OSError as exc:
        return [Finding("FATAL", "READ_ERROR", str(exc))]

    split = _split_frontmatter(text)
    if split is None:
        return [Finding("FATAL", "NO_FRONTMATTER", "file has no YAML frontmatter")]
    fm_text, body = split

    try:
        fm = yaml.safe_load(fm_text) or {}
    except yaml.YAMLError as exc:
        return [Finding("FATAL", "BAD_YAML", f"YAML parse error: {exc}")]
    if fm.get("layout") != "plugin":
        return []

    findings: list[Finding] = []
    body_stripped = body.strip()
    if body_stripped:
        leaked = _BODY_LEAK_PATTERNS.findall(body_stripped)
        if leaked:
            findings.append(Finding(
                "FATAL",
                "BODY_LEAK",
                "content sections found in page body instead of frontmatter: " + ", ".join(leaked),
            ))
        else:
            findings.append(Finding("WARN", "NONEMPTY_BODY", "page body is not empty"))

    for key in _REQUIRED_TOP_KEYS:
        value = fm.get(key)
        if value is None or (isinstance(value, str) and not value.strip()):
            findings.append(Finding("FATAL", "MISSING_KEY", f"required key '{key}' is missing or empty"))

    for section_name in _REQUIRED_SECTIONS_WITH_ENABLE:
        section = fm.get(section_name)
        if section is None:
            findings.append(Finding("FATAL", "MISSING_KEY", f"required section '{section_name}' is missing"))
            continue
        if not isinstance(section, dict):
            findings.append(Finding("FATAL", "MISSING_KEY", f"'{section_name}' must be a mapping"))
            continue
        if not section.get("enable"):
            findings.append(Finding("ERROR", "MISSING_ENABLE", f"'{section_name}.enable' is not true"))

    display_severity = "ERROR" if _is_english_page(filepath) else "WARN"
    for section_name in _DISPLAY_SECTIONS_WITH_ENABLE:
        section = fm.get(section_name)
        if section is None:
            findings.append(Finding(display_severity, "MISSING_DISPLAY", f"display section '{section_name}' is missing"))
        elif isinstance(section, dict) and not section.get("enable"):
            findings.append(Finding(display_severity, "MISSING_ENABLE", f"'{section_name}.enable' is not true"))

    for section_name, sub_keys in _SECTIONS_WITH_CONTENT.items():
        section = fm.get(section_name)
        if not isinstance(section, dict):
            continue
        for sub_key in sub_keys:
            value = section.get(sub_key)
            if value is None:
                findings.append(Finding("WARN", "EMPTY_SECTION", f"'{section_name}.{sub_key}' is missing"))
            elif isinstance(value, list) and not value:
                findings.append(Finding("WARN", "EMPTY_SECTION", f"'{section_name}.{sub_key}' is an empty list"))
            elif isinstance(value, str) and not value.strip():
                findings.append(Finding("WARN", "EMPTY_SECTION", f"'{section_name}.{sub_key}' is empty"))

    provenance_severity = "FATAL" if _is_english_page(filepath) else "WARN"
    if "provenance" not in fm:
        findings.append(Finding(provenance_severity, "MISSING_KEY", "required key 'provenance' is missing"))
    if "evidence" not in fm:
        findings.append(Finding(provenance_severity, "MISSING_KEY", "required key 'evidence' is missing"))
    return findings


def _collect_files(targets: list[Path]) -> list[Path]:
    files: list[Path] = []
    for target in targets:
        if target.is_file():
            files.append(target)
        elif target.is_dir():
            files.extend(sorted(target.rglob("_index.md")))
    return files


def validate_paths(targets: list[Path], strict: bool = False) -> int:
    fatal = error = warn = checked = 0
    for filepath in _collect_files(targets):
        findings = check_file(filepath)
        if findings:
            print(filepath)
        checked += 1
        for finding in findings:
            print(finding)
            if finding.severity == "FATAL":
                fatal += 1
            elif finding.severity == "ERROR":
                error += 1
            elif finding.severity == "WARN":
                warn += 1
    print(f"\nvalidate_plugin_structure: checked={checked} fatal={fatal} error={error} warn={warn}")
    if fatal or error:
        return 1
    if strict and warn:
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--files", nargs="+")
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--content-root", default="content/products.aspose.org")
    args = parser.parse_args(argv)
    targets = [Path(item) for item in args.files] if args.files else [Path(args.content_root)]
    return validate_paths(targets, strict=args.strict)


if __name__ == "__main__":
    raise SystemExit(main())
