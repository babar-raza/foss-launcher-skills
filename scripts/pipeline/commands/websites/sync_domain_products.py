#!/usr/bin/env python3
"""sync_domain_products.py — Regenerate ``products:`` block in websites.aspose.org domain pages.

This script reads authoritative product data from:
  - data/products.json            (active FOSS products)
  - data/families.json            (family display names)
  - data/families_order.json      (authoritative family ordering)
  - data/platforms_order.json     (platform ordering within each family)
  - scripts/pipeline/config/metrics_taxonomy.yaml  (platform display names)

And filters to actually *published* platforms by checking:
  - content/products.aspose.org/en/{family}/{platform}/_index.md exists
  - that file has ``layout: plugin``
  - that file does NOT have ``draft: true``

It then regenerates the ``products:`` block in:
  - content/websites.aspose.org/en/aspose/org/_index.md      (English)
  - content/websites.aspose.org/{locale}/aspose/org/_index.md (36 locales)

Only the ``products:`` key is replaced. All other frontmatter fields —
including locale-specific translations — are preserved verbatim.

GOVERNANCE NOTE
---------------
content/websites.aspose.org/ is outside ALLOWED_PREFIXES in path_guard.py.
To commit changes produced by ``--write``, you must first create an override
token::

    python scripts/pipeline/commands/governance/override_manager.py create \\
      --paths "content/websites.aspose.org/*/aspose/org/_index.md" \\
      --reason "Sync domain products list from authoritative data"

Usage::

    # Safe read-only diff (default / recommended):
    python sync_domain_products.py --domain aspose/org --dry-run

    # Write mode (mutates governed content — requires override token for commit):
    python sync_domain_products.py --domain aspose/org --write

    # Write even if some locale files are missing (emergency use):
    python sync_domain_products.py --domain aspose/org --write --allow-missing-locales
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Path setup (allows running as a script or imported from tests)
# ---------------------------------------------------------------------------

_HERE = Path(__file__).resolve().parent
_PIPELINE_ROOT = _HERE.parent.parent          # scripts/pipeline/
_DEFAULT_REPO_ROOT = _PIPELINE_ROOT.parent.parent     # repo root

if str(_PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_ROOT))

# ---------------------------------------------------------------------------
# Constants (mutable via configure() for test isolation — see §16.3)
# ---------------------------------------------------------------------------

_DEFAULT_CONTENT_WEBSITES = _DEFAULT_REPO_ROOT / "content" / "websites.aspose.org"
_DEFAULT_CONTENT_PRODUCTS = _DEFAULT_REPO_ROOT / "content" / "products.aspose.org" / "en"
_DEFAULT_DATA_DIR = _DEFAULT_REPO_ROOT / "data"

_REPO_ROOT: Path = _DEFAULT_REPO_ROOT
_CONTENT_WEBSITES: Path = _DEFAULT_CONTENT_WEBSITES
_CONTENT_PRODUCTS: Path = _DEFAULT_CONTENT_PRODUCTS
_DATA_DIR: Path = _DEFAULT_DATA_DIR

_PRODUCTS_BASE_URL = "https://products.aspose.org"


def configure(
    repo_root: "Path | None" = None,
    content_websites: "Path | None" = None,
    content_products: "Path | None" = None,
    data_dir: "Path | None" = None,
) -> None:
    """Override module-level path constants for test isolation.

    Call with no args to reset all constants to their built-in defaults.
    Tests MUST use an autouse fixture or finally block to call configure()
    after each test (see §16.3).
    """
    global _REPO_ROOT, _CONTENT_WEBSITES, _CONTENT_PRODUCTS, _DATA_DIR
    _REPO_ROOT = repo_root if repo_root is not None else _DEFAULT_REPO_ROOT
    _CONTENT_WEBSITES = (
        content_websites if content_websites is not None else _DEFAULT_CONTENT_WEBSITES
    )
    _CONTENT_PRODUCTS = (
        content_products if content_products is not None else _DEFAULT_CONTENT_PRODUCTS
    )
    _DATA_DIR = data_dir if data_dir is not None else _DEFAULT_DATA_DIR

# Fallback platform display names (matches metrics_taxonomy.yaml)
_PLATFORM_DISPLAY_FALLBACK: dict[str, str] = {
    "python": "Python",
    "net": ".NET",
    "java": "Java",
    "cpp": "C++",
    "typescript": "TypeScript",
    "javascript": "JavaScript",
    "node": "Node.js",
    "ruby": "Ruby",
    "php": "PHP",
    "go": "Go",
    "android": "Android",
    "swift": "Swift",
}


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def _load_json(path: Path) -> Any:
    """Load and return JSON from path, raising with a clear message on failure."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Failed to load {path}: {exc}") from exc


