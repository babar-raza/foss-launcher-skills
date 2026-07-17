#!/usr/bin/env python3
"""seo_stability_check.py — RPR-F-05: SEO-safety gates for the refresh pipeline.

Plan §2.3 confirmed there is **no** title/H1/slug/canonical stability check anywhere
in the pipeline. A refresh that silently changes a live page's URL slug, canonical
tag, `<title>`, or H1 damages its search ranking with no gate to catch it. This
module compares a page's SEO-load-bearing fields before vs. after a refresh and
flags any change that was not explicitly pre-declared as intentional (via the
refresh-run manifest's `intentional_renames` allowlist, schema 5e).

  * `extract_seo_fields(frontmatter, body)` → the 4 fields, normalized.
  * `compare_seo(before, after)` → list of changed field names.
  * `detect_seo_violations(pages, base_ref, intentional_renames=...)` → per-page
    violations, comparing the working tree against a git base ref.

A page whose id is in `intentional_renames` may change freely (a declared rename);
any other page changing any of the 4 fields is a blocking violation.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

_THIS = Path(__file__).resolve()
_PIPELINE_ROOT = _THIS.parents[2]
_REPO_ROOT = _THIS.parents[3]
if str(_PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_ROOT))

# Reuse the frontmatter split/parse already proven in audit_content_hash (RPR-F-04)
# rather than reimplementing YAML-frontmatter handling.
from commands.content.audit_content_hash import (  # noqa: E402
    _frontmatter_top_keys,
    _split_frontmatter_body,
)

# SEO-load-bearing fields. title/slug/canonical come from frontmatter; H1 from body.
SEO_FIELDS = ("title", "slug", "canonical", "h1")

_H1_RE = re.compile(r"^\s*#\s+(.+?)\s*$", re.MULTILINE)


def _first_h1(body: str) -> str | None:
    """The first ATX H1 (`# ...`) in the body, or None. Fenced code is not stripped
    because a leading `#` inside a code fence is not a Markdown H1 in practice for
    these pages (H1 is always the page title line at top)."""
    m = _H1_RE.search(body)
    return m.group(1).strip() if m else None


def extract_seo_fields(frontmatter: dict, body: str) -> dict:
    """Return the normalized SEO fields for one page."""
    fm = frontmatter or {}
    return {
        "title": (str(fm["title"]).strip() if fm.get("title") is not None else None),
        "slug": (str(fm["slug"]).strip() if fm.get("slug") is not None else None),
        "canonical": (str(fm["canonical"]).strip() if fm.get("canonical") is not None else None),
        "h1": _first_h1(body or ""),
    }


def extract_from_text(text: str) -> dict:
    """Split a full page (frontmatter + body) and extract its SEO fields."""
    fm_text, body = _split_frontmatter_body(text)
    fm = _frontmatter_top_keys(fm_text)
    return extract_seo_fields(fm, body)


def compare_seo(before: dict, after: dict) -> list[str]:
    """Return the names of SEO fields that changed between before and after.

    A field appearing or disappearing counts as a change; two None values do not.
    """
    changed = []
    for field in SEO_FIELDS:
        if before.get(field) != after.get(field):
            changed.append(field)
    return changed


def _git_show(repo_root: Path, ref: str, path: str) -> str | None:
    """Content of path at ref, or None if it did not exist there / git failed."""
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_root), "show", f"{ref}:{path}"],
            capture_output=True, text=True, timeout=30,
        )
        return result.stdout if result.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


def detect_seo_violations(
    pages: list[str],
    *,
    base_ref: str = "HEAD",
    intentional_renames: set[str] | None = None,
    repo_root: Path | str | None = None,
) -> list[dict]:
    """Compare each page's working-tree SEO fields against base_ref.

    A changed field on a page NOT in intentional_renames is a violation. Pages that
    are new (absent at base_ref) are skipped — there is no prior SEO state to protect.
    """
    repo_root = Path(repo_root) if repo_root else _REPO_ROOT
    intentional = set(intentional_renames or set())
    violations = []
    for page in pages:
        rel = page.replace("\\", "/")
        before_text = _git_show(repo_root, base_ref, rel)
        if before_text is None:
            continue  # new page — nothing to protect
        wt_path = repo_root / rel
        if not wt_path.is_file():
            continue
        after_text = wt_path.read_text(encoding="utf-8", errors="replace")
        changed = compare_seo(extract_from_text(before_text), extract_from_text(after_text))
        if not changed:
            continue
        if page in intentional or rel in intentional:
            continue  # declared rename — allowed
        before_fields = extract_from_text(before_text)
        after_fields = extract_from_text(after_text)
        violations.append({
            "page": rel,
            "changed_fields": changed,
            "before": {f: before_fields.get(f) for f in changed},
            "after": {f: after_fields.get(f) for f in changed},
        })
    return violations


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="SEO-stability gate for refreshed pages (RPR-F-05).")
    parser.add_argument("pages", nargs="*", help="Content page paths (repo-relative)")
    parser.add_argument("--base", default="HEAD", help="Git ref for the before-state (default HEAD)")
    parser.add_argument("--intentional-renames", default="",
                        help="Comma-separated page paths allowed to change SEO fields")
    parser.add_argument("--repo-root", default=str(_REPO_ROOT))
    args = parser.parse_args(argv)

    intentional = {s.strip() for s in args.intentional_renames.split(",") if s.strip()}
    violations = detect_seo_violations(
        args.pages, base_ref=args.base, intentional_renames=intentional, repo_root=args.repo_root
    )
    if violations:
        print(f"SEO STABILITY: {len(violations)} undeclared SEO change(s):")
        for v in violations:
            print(f"  {v['page']}: {v['changed_fields']} changed "
                  f"(before={v['before']} after={v['after']}) — declare in manifest.intentional_renames if intended")
        return 1
    print(f"OK: no undeclared SEO changes across {len(args.pages)} page(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
