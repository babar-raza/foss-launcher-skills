#!/usr/bin/env python3
"""check_site_plan_mandatory_roles.py — Detect stale mandatory blog_role pointers.

BLOG-SLUGDUPE-001 follow-up (plans/healing/2026-09-18-site-plan-bookkeeping-
self-review-remediation.md, Taskcard SPBK-02). Each product's
reports/plans/{family}/{platform}/site_plan.yaml carries exactly one
mandatory `blog_role: announcement` record and one mandatory
`blog_role: features` record under plan.sections.blog.pages. Both are
supposed to point at the live blog post filling that role. When the pointed-
to post is later retired (draft: true) or renamed without the plan record
being updated, the record goes stale and nothing previously caught it.

This defect class was found twice independently and by accident: once
inside an already-"resolved" content-duplication incident (BLOG-URLDUPE-001,
note/python), and once pre-existing in a product (cells/net) that was only
checked because an unrelated edit happened to touch it. Neither occurrence
was caught by any existing check. This script is the permanent guard.

Four distinct problems are detected, never conflated:
  - stale:         the record's target exists but is `draft: true` (retired).
  - alias_covered: the record's target path does not exist, but exactly one
                   live sibling's `aliases:` already claims that slug's URL --
                   i.e. the page was renamed and the plan never followed. The
                   right fix is to repoint the plan, NEVER to generate a page
                   at the slug (that would collide with the alias redirect;
                   found 2026-09-18 when 3 duplicate posts were generated
                   for exactly this case and had to be retired).
  - missing:       the record's target path does not exist on disk and no
                   live sibling aliases it (a different defect: the mandatory
                   page was genuinely never generated).
  - double_role:   the same slug is assigned to more than one mandatory role
                   in the same product (a plan-authoring defect, independent
                   of whether either assignment is stale).

Uses a real YAML parser throughout (yaml.safe_load + core.markdown's shared
parse_frontmatter) -- no regex-based structural assumptions about field
order, which is what made the first, ad hoc version of this check fragile.

--apply only ever repairs a `stale` or `alias_covered` finding, and only when
exactly one live sibling in the same family/platform carries an `aliases:`
entry pointing back at the recorded slug's own URL -- the same mechanism that
actually resolved all 13 originally-known fixes by hand. If zero or more than
one such sibling exists, the finding is left for a human to resolve (matches
the real `words/python` / `email/cpp` cases, which needed a human judgment
call, not an automated guess). --apply never touches `missing` or
`double_role` findings -- both require a human decision about intent, not
a mechanical repair.

Usage:
    # Report every product with a site_plan.yaml (default mode; writes nothing)
    python check_site_plan_mandatory_roles.py --all

    # Report specific products only
    python check_site_plan_mandatory_roles.py --products slides/cpp cells/net

    # Repair every unambiguous stale finding across all products
    python check_site_plan_mandatory_roles.py --all --apply

Exit code: 0 if no findings of any kind remain after the run; 1 otherwise.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent
_PIPELINE_ROOT = _HERE.parent.parent  # commands/diagnostics/ -> scripts/pipeline/
if str(_PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_ROOT))
_LIB_DIR = str(_PIPELINE_ROOT / "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)

import yaml  # noqa: E402

from core.markdown import parse_frontmatter  # noqa: E402

MANDATORY_ROLES = {"announcement", "features"}


def repo_root() -> Path:
    """scripts/pipeline/commands/diagnostics/ -> scripts/pipeline -> scripts -> repo root."""
    return _PIPELINE_ROOT.parent.parent


def discover_plans(root: Path, products: list[str] | None) -> list[Path]:
    """Return sorted site_plan.yaml paths, optionally filtered to family/platform pairs."""
    base = root / "reports" / "plans"
    if products:
        found = []
        for p in products:
            family, _, platform = p.partition("/")
            candidate = base / family / platform / "site_plan.yaml"
            if candidate.exists():
                found.append(candidate)
        return sorted(found)
    return sorted(base.glob("*/*/site_plan.yaml"))


def _is_draft(fm: dict[str, Any]) -> bool:
    return str(fm.get("draft", "")).strip().lower() == "true"


def _aliases(fm: dict[str, Any]) -> list[str]:
    raw = fm.get("aliases")
    if raw is None:
        return []
    if isinstance(raw, str):
        return [raw]
    if isinstance(raw, list):
        return [str(a) for a in raw]
    return []


def check_plan(plan_path: Path, root: Path) -> dict[str, Any]:
    """Check one product's site_plan.yaml. Never raises -- parse failures are findings."""
    rel = plan_path.relative_to(root / "reports" / "plans")
    family, platform = rel.parts[0], rel.parts[1]
    result: dict[str, Any] = {
        "family": family,
        "platform": platform,
        "plan_path": str(plan_path),
        "parse_error": None,
        "stale": [],
        "alias_covered": [],
        "missing": [],
        "double_role": [],
    }

    try:
        data = yaml.safe_load(plan_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        result["parse_error"] = f"YAML parse error: {exc}"
        return result

    try:
        pages = data["plan"]["sections"]["blog"]["pages"]
    except (KeyError, TypeError):
        result["parse_error"] = "no plan.sections.blog.pages list found"
        return result
    if not isinstance(pages, list):
        result["parse_error"] = "plan.sections.blog.pages is not a list"
        return result

    slug_to_roles: dict[str, list[str]] = {}
    for page in pages:
        if not isinstance(page, dict):
            continue
        if not page.get("mandatory") or page.get("blog_role") not in MANDATORY_ROLES:
            continue

        role = page["blog_role"]
        slug = str(page.get("slug", ""))
        rel_path = str(page.get("path", ""))
        slug_to_roles.setdefault(slug, []).append(role)

        content_path = root / rel_path
        if not content_path.exists():
            survivor = find_unambiguous_survivor(family, platform, slug, root)
            if survivor is not None:
                result["alias_covered"].append(
                    {"role": role, "slug": slug, "path": rel_path, "survivor": survivor}
                )
            else:
                result["missing"].append({"role": role, "slug": slug, "path": rel_path})
            continue

        fm = parse_frontmatter(content_path)
        if _is_draft(fm):
            result["stale"].append({"role": role, "slug": slug, "path": rel_path})

    for slug, roles in slug_to_roles.items():
        if len(roles) > 1:
            result["double_role"].append({"slug": slug, "roles": sorted(roles)})

    return result


def find_unambiguous_survivor(
    family: str, platform: str, stale_slug: str, root: Path
) -> str | None:
    """Return the one live sibling slug whose aliases: points back at stale_slug's URL.

    Works for both a retired slug (stale) and a never-generated slug that only
    exists as another page's alias (alias_covered). Returns None if zero or
    more than one such sibling exists -- callers must treat None as "needs a
    human," never as "no survivor exists."
    """
    stale_url = f"/{family}/{platform}/{stale_slug}/"
    blog_dir = root / "content" / "blog.aspose.org" / family / platform
    if not blog_dir.is_dir():
        return None

    candidates: list[str] = []
    for child in sorted(blog_dir.iterdir()):
        if not child.is_dir():
            continue
        index_md = child / "index.md"
        if not index_md.exists():
            continue
        fm = parse_frontmatter(index_md)
        if _is_draft(fm):
            continue
        if stale_url in _aliases(fm):
            candidates.append(child.name)

    if len(candidates) == 1:
        return candidates[0]
    return None


def apply_repairs(check_result: dict[str, Any], root: Path) -> list[dict[str, Any]]:
    """Repair every unambiguous stale/alias_covered finding in one plan file, in place.

    Returns the list of repairs actually applied (empty list if none were
    unambiguous). Never touches missing/double_role findings.
    """
    if not check_result["stale"] and not check_result.get("alias_covered"):
        return []

    plan_path = Path(check_result["plan_path"])
    text = plan_path.read_text(encoding="utf-8")
    applied: list[dict[str, Any]] = []

    findings = [(f, "stale") for f in check_result["stale"]] + [
        (f, "alias_covered") for f in check_result.get("alias_covered", [])
    ]
    for finding, kind in findings:
        family, platform = check_result["family"], check_result["platform"]
        old_slug = finding["slug"]
        survivor = find_unambiguous_survivor(family, platform, old_slug, root)
        if survivor is None:
            continue  # ambiguous or no survivor -- leave for a human, do not guess

        old_path = finding["path"]
        new_path = old_path.replace(f"/{old_slug}/", f"/{survivor}/")
        old_block = f"slug: {old_slug}\n        path: {old_path}"
        new_block = f"slug: {survivor}\n        path: {new_path}"
        if old_block not in text:
            # Field indentation differs from the expected 8-space convention;
            # refuse rather than risk a malformed edit.
            continue

        role_label = "Introductory announcement post" if finding["role"] == "announcement" \
            else "Key features overview post"
        reason = (
            f"{old_slug} retired, this is the live survivor"
            if kind == "stale"
            else f"{old_slug} exists only as an aliases: redirect on this live page"
        )
        note = (
            f"note: '{role_label} (bookkeeping update via "
            f"check_site_plan_mandatory_roles.py --apply: {reason})'"
        )
        # Replace the slug/path pair; then replace the very next `note:` line
        # that follows it (bounded to avoid touching a later record's note).
        text = text.replace(old_block, new_block, 1)
        idx = text.find(new_block)
        note_start = text.find("note:", idx)
        note_end = text.find("\n", note_start)
        if note_start != -1 and note_start - idx < 400:
            text = text[:note_start] + note + text[note_end:]

        applied.append({
            "role": finding["role"], "old_slug": old_slug, "new_slug": survivor,
        })

    if applied:
        plan_path.write_text(text, encoding="utf-8")

    return applied


def _print_report(results: list[dict[str, Any]]) -> int:
    total_findings = 0
    for r in results:
        label = f"{r['family']}/{r['platform']}"
        if r["parse_error"]:
            print(f"{label:24} PARSE ERROR: {r['parse_error']}")
            total_findings += 1
            continue
        if not (r["stale"] or r["alias_covered"] or r["missing"] or r["double_role"]):
            continue
        for f in r["stale"]:
            print(f"{label:24} STALE        {f['role']:12} -> {f['slug']}")
            total_findings += 1
        for f in r["alias_covered"]:
            print(f"{label:24} ALIAS-COVERED {f['role']:12} -> {f['slug']} "
                  f"(live page {f['survivor']} aliases this slug; repoint the plan, do NOT generate)")
            total_findings += 1
        for f in r["missing"]:
            print(f"{label:24} MISSING      {f['role']:12} -> {f['slug']} (no file at {f['path']})")
            total_findings += 1
        for f in r["double_role"]:
            print(f"{label:24} DOUBLE-ROLE  {f['slug']} assigned to: {', '.join(f['roles'])}")
            total_findings += 1
    return total_findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Detect stale mandatory blog_role pointers in site_plan.yaml files."
    )
    parser.add_argument("--all", action="store_true", help="Check every product with a site_plan.yaml")
    parser.add_argument("--products", nargs="*", default=None, help="family/platform pairs, e.g. slides/cpp cells/net")
    parser.add_argument("--apply", action="store_true", default=False, help="Repair unambiguous stale findings in place (default: report only)")
    args = parser.parse_args(argv)

    if not args.all and not args.products:
        parser.print_help()
        return 0

    root = repo_root()
    plans = discover_plans(root, args.products)
    if not plans:
        print("No site_plan.yaml files found for the given selection.")
        return 0

    mode = "APPLY" if args.apply else "REPORT-ONLY"
    print(f"check_site_plan_mandatory_roles — mode={mode}  products={len(plans)}")

    results = [check_plan(p, root) for p in plans]

    if args.apply:
        for r in results:
            if r["parse_error"]:
                continue
            repaired = apply_repairs(r, root)
            for rep in repaired:
                print(f"  REPAIRED  {r['family']}/{r['platform']}  {rep['role']}: "
                      f"{rep['old_slug']} -> {rep['new_slug']}")
            if repaired:
                # Re-check after writing so the final report reflects reality.
                idx = results.index(r)
                results[idx] = check_plan(Path(r["plan_path"]), root)

    remaining = _print_report(results)
    print()
    print(f"Remaining findings: {remaining}")
    return 1 if remaining else 0


if __name__ == "__main__":
    sys.exit(main())
