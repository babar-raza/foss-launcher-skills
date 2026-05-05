"""plan_check.py — Code-enforced plan validation gate.

Checks whether a given slug exists in the site plan for a family/platform.
Used by generators (new-kb-howto, new-docs-page, etc.) to enforce plan
compliance before writing content.

Usage:
    python scripts/pipeline/plan_check.py {family} {platform} {section} {slug} [--bypass]

Exit codes:
    0 — slug found in plan, plan doesn't exist, or --bypass active
    1 — slug not in plan (prints warning message)
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent
REPORTS_ROOT = REPO_ROOT / "reports" / "plans"
_DEFAULT_REPORTS_ROOT = REPORTS_ROOT


def configure(*, reports_root: "Path | str | None" = None) -> None:
    """Override module-level path constants for testing."""
    global REPORTS_ROOT
    REPORTS_ROOT = Path(reports_root) if reports_root is not None else _DEFAULT_REPORTS_ROOT


def check_slug_in_plan(
    family: str,
    platform: str,
    section: str,
    slug: str,
    bypass: bool = False,
) -> tuple[bool, str]:
    """Check if slug is in the site plan.

    Returns (allowed, message).
    - (True, "") if plan doesn't exist or slug is found.
    - (True, "plan_bypass") if bypass=True and slug not found.
    - (False, "PLAN WARNING: ...") if slug not found and bypass=False.
    """
    plan_path = REPORTS_ROOT / family / platform / "site_plan.yaml"

    if not plan_path.exists():
        return True, ""

    try:
        data = yaml.safe_load(plan_path.read_text(encoding="utf-8"))
    except (yaml.YAMLError, OSError) as exc:
        print(f"WARN: Could not read site plan: {exc}", file=sys.stderr)
        return True, ""

    # Support both wrapped {"plan": {...}} and flat format
    plan = data.get("plan", data) if isinstance(data, dict) else data
    if not isinstance(plan, dict):
        return True, ""

    sections = plan.get("sections", {})
    sec_data = sections.get(section, {})
    pages = sec_data.get("pages", [])

    # Check by slug (exact match)
    for page in pages:
        page_slug = page.get("slug", "")
        if page_slug == slug:
            return True, ""

    # Check by path suffix (handles cases where slug is passed as filename)
    for page in pages:
        page_path = page.get("path", "")
        # Match if slug appears as the terminal component of the path
        if page_path.endswith(f"/{slug}.md") or page_path.endswith(f"/{slug}/index.md"):
            return True, ""
        # Also match bare slug against the path-derived slug
        if slug in page_path:
            return True, ""

    # Slug not found
    if bypass:
        return True, "plan_bypass"

    msg = (
        f"PLAN WARNING: slug '{slug}' is not in the site plan for "
        f"{family}/{platform} section '{section}'.\n"
        f"Run '/site-plan {family} {platform}' to review the evidence-based plan.\n"
        f"Add --bypass-plan to override this warning and generate anyway."
    )
    return False, msg


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Check if a slug exists in the site plan."
    )
    parser.add_argument("family", help="Product family (e.g. 3d, slides)")
    parser.add_argument("platform", help="Platform (e.g. python, java)")
    parser.add_argument(
        "section",
        choices=["products", "blog", "docs", "kb", "reference"],
        help="Site section to check",
    )
    parser.add_argument("slug", help="Slug to verify against the plan")
    parser.add_argument(
        "--bypass",
        action="store_true",
        help="Allow generation even if slug is not in plan",
    )
    args = parser.parse_args()

    allowed, message = check_slug_in_plan(
        args.family, args.platform, args.section, args.slug, args.bypass
    )

    if message == "plan_bypass":
        print("plan_bypass: true")
        sys.exit(0)
    elif not allowed:
        print(message, file=sys.stderr)
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
