# Adapted from aspose.org
"""translation_coverage.py — Measure translation coverage across all subdomains.

Usage:
    python -m translation_coverage                   # disk coverage report
    python -m translation_coverage --served          # detect unserved locale dirs
    python -m translation_coverage --fallback-detect # detect English-copy files in locale dirs
    python -m translation_coverage --products-parity # detect missing products locale files
    python -m translation_coverage --all             # all modes combined
    python -m translation_coverage --subdomain docs.aspose.org  # limit to one subdomain
    python -m translation_coverage --json-out reports/translation_coverage.json

Exit code: 0 always (coverage is advisory, not a hard gate).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

# Force UTF-8 stdout/stderr on Windows (cp1252 can't encode checkmarks etc.)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

try:
    import tomllib  # Python 3.11+
except ImportError:
    try:
        import tomli as tomllib  # type: ignore[no-redef]
    except ImportError:
        tomllib = None  # type: ignore[assignment]

import yaml  # pyyaml — already in requirements.txt

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parent.parent.parent.parent

# ---------------------------------------------------------------------------
# Canonical locale list (36 non-English)
# ---------------------------------------------------------------------------

ALL_LOCALES = [
    "ar", "bg", "ca", "cs", "da", "de", "el", "es", "fa", "fi",
    "fr", "he", "hi", "hr", "hu", "id", "it", "ja", "ko", "lt",
    "lv", "ms", "nl", "no", "pl", "pt", "ro", "ru", "sk", "sr",
    "sv", "th", "tr", "uk", "vi", "zh",
]

# ---------------------------------------------------------------------------
# Subdomain descriptors
# ---------------------------------------------------------------------------

SUBDOMAINS = {
    "docs.aspose.org": {
        "type": "contentdir",
        "config": "configs/docs.aspose.org.toml",
        "en_root": "content/docs.aspose.org/en",
        "locale_root_tpl": "content/docs.aspose.org/{locale}",
    },
    "kb.aspose.org": {
        "type": "contentdir",
        "config": "configs/kb.aspose.org.toml",
        "en_root": "content/kb.aspose.org/en",
        "locale_root_tpl": "content/kb.aspose.org/{locale}",
    },
    "products.aspose.org": {
        "type": "contentdir",
        "config": "configs/products.aspose.org.toml",
        "en_root": "content/products.aspose.org/en",
        "locale_root_tpl": "content/products.aspose.org/{locale}",
    },
    "reference.aspose.org": {
        "type": "contentdir",
        "config": "configs/reference.aspose.org.toml",
        "en_root": "content/reference.aspose.org/en",
        "locale_root_tpl": "content/reference.aspose.org/{locale}",
    },
    "blog.aspose.org": {
        "type": "filename",
        "config": "configs/blog.aspose.org.yml",
        "content_root": "content/blog.aspose.org",
    },
}

# ---------------------------------------------------------------------------
# Config parsing
# ---------------------------------------------------------------------------

_TOML_LANG_RE = re.compile(r"^\[languages\.(\w+)\]", re.MULTILINE)


def load_declared_locales(subdomain: str, repo_root: Path) -> set[str]:
    """Return the set of non-English locale codes declared in the Hugo config."""
    cfg = SUBDOMAINS[subdomain]
    config_path = repo_root / cfg["config"]
    if not config_path.exists():
        return set(ALL_LOCALES)

    text = config_path.read_text(encoding="utf-8")

    if config_path.suffix == ".toml":
        if tomllib is not None:
            try:
                data = tomllib.loads(text)
                langs = data.get("languages", {})
                return {k for k in langs if k != "en"}
            except Exception:
                pass
        # Fallback: regex scan for [languages.xx] blocks
        return {m.group(1) for m in _TOML_LANG_RE.finditer(text) if m.group(1) != "en"}

    else:  # YAML (.yml)
        try:
            data = yaml.safe_load(text) or {}
            langs = data.get("languages", {}) or {}
            return {k for k in langs if k != "en"}
        except yaml.YAMLError:
            return set(ALL_LOCALES)


# ---------------------------------------------------------------------------
# Frontmatter field extraction (fast regex, no full YAML parse)
# ---------------------------------------------------------------------------

try:
    from core.markdown import _FRONTMATTER_READER_RE as _FRONTMATTER_RE
except ImportError:
    import re as _re_mod
    _FRONTMATTER_RE = _re_mod.compile(r"^---\s*
(.*?)
---\s*(?:
|$)", _re_mod.DOTALL)
_TITLE_RE = re.compile(r"^title:\s*['\"]?(.*?)['\"]?\s*$", re.MULTILINE)
_DESC_RE = re.compile(r"^description:\s*['\"]?(.*?)['\"]?\s*$", re.MULTILINE)


def _read_frontmatter_fields(path: Path) -> dict[str, str]:
    """Return {title, description} from frontmatter. Empty strings if not found."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {"title": "", "description": ""}
    m = _FRONTMATTER_RE.match(text)
    fm = m.group(1) if m else text[:2000]
    t = _TITLE_RE.search(fm)
    d = _DESC_RE.search(fm)
    return {
        "title": t.group(1).strip() if t else "",
        "description": d.group(1).strip() if d else "",
    }