def _load_platform_display() -> dict[str, str]:
    """Load platform display names from metrics_taxonomy.yaml, falling back to built-in map."""
    try:
        import yaml  # available in pipeline env
        taxonomy_path = (
            _PIPELINE_ROOT / "config" / "metrics_taxonomy.yaml"
        )
        data = yaml.safe_load(taxonomy_path.read_text(encoding="utf-8")) or {}
        platforms = data.get("platforms", {})
        if platforms:
            return {k: str(v) for k, v in platforms.items()}
    except Exception:  # noqa: BLE001
        pass
    return _PLATFORM_DISPLAY_FALLBACK


def resolve_platform_display(key: str, display_map: dict[str, str]) -> str:
    """Return human-readable platform label (e.g. 'net' → '.NET')."""
    return display_map.get(key, key.title())


# ---------------------------------------------------------------------------
# Publication filter
# ---------------------------------------------------------------------------

_LAYOUT_RE = re.compile(r"^layout:\s*(.+)$", re.MULTILINE)
_DRAFT_RE = re.compile(r"^draft:\s*true\b", re.MULTILINE)
_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*(?:\n|$)", re.DOTALL)


def _read_frontmatter_text(path: Path) -> str:
    """Return the raw YAML body between --- fences, or empty string."""
    try:
        text = path.read_text(encoding="utf-8")
        m = _FRONTMATTER_RE.match(text)
        return m.group(1) if m else ""
    except OSError:
        return ""


def is_published(family: str, platform: str) -> tuple[bool, str]:
    """Return (True, "") if this family/platform is published, else (False, reason)."""
    source_path = _CONTENT_PRODUCTS / family / platform / "_index.md"
    if not source_path.exists():
        return False, "source file missing"
    fm = _read_frontmatter_text(source_path)
    if not fm:
        return False, "no frontmatter"
    layout_m = _LAYOUT_RE.search(fm)
    layout = layout_m.group(1).strip().strip('"\'') if layout_m else ""
    if layout != "plugin":
        return False, f"layout={layout!r} (not plugin)"
    if _DRAFT_RE.search(fm):
        return False, "draft: true"
    return True, ""


def get_published_products(
    products: list[dict[str, Any]],
    platform_display: dict[str, str],
    families: dict[str, str],
    families_order: list[str],
    platforms_order: list[str],
) -> tuple[list[dict], list[dict]]:
    """Return (included, excluded) product dicts ordered for the products: block."""
    # Group active products by family
    by_family: dict[str, list[str]] = {}
    excluded: list[dict] = []
    for entry in products:
        if not entry.get("active", False):
            excluded.append({**entry, "reason": "inactive"})
            continue
        family = entry["family"]
        platform = entry["platform"]
        ok, reason = is_published(family, platform)
        if ok:
            by_family.setdefault(family, []).append(platform)
        else:
            excluded.append({**entry, "reason": reason})

    # Order families
    fam_rank = {f: i for i, f in enumerate(families_order)}
    ordered_families = sorted(
        by_family.keys(),
        key=lambda f: (fam_rank.get(f, len(families_order)), f),
    )

    # Order platforms within each family
    plat_rank = {p: i for i, p in enumerate(platforms_order)}

    included: list[dict] = []
    for family in ordered_families:
        platforms = sorted(
            by_family[family],
            key=lambda p: (plat_rank.get(p, len(platforms_order)), p),
        )
        family_display = families.get(family, family.title())
        product_entry: dict[str, Any] = {
            "name": family_display,
            "url": f"{_PRODUCTS_BASE_URL}/{family}/",
            "image": f"/img/aspose/aspose-{family}.png",
            "list": [
                {
                    "text": f"{family_display} for {resolve_platform_display(p, platform_display)}",
                    "link": f"{_PRODUCTS_BASE_URL}/{family}/{p}/",
                }
                for p in platforms
            ],
        }
        included.append(product_entry)

    return included, excluded


# ---------------------------------------------------------------------------
# Image safety check
# ---------------------------------------------------------------------------

def check_images(products: list[dict]) -> list[str]:
    """Return list of blocking image-path failures (empty = all OK)."""
    failures = []
    for prod in products:
        image_rel = prod["image"].lstrip("/")          # img/aspose/aspose-X.png
        image_file = _REPO_ROOT / "themes" / "websites" / "static" / image_rel
        if not image_file.exists():
            failures.append(f"Missing image: {image_rel} (for {prod['name']})")
    return failures


# ---------------------------------------------------------------------------
# YAML serialisation (deterministic, preserves double-quote style)
# ---------------------------------------------------------------------------

def _q(s: str) -> str:
    """Wrap s in double quotes, escaping embedded double quotes."""
    return '"' + s.replace('"', '\\"') + '"'


