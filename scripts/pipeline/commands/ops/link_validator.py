#!/usr/bin/env python3
"""Validate cross-subdomain Aspose links against a local content root."""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[4]
REPO_ROOT = DEFAULT_REPO_ROOT
CONTENT_ROOT = REPO_ROOT / "content"

KNOWN_SUBDOMAINS = {
    "blog.aspose.org",
    "docs.aspose.org",
    "kb.aspose.org",
    "products.aspose.org",
    "reference.aspose.org",
}
_LINK_RE = re.compile(
    r"\[[^\]]*\]\((https?://(?:" + "|".join(re.escape(item) for item in KNOWN_SUBDOMAINS) + r")[^)]*)\)"
    r"|<(https?://(?:" + "|".join(re.escape(item) for item in KNOWN_SUBDOMAINS) + r")[^>]*)>",
    re.IGNORECASE,
)
_URL_RE = re.compile(r"https?://([\w.-]+\.aspose\.org)(/?[^)>\s#?]*)", re.IGNORECASE)


@dataclass(frozen=True)
class LinkFinding:
    level: str
    source_file: str
    url: str
    subdomain: str
    slug: str
    message: str


def configure(*, repo_root: Path | str | None = None, content_root: Path | str | None = None) -> None:
    global REPO_ROOT, CONTENT_ROOT
    REPO_ROOT = Path(repo_root) if repo_root is not None else DEFAULT_REPO_ROOT
    CONTENT_ROOT = Path(content_root) if content_root is not None else REPO_ROOT / "content"


def _slug_for(subdomain_path: str) -> str | None:
    if subdomain_path.endswith("/_index.md"):
        slug = "/" + subdomain_path[: -len("/_index.md")] + "/"
    elif subdomain_path.endswith("/index.md"):
        slug = "/" + subdomain_path[: -len("/index.md")] + "/"
    elif subdomain_path.endswith(".md"):
        slug = "/" + subdomain_path[:-3] + "/"
    else:
        return None
    if slug.lower().startswith("/en/"):
        slug = slug[3:]
    return slug.lower()


def build_slug_index(content_root: Path = CONTENT_ROOT) -> dict[str, set[str]]:
    index = {subdomain: set() for subdomain in KNOWN_SUBDOMAINS}
    if not content_root.exists():
        return index
    for path in content_root.rglob("*.md"):
        rel = path.relative_to(content_root).as_posix()
        parts = rel.split("/", 1)
        if len(parts) != 2 or parts[0] not in KNOWN_SUBDOMAINS:
            continue
        slug = _slug_for(parts[1])
        if slug:
            index[parts[0]].add(slug)
            index[parts[0]].add(slug.rstrip("/"))
    for subdomain in KNOWN_SUBDOMAINS:
        root = content_root / subdomain
        if not root.exists():
            continue
        for directory in root.rglob("*"):
            if directory.is_dir():
                slug = "/" + directory.relative_to(root).as_posix() + "/"
                if slug.lower().startswith("/en/"):
                    slug = slug[3:]
                index[subdomain].add(slug.lower())
                index[subdomain].add(slug.lower().rstrip("/"))
    return index


def extract_links(filepath: Path) -> list[tuple[str, str, str]]:
    text = filepath.read_text(encoding="utf-8", errors="ignore")
    result: list[tuple[str, str, str]] = []
    for match in _LINK_RE.finditer(text):
        url = match.group(1) or match.group(2)
        parsed = _URL_RE.match(url or "")
        if parsed:
            result.append((url, parsed.group(1).lower(), parsed.group(2)))
    return result


def validate_files(files: list[Path], slug_index: dict[str, set[str]], *, repo_root: Path = REPO_ROOT) -> list[LinkFinding]:
    findings: list[LinkFinding] = []
    for filepath in files:
        for url, subdomain, path in extract_links(filepath):
            clean_path = re.split(r"[?#]", path)[0].rstrip("/") or "/"
            known = slug_index.get(subdomain, set())
            if clean_path.lower() not in known and f"{clean_path.lower()}/" not in known:
                try:
                    source = str(filepath.relative_to(repo_root))
                except ValueError:
                    source = str(filepath)
                findings.append(LinkFinding("BROKEN", source, url, subdomain, clean_path, f"Link target not found: {subdomain}{clean_path}"))
    return findings


def discover_files(family: str, platform: str, content_root: Path = CONTENT_ROOT) -> list[Path]:
    files: list[Path] = []
    if not content_root.exists():
        return files
    for site_dir in content_root.iterdir():
        candidate = site_dir / "en" / family / platform
        if candidate.exists():
            files.extend(candidate.rglob("*.md"))
    return files


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", nargs="?")
    parser.add_argument("platform", nargs="?")
    parser.add_argument("--files", nargs="+")
    parser.add_argument("--content-root")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    content_root = Path(args.content_root) if args.content_root else CONTENT_ROOT
    if args.files:
        files = [Path(item).resolve() for item in args.files if Path(item).exists()]
    elif args.target == "all":
        files = list(content_root.rglob("*.md"))
    elif args.target and args.platform:
        files = discover_files(args.target, args.platform, content_root)
    else:
        parser.print_help()
        return 1
    findings = validate_files(files, build_slug_index(content_root), repo_root=REPO_ROOT)
    if args.json:
        print(json.dumps({"files_scanned": len(files), "broken": len(findings), "findings": [asdict(item) for item in findings]}, indent=2))
    elif findings:
        print(f"Link validation: {len(findings)} BROKEN link(s) found")
    else:
        print(f"Link validation: OK - no broken cross-subdomain links in {len(files)} file(s).")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