# ---------------------------------------------------------------------------
# Coverage scanning
# ---------------------------------------------------------------------------

def _iter_en_files(en_root: Path) -> Iterator[Path]:
    if not en_root.exists():
        return
    for p in en_root.rglob("*.md"):
        yield p


def scan_contentdir(subdomain: str, repo_root: Path) -> dict:
    """Scan a contentDir-based subdomain."""
    cfg = SUBDOMAINS[subdomain]
    en_root = repo_root / cfg["en_root"]
    locale_tpl = cfg["locale_root_tpl"]

    en_files = list(_iter_en_files(en_root))
    en_count = len(en_files)
    if en_count == 0:
        return {"subdomain": subdomain, "en_count": 0, "locale_coverage": {}, "per_file": {}}

    per_file: dict[str, set[str]] = {}
    for f in en_files:
        rel = f.relative_to(en_root).as_posix()
        per_file[rel] = set()

    locale_coverage: dict[str, int] = {}
    for locale in ALL_LOCALES:
        loc_root = repo_root / locale_tpl.format(locale=locale)
        count = 0
        for rel in per_file:
            if (loc_root / rel).exists():
                per_file[rel].add(locale)
                count += 1
        locale_coverage[locale] = count

    family_platform: dict[str, dict] = defaultdict(lambda: {"en": 0, "locales": defaultdict(int)})
    for rel in per_file:
        parts = rel.split("/")
        key = f"{parts[0]}/{parts[1]}" if len(parts) >= 2 else parts[0]
        family_platform[key]["en"] += 1
        for loc in per_file[rel]:
            family_platform[key]["locales"][loc] += 1

    return {
        "subdomain": subdomain,
        "en_count": en_count,
        "locale_coverage": locale_coverage,
        "per_file": {k: sorted(v) for k, v in per_file.items()},
        "family_platform": {k: {"en": v["en"], "locales": dict(v["locales"])}
                            for k, v in family_platform.items()},
    }


def scan_blog(repo_root: Path) -> dict:
    """Scan blog subdomain (filename-based locale strategy)."""
    content_root = repo_root / "content/blog.aspose.org"
    if not content_root.exists():
        return {"subdomain": "blog.aspose.org", "en_count": 0, "locale_coverage": {}, "per_file": {}}

    en_files = [p for p in content_root.rglob("index.md")
                if not re.search(r"index\.[a-z]{2}\.md$", str(p))]

    per_file: dict[str, set[str]] = {}
    for f in en_files:
        rel = f.relative_to(content_root).as_posix()
        locales_present = set()
        for locale in ALL_LOCALES:
            if (f.parent / f"index.{locale}.md").exists():
                locales_present.add(locale)
        per_file[rel] = locales_present

    locale_coverage: dict[str, int] = {
        loc: sum(1 for v in per_file.values() if loc in v)
        for loc in ALL_LOCALES
    }

    # archive.{locale}.md at blog root
    archive_locales: set[str] = set()
    for locale in ALL_LOCALES:
        if (content_root / f"archive.{locale}.md").exists():
            archive_locales.add(locale)
    if (content_root / "archive.md").exists():
        per_file["archive.md"] = archive_locales
        for loc in archive_locales:
            locale_coverage[loc] = locale_coverage.get(loc, 0) + 1

    return {
        "subdomain": "blog.aspose.org",
        "en_count": len(per_file),
        "locale_coverage": locale_coverage,
        "per_file": {k: sorted(v) for k, v in per_file.items()},
        "family_platform": {},
    }


# ---------------------------------------------------------------------------
# --served: detect locale dirs not declared in config
# ---------------------------------------------------------------------------