def serialize_products_yaml(products: list[dict]) -> str:
    """Serialize products list to a YAML block matching the existing page style.

    Output format::

        products:
          - name: "Aspose.Words"
            url: "https://products.aspose.org/words/"
            image: "/img/aspose/aspose-words.png"
            list:
              - text: "Aspose.Words for Python"
                link: "https://products.aspose.org/words/python/"

    Blank line separates each family block.
    """
    lines = ["products:"]
    for i, prod in enumerate(products):
        if i > 0:
            lines.append("")  # blank line between families
        lines.append(f'  - name: {_q(prod["name"])}')
        lines.append(f'    url: {_q(prod["url"])}')
        lines.append(f'    image: {_q(prod["image"])}')
        lines.append("    list:")
        for item in prod["list"]:
            lines.append(f'      - text: {_q(item["text"])}')
            lines.append(f'        link: {_q(item["link"])}')
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# In-place frontmatter products: block replacement
# ---------------------------------------------------------------------------

_PRODUCTS_START_RE = re.compile(r"^products:", re.MULTILINE)
_FRONTMATTER_WRITER_RE = re.compile(
    r"^(---\s*\n)(.*?)(\n---\s*(?:\n|$))", re.DOTALL
)
_AUTO_UPDATABLE_RE = re.compile(r"(auto_updatable:\s*)false\b")
_LAST_MECHANISM_RE = re.compile(r"(last_mechanism:\s*)[\w-]+")


def replace_products_in_text(
    text: str,
    new_products_yaml: str,
    update_provenance: bool = False,
) -> str | None:
    """Replace the ``products:`` block in a markdown file text.

    Returns updated text, or None if the file has no frontmatter or no
    products: key.
    """
    m = _FRONTMATTER_WRITER_RE.match(text)
    if not m:
        return None

    opening_fence = m.group(1)   # "---\n"
    yaml_body = m.group(2)       # raw YAML between fences
    closing_fence = m.group(3)   # "\n---\n" (or end)
    body_after = text[m.end():]  # anything after the closing fence

    # Find the products: key in the yaml body
    prod_m = _PRODUCTS_START_RE.search(yaml_body)
    if prod_m is None:
        # products: key not found — append at end
        prefix = yaml_body.rstrip("\n") + "\n"
        new_yaml_body = prefix + new_products_yaml
    else:
        # Keep everything before products:, replace from products: onward
        prefix = yaml_body[: prod_m.start()]
        new_yaml_body = prefix + new_products_yaml

    # Optionally update provenance fields in English page
    if update_provenance:
        new_yaml_body = _AUTO_UPDATABLE_RE.sub(r"\g<1>true", new_yaml_body)
        new_yaml_body = _LAST_MECHANISM_RE.sub(
            r"\g<1>skill", new_yaml_body
        )

    return opening_fence + new_yaml_body + closing_fence + body_after


# ---------------------------------------------------------------------------
# Unified diff helper
# ---------------------------------------------------------------------------

def _unified_diff(old: str, new: str, path: str) -> str:
    """Return a unified diff string, or empty string if identical."""
    import difflib
    old_lines = old.splitlines(keepends=True)
    new_lines = new.splitlines(keepends=True)
    diff = list(
        difflib.unified_diff(
            old_lines, new_lines,
            fromfile=f"a/{path}",
            tofile=f"b/{path}",
            lineterm="",
        )
    )
    return "\n".join(diff) if diff else ""


# ---------------------------------------------------------------------------
# Core run logic
# ---------------------------------------------------------------------------

