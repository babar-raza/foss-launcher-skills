#!/usr/bin/env python3
"""
Family root display-name linter for reference/docs/kb sites.

Scans family-level _index.md files (one directory below en/) and validates:
  V-01  linkTitle must NOT exist at family root level
  V-02  title must match "{Canonical Product Name} FOSS"

Canonical product names are loaded from metrics_taxonomy.yaml.

Exit code: 0 if clean, 1 if violations found, 2 if setup error.
"""
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML not installed — run: pip install pyyaml", file=sys.stderr)
    sys.exit(2)

_REPO_ROOT = Path(__file__).resolve().parents[3]
_TAXONOMY_PATH = _REPO_ROOT / "scripts" / "pipeline" / "config" / "metrics_taxonomy.yaml"

_SITES = [
    "reference.aspose.org",
    "docs.aspose.org",
    "kb.aspose.org",
]

# Keys in taxonomy that are not real family directories.
_SKIP_KEYS = {"_all"}


def _load_taxonomy() -> dict[str, str]:
    """Return {family_slug: product_display_name} from metrics_taxonomy.yaml."""
    if not _TAXONOMY_PATH.exists():
        print(f"ERROR: taxonomy not found: {_TAXONOMY_PATH}", file=sys.stderr)
        sys.exit(2)
    with open(_TAXONOMY_PATH, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    products = data.get("products", {})
    return {k: v for k, v in products.items() if k not in _SKIP_KEYS}


def _parse_frontmatter(path: Path) -> tuple[dict | None, str | None]:
    """Parse YAML frontmatter. Return (dict, None) or (None, error_reason)."""
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return None, "missing frontmatter delimiters"
    end = text.find("\n---", 3)
    if end == -1:
        return None, "unclosed frontmatter (no closing ---)"
    try:
        fm = yaml.safe_load(text[3:end])
    except yaml.YAMLError as exc:
        return None, f"YAML parse error: {exc}"
    if not isinstance(fm, dict):
        return None, f"frontmatter is {type(fm).__name__}, expected dict"
    return fm, None


def check_file(
    path: Path, family: str, taxonomy: dict[str, str]
) -> list[str]:
    """Return violation strings for a single family _index.md."""
    violations: list[str] = []
    try:
        rel = path.relative_to(_REPO_ROOT)
    except ValueError:
        rel = path

    fm, parse_error = _parse_frontmatter(path)
    if fm is None:
        violations.append(
            f"FAIL {rel}: V-00 unparsable frontmatter — {parse_error}"
        )
        return violations

    # V-01: linkTitle must not exist at family root level
    link_title = fm.get("linkTitle")
    if link_title is not None:
        violations.append(
            f"FAIL {rel}: V-01 linkTitle={link_title!r} present "
            f"(family root must not have linkTitle — sidebar will show short name)"
        )

    # V-02: title must match "{Product} FOSS"
    title = fm.get("title", "")
    canonical = taxonomy.get(family)
    if canonical is not None:
        expected = f"{canonical} FOSS"
        if title != expected:
            violations.append(
                f"FAIL {rel}: V-02 title={title!r} "
                f"does not match expected {expected!r}"
            )
    else:
        # Family not in taxonomy — warn but don't fail
        violations.append(
            f"WARN {rel}: family {family!r} not found in taxonomy — "
            f"cannot validate title={title!r}"
        )

    return violations


def main() -> int:
    taxonomy = _load_taxonomy()

    violations: list[str] = []
    files_checked = 0

    for site in _SITES:
        en_root = _REPO_ROOT / "content" / site / "en"
        if not en_root.exists():
            continue
        for family_dir in sorted(en_root.iterdir()):
            if not family_dir.is_dir():
                continue
            index_md = family_dir / "_index.md"
            if not index_md.exists():
                continue
            family = family_dir.name
            files_checked += 1
            violations.extend(check_file(index_md, family, taxonomy))

    fails = [v for v in violations if v.startswith("FAIL")]
    warns = [v for v in violations if v.startswith("WARN")]

    if violations:
        for v in violations:
            print(v)

    if fails:
        print(
            f"\n{len(fails)} violation(s) found across {files_checked} files.",
            file=sys.stderr,
        )
        return 1

    status = "OK"
    if warns:
        status += f" (with {len(warns)} warning(s))"
    print(f"{status} — {files_checked} family root pages checked, all display names canonical.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