def check_served_gaps(subdomain: str, repo_root: Path) -> list[dict]:
    declared = load_declared_locales(subdomain, repo_root)
    cfg = SUBDOMAINS[subdomain]
    gaps = []

    if cfg["type"] == "contentdir":
        en_root = repo_root / cfg["en_root"]
        parent = en_root.parent
        if not parent.exists():
            return []
        for child in sorted(parent.iterdir()):
            if child.is_dir() and child.name != "en" and len(child.name) == 2:
                if child.name not in declared:
                    file_count = sum(1 for _ in child.rglob("*.md"))
                    gaps.append({
                        "subdomain": subdomain,
                        "locale": child.name,
                        "dir": str(child.relative_to(repo_root)),
                        "file_count": file_count,
                    })
    else:
        content_root = repo_root / cfg["content_root"]
        if not content_root.exists():
            return []
        found_locales: set[str] = set()
        for p in content_root.rglob("index.*.md"):
            m = re.search(r"index\.([a-z]{2})\.md$", p.name)
            if m:
                found_locales.add(m.group(1))
        for p in content_root.glob("archive.*.md"):
            m = re.search(r"archive\.([a-z]{2})\.md$", p.name)
            if m:
                found_locales.add(m.group(1))
        for locale in sorted(found_locales - declared):
            gaps.append({
                "subdomain": subdomain,
                "locale": locale,
                "dir": "content/blog.aspose.org (filename-based)",
                "file_count": None,
            })

    return gaps


# ---------------------------------------------------------------------------
# --fallback-detect: find locale files matching English title+description
# ---------------------------------------------------------------------------

def detect_fallbacks(subdomain: str, repo_root: Path) -> list[dict]:
    cfg = SUBDOMAINS[subdomain]
    if cfg["type"] != "contentdir":
        return []

    en_root = repo_root / cfg["en_root"]
    locale_tpl = cfg["locale_root_tpl"]

    en_index: dict[str, dict] = {}
    for f in _iter_en_files(en_root):
        rel = f.relative_to(en_root).as_posix()
        en_index[rel] = _read_frontmatter_fields(f)

    fallbacks = []
    for locale in ALL_LOCALES:
        loc_root = repo_root / locale_tpl.format(locale=locale)
        if not loc_root.exists():
            continue
        for rel, en_fields in en_index.items():
            loc_file = loc_root / rel
            if not loc_file.exists():
                continue
            loc_fields = _read_frontmatter_fields(loc_file)
            if (en_fields["title"] and loc_fields["title"] == en_fields["title"] and
                    en_fields["description"] and loc_fields["description"] == en_fields["description"]):
                fallbacks.append({
                    "subdomain": subdomain,
                    "locale": locale,
                    "file": rel,
                    "title": en_fields["title"],
                })

    return fallbacks


# ---------------------------------------------------------------------------
# --products-parity: detect missing products locale files
# ---------------------------------------------------------------------------

def check_products_parity(repo_root: Path) -> list[dict]:
    en_root = repo_root / "content/products.aspose.org/en"
    declared = load_declared_locales("products.aspose.org", repo_root)
    gaps = []

    if not en_root.exists():
        return []

    for en_file in en_root.rglob("*.md"):
        rel = en_file.relative_to(en_root).as_posix()
        for locale in sorted(declared):
            loc_file = repo_root / f"content/products.aspose.org/{locale}/{rel}"
            if not loc_file.exists():
                gaps.append({
                    "locale": locale,
                    "file": rel,
                    "expected_path": f"content/products.aspose.org/{locale}/{rel}",
                })

    return gaps


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def _pct(n: int, total: int) -> str:
    if total == 0:
        return "N/A"
    return f"{100 * n / total:.1f}%"