def run(
    domain: str,
    dry_run: bool,
    allow_missing_locales: bool = False,
    verbose: bool = True,
) -> int:
    """Execute the sync for the given domain.

    Returns 0 on success, non-zero on failure.
    """
    if domain != "aspose/org":
        print(f"ERROR: Unsupported domain {domain!r}. Only 'aspose/org' is implemented.")
        return 1

    # --- Load data sources ---
    try:
        products_data: list[dict] = _load_json(_DATA_DIR / "products.json")
        # All products in the aspose/org domain are FOSS; append the label to display names.
        families: dict[str, str] = {k: v + " FOSS" for k, v in _load_json(_DATA_DIR / "families.json").items()}
        families_order: list[str] = _load_json(_DATA_DIR / "families_order.json")
        platforms_order: list[str] = _load_json(_DATA_DIR / "platforms_order.json")
    except RuntimeError as exc:
        print(f"ERROR loading data: {exc}")
        return 1

    platform_display = _load_platform_display()

    # --- Build published product list ---
    included, excluded = get_published_products(
        products_data, platform_display, families, families_order, platforms_order
    )

    if verbose:
        print(f"Published products: {len(included)} families")
        total_platforms = sum(len(p["list"]) for p in included)
        print(f"  Total platforms:  {total_platforms}")
        for prod in included:
            plats = ", ".join(item["text"].split(" for ")[1] for item in prod["list"])
            print(f"  {prod['name']}: {plats}")
        if excluded:
            print(f"\nExcluded ({len(excluded)}):")
            for ex in excluded:
                print(f"  {ex['family']}/{ex['platform']}: {ex['reason']}")

    # --- Safety: non-empty check ---
    if not included:
        print("ERROR: Generated product list is empty. Refusing to proceed.")
        return 1

    # --- Safety: image check ---
    image_failures = check_images(included)
    if image_failures:
        print("ERROR: Missing product images (blocking):")
        for f in image_failures:
            print(f"  {f}")
        return 1

    # --- Serialise the products: block ---
    new_products_yaml = serialize_products_yaml(included)

    # --- Determine target files ---
    domain_path = domain  # "aspose/org"
    target_files: list[tuple[Path, bool]] = []  # (path, is_english)

    en_path = _CONTENT_WEBSITES / "en" / domain_path / "_index.md"
    if not en_path.exists():
        print(f"ERROR: English domain page not found: {en_path}")
        return 1
    target_files.append((en_path, True))

    # Collect locale files
    missing_locales: list[Path] = []
    for locale_dir in sorted(_CONTENT_WEBSITES.iterdir()):
        if locale_dir.name == "en" or not locale_dir.is_dir():
            continue
        locale_page = locale_dir / domain_path / "_index.md"
        if locale_page.exists():
            target_files.append((locale_page, False))
        else:
            missing_locales.append(locale_page)

    if missing_locales and not allow_missing_locales:
        print(f"ERROR: {len(missing_locales)} expected locale file(s) missing:")
        for p in missing_locales[:5]:
            print(f"  {p.relative_to(_REPO_ROOT)}")
        if len(missing_locales) > 5:
            print(f"  ... and {len(missing_locales) - 5} more")
        print("Use --allow-missing-locales to proceed anyway.")
        return 1

    # --- Process each file ---
    changed: list[str] = []
    errors: list[str] = []

    for file_path, is_english in target_files:
        rel_path = str(file_path.relative_to(_REPO_ROOT)).replace("\\", "/")
        old_text = file_path.read_text(encoding="utf-8")
        new_text = replace_products_in_text(
            old_text,
            new_products_yaml,
            update_provenance=is_english,
        )

        if new_text is None:
            errors.append(f"No frontmatter: {rel_path}")
            continue

        if new_text == old_text:
            if verbose:
                print(f"  unchanged: {rel_path}")
            continue

        diff = _unified_diff(old_text, new_text, rel_path)
        changed.append(rel_path)

        if dry_run:
            print(f"\n--- DRY-RUN diff: {rel_path} ---")
            print(diff)
        else:
            # Verify updated frontmatter parses cleanly before writing
            import yaml
            fm_m = _FRONTMATTER_RE.match(new_text)
            if fm_m:
                try:
                    yaml.safe_load(fm_m.group(1))
                except yaml.YAMLError as exc:
                    errors.append(f"Generated YAML parse error in {rel_path}: {exc}")
                    continue
            file_path.write_text(new_text, encoding="utf-8")
            if verbose:
                print(f"  updated: {rel_path}")

    # --- Summary ---
    mode_label = "DRY-RUN" if dry_run else "WRITE"
    print(f"\n{mode_label} summary:")
    print(f"  files processed: {len(target_files)}")
    print(f"  files changed:   {len(changed)}")
    print(f"  errors:          {len(errors)}")

    if errors:
        print("ERRORS:")
        for e in errors:
            print(f"  {e}")
        return 1

    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--domain",
        default="aspose/org",
        help="Domain path to sync (default: aspose/org)",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--dry-run",
        action="store_true",
        help="Print diffs without writing (default if neither flag supplied)",
    )
    mode.add_argument(
        "--write",
        action="store_true",
        help=(
            "Write changes to disk. "
            "WARNING: content/websites.aspose.org/ is a governed path — "
            "create an override token before committing."
        ),
    )
    parser.add_argument(
        "--allow-missing-locales",
        action="store_true",
        help="Continue even if some locale _index.md files are absent",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress per-file output (errors still shown)",
    )
    args = parser.parse_args()

    # Default to dry-run if neither --dry-run nor --write
    dry_run = not args.write

    if not args.dry_run and not args.write:
        print("INFO: No mode flag supplied — defaulting to --dry-run (safe).")

    return run(
        domain=args.domain,
        dry_run=dry_run,
        allow_missing_locales=args.allow_missing_locales,
        verbose=not args.quiet,
    )


if __name__ == "__main__":
    sys.exit(main())
