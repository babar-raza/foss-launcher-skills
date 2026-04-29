#!/usr/bin/env python3
"""
Canonical plugin_platform value linter for products.aspose.org.

Checks every content/products.aspose.org/**/_index.md file and verifies
that the `plugin_platform` frontmatter field contains one of the allowed
canonical values defined in AGENTS.md Section 3b.

Exit code: 1 if any violations found, 0 if clean.
"""
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML not installed — run: pip install pyyaml", file=sys.stderr)
    sys.exit(2)

# Canonical values from AGENTS.md Section 3b.
# Update this set when a new platform is added to the repo.
CANONICAL_PLUGIN_PLATFORMS = {".NET", "Python", "Java", "C++", "TypeScript"}

PRODUCTS_ROOT = Path(__file__).resolve().parents[3] / "content" / "products.aspose.org"


def check_file(path: Path) -> list[str]:
    """Return a list of violation strings for the given file, empty if clean."""
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return []  # No frontmatter — skip

    end = text.find("\n---", 3)
    if end == -1:
        return []  # Malformed frontmatter — skip (other checkers handle this)

    fm_text = text[3:end]
    try:
        fm = yaml.safe_load(fm_text)
    except yaml.YAMLError:
        return []  # Malformed YAML — skip

    if not isinstance(fm, dict):
        return []

    platform = fm.get("plugin_platform")
    if platform is None:
        return []  # Field absent — not this checker's concern

    if platform not in CANONICAL_PLUGIN_PLATFORMS:
        rel = path.relative_to(PRODUCTS_ROOT.parent.parent)
        return [
            f"FAIL {rel}: plugin_platform={platform!r} "
            f"(allowed: {sorted(CANONICAL_PLUGIN_PLATFORMS)})"
        ]
    return []


def main() -> int:
    if not PRODUCTS_ROOT.exists():
        print(f"ERROR: products root not found: {PRODUCTS_ROOT}", file=sys.stderr)
        return 2

    violations: list[str] = []
    for index_md in sorted(PRODUCTS_ROOT.rglob("_index.md")):
        violations.extend(check_file(index_md))

    if violations:
        for v in violations:
            print(v)
        print(f"\n{len(violations)} violation(s) found.", file=sys.stderr)
        return 1

    print(f"OK — all plugin_platform values are canonical.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