def render_markdown(results: dict, gaps: dict, args: argparse.Namespace) -> str:
    lines = [
        "# Translation Coverage Report",
        f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}",
        "",
    ]

    lines.append("## Disk Coverage by Subdomain")
    lines.append("")
    lines.append("| Subdomain | EN Pages | Avg Locales Present | Coverage % |")
    lines.append("|-----------|----------|---------------------|-----------|")
    for sd, data in results.items():
        en = data["en_count"]
        if en == 0:
            lines.append(f"| {sd} | 0 | - | N/A |")
            continue
        total_locale_pages = sum(data["locale_coverage"].values())
        avg = total_locale_pages / 36
        pct = _pct(total_locale_pages, en * 36)
        lines.append(f"| {sd} | {en} | {avg:.1f} | {pct} |")
    lines.append("")

    lines.append("## Coverage by Locale (all subdomains)")
    lines.append("")
    lines.append("| Locale | Total Translated | Max Possible | Coverage % |")
    lines.append("|--------|-----------------|--------------|-----------|")
    locale_totals: dict[str, int] = defaultdict(int)
    total_en = 0
    for sd, data in results.items():
        total_en += data["en_count"]
        for loc, cnt in data["locale_coverage"].items():
            locale_totals[loc] += cnt
    for loc in ALL_LOCALES:
        cnt = locale_totals.get(loc, 0)
        lines.append(f"| {loc} | {cnt} | {total_en} | {_pct(cnt, total_en)} |")
    lines.append("")

    if args.served or args.all:
        served_gaps = gaps.get("served", [])
        lines.append("## Unserved Locale Directories")
        lines.append("")
        if served_gaps:
            lines.append("These locale directories exist on disk but are NOT declared in Hugo config:")
            lines.append("")
            lines.append("| Subdomain | Locale | Files on Disk |")
            lines.append("|-----------|--------|--------------|")
            for g in served_gaps:
                fc = g["file_count"] if g["file_count"] is not None else "?"
                lines.append(f"| {g['subdomain']} | {g['locale']} | {fc} |")
        else:
            lines.append("No unserved locale directories found.")
        lines.append("")

    if args.fallback_detect or args.all:
        fallbacks = gaps.get("fallbacks", [])
        lines.append("## Untranslated Fallback Files (English copy in locale dir)")
        lines.append("")
        if fallbacks:
            lines.append(f"Found {len(fallbacks)} files where title+description match English source:")
            lines.append("")
            lines.append("| Subdomain | Locale | File |")
            lines.append("|-----------|--------|------|")
            for f in fallbacks[:50]:
                lines.append(f"| {f['subdomain']} | {f['locale']} | {f['file']} |")
            if len(fallbacks) > 50:
                lines.append(f"| ... | ... | ({len(fallbacks) - 50} more) |")
        else:
            lines.append("No untranslated fallback files detected.")
        lines.append("")

    if args.products_parity or args.all:
        parity_gaps = gaps.get("products_parity", [])
        lines.append("## Products Parity Gaps")
        lines.append("")
        if parity_gaps:
            by_file: dict[str, list[str]] = defaultdict(list)
            for g in parity_gaps:
                by_file[g["file"]].append(g["locale"])
            lines.append(f"Found {len(parity_gaps)} missing products locale files ({len(by_file)} pages):")
            lines.append("")
            lines.append("| File | Missing Locales |")
            lines.append("|------|----------------|")
            for f, locs in sorted(by_file.items()):
                lines.append(f"| {f} | {', '.join(locs)} |")
        else:
            lines.append("All products pages present in all declared locales.")
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Measure translation coverage across all subdomains."
    )
    parser.add_argument("--subdomain", choices=list(SUBDOMAINS.keys()),
                        help="Limit scan to one subdomain")
    parser.add_argument("--served", action="store_true",
                        help="Detect locale dirs not declared in Hugo config")
    parser.add_argument("--fallback-detect", dest="fallback_detect", action="store_true",
                        help="Detect files where title+description match English source")
    parser.add_argument("--products-parity", dest="products_parity", action="store_true",
                        help="Detect products pages missing in locale dirs")
    parser.add_argument("--all", action="store_true", help="Run all modes")
    parser.add_argument("--json-out", default=None, metavar="PATH",
                        help="Write full JSON report to this path")
    args = parser.parse_args(argv)

    repo_root = _REPO_ROOT
    target_subdomains = [args.subdomain] if args.subdomain else list(SUBDOMAINS.keys())

    print(f"Scanning {len(target_subdomains)} subdomain(s)...", file=sys.stderr)

    results: dict[str, dict] = {}
    for sd in target_subdomains:
        print(f"  {sd}...", file=sys.stderr)
        if SUBDOMAINS[sd]["type"] == "filename":
            results[sd] = scan_blog(repo_root)
        else:
            results[sd] = scan_contentdir(sd, repo_root)

    gaps: dict[str, list] = {}

    if args.served or args.all:
        served_gaps = []
        for sd in target_subdomains:
            served_gaps.extend(check_served_gaps(sd, repo_root))
        gaps["served"] = served_gaps

    if args.fallback_detect or args.all:
        fallbacks = []
        for sd in target_subdomains:
            fallbacks.extend(detect_fallbacks(sd, repo_root))
        gaps["fallbacks"] = fallbacks

    if args.products_parity or args.all:
        gaps["products_parity"] = check_products_parity(repo_root)

    md = render_markdown(results, gaps, args)
    print(md)

    if args.json_out:
        out_path = repo_root / args.json_out
        out_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "subdomains": results,
            "gaps": {k: v for k, v in gaps.items()},
        }
        out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"\nJSON report written to {out_path}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
