"""Validate markdown frontmatter structure.

Standalone-compatible subset of the aspose.org frontmatter gate. It detects:

- duplicate frontmatter blocks;
- duplicate YAML keys before PyYAML collapses them;
- malformed YAML;
- blog post evidence/draft requirements.
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path

import yaml


_FIRST_FM_RE = re.compile(r"^---\s*\n(.*?)\n---\s*(?:\n|$)", re.DOTALL)
_BLOG_ROOT_MARKER = "content/blog.aspose.org/"
_LANG_SUFFIX_RE = re.compile(r"\.[a-z]{2}(-[a-zA-Z]{2,4})?$", re.IGNORECASE)


@dataclass
class FrontmatterFinding:
    path: str
    check: str
    line: int
    detail: str
    severity: str = "error"

    def __str__(self) -> str:
        return f"{self.severity.upper()}: {self.path}:{self.line}: [{self.check}] {self.detail}"


def extract_frontmatter(text: str) -> str | None:
    match = _FIRST_FM_RE.match(text)
    return match.group(1).strip() if match else None


def check_double_frontmatter(text: str, path: str) -> list[FrontmatterFinding]:
    match = _FIRST_FM_RE.match(text)
    if not match:
        return []
    remainder = text[match.end() :]
    if not re.match(r"^\s*---\s*\n", remainder):
        return []
    line_no = text[: match.end()].count("\n") + 1
    return [
        FrontmatterFinding(
            path=path,
            check="double_frontmatter",
            line=line_no,
            detail="second frontmatter block found; Hugo reads only the first block",
        )
    ]


def _walk_duplicate_keys(node: yaml.Node, path: str, findings: list[FrontmatterFinding]) -> None:
    if isinstance(node, yaml.MappingNode):
        seen: dict[str, int] = {}
        for key_node, value_node in node.value:
            key = str(key_node.value)
            line = key_node.start_mark.line + 1
            if key in seen:
                findings.append(
                    FrontmatterFinding(
                        path=path,
                        check="duplicate_key",
                        line=line,
                        detail=f"duplicate key '{key}' (first seen at line {seen[key]})",
                    )
                )
            else:
                seen[key] = line
            _walk_duplicate_keys(value_node, path, findings)
    elif isinstance(node, yaml.SequenceNode):
        for item in node.value:
            _walk_duplicate_keys(item, path, findings)


def check_duplicate_keys(frontmatter: str, path: str) -> list[FrontmatterFinding]:
    findings: list[FrontmatterFinding] = []
    try:
        node = yaml.compose(frontmatter)
    except yaml.YAMLError as exc:
        return [
            FrontmatterFinding(
                path=path,
                check="yaml_parse",
                line=getattr(getattr(exc, "problem_mark", None), "line", 0) + 1,
                detail=str(exc).splitlines()[0],
            )
        ]
    if node is not None:
        _walk_duplicate_keys(node, path, findings)
    return findings


def is_blog_content_file(path: Path) -> bool:
    path_str = str(path).replace("\\", "/")
    if _BLOG_ROOT_MARKER not in path_str:
        return False
    if len(path.suffixes) > 1 and _LANG_SUFFIX_RE.search(path.suffixes[-2]):
        return False
    rel = path_str.split(_BLOG_ROOT_MARKER, 1)[1]
    parts = [part for part in rel.split("/") if part]
    min_depth = 4 if path.name == "index.md" else 3
    return len(parts) >= min_depth


def check_blog_evidence(frontmatter: str | None, path: Path) -> list[FrontmatterFinding]:
    if not is_blog_content_file(path) or frontmatter is None:
        return []
    findings: list[FrontmatterFinding] = []
    try:
        data = yaml.safe_load(frontmatter) or {}
    except yaml.YAMLError:
        return findings
    if not isinstance(data, dict):
        return findings
    path_str = str(path).replace("\\", "/")
    if "draft" not in data:
        findings.append(FrontmatterFinding(path_str, "blog_evidence", 1, "blog post missing `draft` field"))
    provenance = data.get("provenance") or {}
    if isinstance(provenance, dict) and provenance.get("content_origin") == "manual-remediation":
        return findings
    evidence = data.get("evidence")
    if not isinstance(evidence, dict):
        findings.append(FrontmatterFinding(path_str, "blog_evidence", 1, "blog post missing `evidence:` block"))
        return findings
    if not evidence.get("claims"):
        findings.append(FrontmatterFinding(path_str, "blog_evidence", 1, "blog post evidence.claims is empty"))
    if not evidence.get("apis"):
        findings.append(FrontmatterFinding(path_str, "blog_evidence", 1, "blog post evidence.apis is empty"))
    return findings


def validate_text(text: str, path: str | Path) -> list[FrontmatterFinding]:
    path_obj = Path(path)
    path_str = str(path_obj).replace("\\", "/")
    findings = check_double_frontmatter(text, path_str)
    frontmatter = extract_frontmatter(text)
    if frontmatter:
        findings.extend(check_duplicate_keys(frontmatter, path_str))
    findings.extend(check_blog_evidence(frontmatter, path_obj))
    return findings


def iter_markdown(paths: list[str]) -> list[Path]:
    selected: list[Path] = []
    for raw in paths or ["content"]:
        path = Path(raw)
        if path.is_dir():
            selected.extend(sorted(path.rglob("*.md")))
        elif path.is_file() and path.suffix == ".md":
            selected.append(path)
    return selected


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate markdown frontmatter.")
    parser.add_argument("paths", nargs="*")
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args(argv)

    findings: list[FrontmatterFinding] = []
    for path in iter_markdown(args.paths):
        findings.extend(validate_text(path.read_text(encoding="utf-8", errors="replace"), path))

    if args.as_json:
        print(json.dumps([asdict(finding) for finding in findings], indent=2))
    else:
        for finding in findings:
            print(finding)
        if not findings:
            print("PASS: frontmatter validation")
    return 1 if any(finding.severity == "error" for finding in findings) else 0


if __name__ == "__main__":
    raise SystemExit(main())
