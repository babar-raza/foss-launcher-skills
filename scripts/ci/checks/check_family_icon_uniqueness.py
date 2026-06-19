#!/usr/bin/env python3
"""
Family icon uniqueness and consistency linter for reference/docs/kb sites.

Single source of truth: data/family_icons.yaml
  - Maps family slug → icon name (e.g. pdf: document-report)

Validates:
  V-I-01  Every family slug in taxonomy must have an entry in data/family_icons.yaml
  V-I-02  Every icon value must exist as a key in themes/docs/data/icons.yaml
  V-I-03  All icon values must be globally unique (no two families share an icon)
  V-I-04  Family-level _index.md files must have icon: that MATCHES data/family_icons.yaml

On any FAIL: prints sorted list of currently unused valid icon names as suggestions,
so the operator can immediately choose an available icon for a new family.

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
_FAMILY_ICONS_PATH = _REPO_ROOT / "data" / "family_icons.yaml"
_ICONS_YAML_PATH = _REPO_ROOT / "themes" / "docs" / "data" / "icons.yaml"
_TAXONOMY_PATH = _REPO_ROOT / "scripts" / "pipeline" / "config" / "metrics_taxonomy.yaml"

_SITES = [
    "reference.aspose.org",
    "docs.aspose.org",
    "kb.aspose.org",
]

_SKIP_KEYS = {"_all"}


def _load_family_icons() -> dict[str, str]:
    """Return {family_slug: icon_name} from data/family_icons.yaml."""
    if not _FAMILY_ICONS_PATH.exists():
        print(
            f"ERROR: data/family_icons.yaml not found: {_FAMILY_ICONS_PATH}",
            file=sys.stderr,
        )
        sys.exit(2)
    with open(_FAMILY_ICONS_PATH, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        print(
            f"ERROR: data/family_icons.yaml must be a YAML mapping, got {type(data).__name__}",
            file=sys.stderr,
        )
        sys.exit(2)
    return {k: v for k, v in data.items() if k not in _SKIP_KEYS}


def _load_icon_names() -> set[str]:
    """Return set of valid icon names from themes/docs/data/icons.yaml."""
    if not _ICONS_YAML_PATH.exists():
        print(
            f"ERROR: icons.yaml not found: {_ICONS_YAML_PATH}",
            file=sys.stderr,
        )
        sys.exit(2)
    with open(_ICONS_YAML_PATH, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        print(
            f"ERROR: icons.yaml must be a YAML mapping, got {type(data).__name__}",
            file=sys.stderr,
        )
        sys.exit(2)
    return set(data.keys())


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


def _print_unused_suggestions(family_icons: dict[str, str], icon_names: set[str]) -> None:
    """Print sorted list of icon names not currently used by any family."""
    used = set(family_icons.values())
    unused = sorted(icon_names - used)
    print(
        f"\nAvailable unused icons ({len(unused)} of {len(icon_names)} total):\n"
        + "  " + ", ".join(unused[:30])
        + (" ..." if len(unused) > 30 else "")
    )
    print(
        "\nTo assign an icon to a new family: add an entry to data/family_icons.yaml,\n"
        "then set the matching icon: value in the family _index.md files (docs/reference/kb)."
    )


def main() -> int:
    family_icons = _load_family_icons()
    icon_names = _load_icon_names()
    taxonomy = _load_taxonomy()

    violations: list[str] = []
    has_fail = False

    # Collect family slugs that are resident in content (have a family _index.md
    # under at least one of docs/reference/kb). These are the families that need icons.
    content_families: set[str] = set()
    for site in _SITES:
        en_root = _REPO_ROOT / "content" / site / "en"
        if not en_root.exists():
            continue
        for family_dir in en_root.iterdir():
            if family_dir.is_dir() and (family_dir / "_index.md").exists():
                content_families.add(family_dir.name)

    # V-I-01: every content-resident family must have an entry in family_icons.yaml
    for slug in sorted(content_families):
        if slug not in family_icons:
            violations.append(
                f"FAIL V-I-01: family '{slug}' has content in docs/reference/kb but no entry in "
                f"data/family_icons.yaml — add '{slug}: <icon>' to assign an icon"
            )
            has_fail = True

    # V-I-02: every icon value in family_icons.yaml must exist in icons.yaml
    for slug, icon in sorted(family_icons.items()):
        if icon not in icon_names:
            violations.append(
                f"FAIL V-I-02: family '{slug}' has icon '{icon}' which is not a valid "
                f"key in themes/docs/data/icons.yaml"
            )
            has_fail = True

    # V-I-03: all icon values must be unique (no two families share one icon)
    values = list(family_icons.values())
    seen_dups: set[str] = set()
    for icon in values:
        if values.count(icon) > 1 and icon not in seen_dups:
            seen_dups.add(icon)
            families_sharing = [s for s, i in family_icons.items() if i == icon]
            violations.append(
                f"FAIL V-I-03: icon '{icon}' is shared by families: "
                + ", ".join(sorted(families_sharing))
                + " — each family must have a unique icon"
            )
            has_fail = True

    # V-I-04: family _index.md frontmatter icon: must match data/family_icons.yaml
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
            if family not in family_icons:
                # V-I-01 already reports this; skip V-I-04 for unregistered families
                continue
            try:
                rel = index_md.relative_to(_REPO_ROOT)
            except ValueError:
                rel = index_md
            fm, parse_error = _parse_frontmatter(index_md)
            if fm is None:
                violations.append(
                    f"FAIL V-I-04: {rel}: unparsable frontmatter — {parse_error}"
                )
                has_fail = True
                continue
            fm_icon = fm.get("icon")
            expected_icon = family_icons[family]
            if fm_icon is None:
                violations.append(
                    f"FAIL V-I-04: {rel}: missing 'icon:' frontmatter field "
                    f"(expected '{expected_icon}' from data/family_icons.yaml)"
                )
                has_fail = True
            elif fm_icon != expected_icon:
                violations.append(
                    f"FAIL V-I-04: {rel}: icon='{fm_icon}' does not match "
                    f"data/family_icons.yaml value '{expected_icon}'"
                )
                has_fail = True

    # Print all violations
    if violations:
        for v in violations:
            print(v)
        _print_unused_suggestions(family_icons, icon_names)
        print(
            f"\n{len(violations)} violation(s) found.",
            file=sys.stderr,
        )
        return 1

    print(
        f"OK — {len(family_icons)} family icons validated: "
        f"present in registry, valid, unique, and consistent with all _index.md files."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
