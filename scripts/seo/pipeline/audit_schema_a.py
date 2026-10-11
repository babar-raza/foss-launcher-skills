"""
SEO-SCHEMA-A-AUDIT-STALE-ENTRIES audit_schema_a.py
====================================================
Read-only audit: cross-reference every Schema A keywords/*.json entry's
`pageTitle` against real page titles currently on disk under content/, to
find orphaned entries (Finding #32) -- e.g. imaging.json's 249 entries
referencing a KB directory that has never existed in this repo's git history.

An entry is a stale-orphan CANDIDATE if its exact pageTitle does not match
any current page's title frontmatter, anywhere in content/ (not just the
entry's own family -- a page can be authored under a different family
directory than the keyword file's name suggests, and a false "orphan" that
quarantines still-live signal is worse than a missed one). This is
deliberately conservative: exact title match only, no fuzzy/partial
matching, so a page that was reworded (not renamed/removed) is correctly
NOT flagged here -- catching those is SEO-SCHEMA-A-FIX-GENERATION-LOGIC's
sourcePath-based identity, going forward, not this audit's job.

Writes reports/seo/schema_a_stale_audit.json. Makes no changes to keywords/
or content/ -- quarantining confirmed orphans is a separate task
(SEO-SCHEMA-A-QUARANTINE-STALE-ENTRIES).

No LLM calls. No network calls. stdlib + pathlib + pyyaml only.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.exit("audit_schema_a.py requires PyYAML: pip install pyyaml")

try:
    from seo.pipeline.schema import classify_keyword_path, SCHEMA_A
except ImportError:
    from schema import classify_keyword_path, SCHEMA_A

REPO_ROOT = Path(__file__).resolve().parents[3]
CONTENT_ROOT = REPO_ROOT / "content"
KEYWORDS_DIR = REPO_ROOT / "keywords"
REPORTS_DIR = REPO_ROOT / "reports" / "seo"

_LOCALE_VARIANT_RE = re.compile(r"\.[a-z]{2}\.md$", re.IGNORECASE)

_SITES = [
    "blog.aspose.org",
    "docs.aspose.org",
    "kb.aspose.org",
    "products.aspose.org",
    "reference.aspose.org",
    "websites.aspose.org",
    "www.aspose.org",
]


def _extract_title(text: str) -> str | None:
    if not text.startswith("---"):
        return None
    parts = text.split("---", 2)
    if len(parts) < 3:
        return None
    try:
        fm = yaml.safe_load(parts[1]) or {}
    except yaml.YAMLError:
        return None
    title = fm.get("title")
    return title if isinstance(title, str) else None


def build_real_title_index(content_root: Path | None = None) -> dict[str, list[str]]:
    """Map every real page title -> list of repo-relative paths carrying it.

    A list (not a single path) because two live pages can legitimately share
    a title -- the audit only needs "does this title exist anywhere",
    the list is kept for evidence/debugging.
    """
    content_root = content_root or CONTENT_ROOT
    index: dict[str, list[str]] = {}
    for site in _SITES:
        site_root = content_root / site
        if not site_root.exists():
            continue
        for path in site_root.rglob("*.md"):
            if _LOCALE_VARIANT_RE.search(path.name):
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            title = _extract_title(text)
            if title:
                rel = str(path.relative_to(REPO_ROOT)).replace("\\", "/")
                index.setdefault(title, []).append(rel)
    return index


def family_has_launched_content(family: str, content_root: Path | None = None) -> bool:
    """Whether `family` has ANY real page anywhere across the 4 sites that
    organize content by family directory (kb/docs/reference use an /en/
    locale prefix; blog does not). products.aspose.org always has a family
    landing page even for stub-tier families, so it is deliberately excluded
    here -- it would make every family look "launched."
    """
    content_root = content_root or CONTENT_ROOT
    candidates = [
        content_root / "kb.aspose.org" / "en" / family,
        content_root / "docs.aspose.org" / "en" / family,
        content_root / "reference.aspose.org" / "en" / family,
        content_root / "blog.aspose.org" / family,
    ]
    return any(d.is_dir() and any(d.rglob("*.md")) for d in candidates)


def audit_family_file(path: Path, real_titles: dict[str, list[str]]) -> dict:
    family = path.stem
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"family": family, "file": path.name, "error": "unreadable_or_invalid_json"}

    if not isinstance(raw, list):
        return {"family": family, "file": path.name, "error": "root_is_not_a_list"}

    live = 0
    orphans: list[dict] = []
    for idx, entry in enumerate(raw):
        if not isinstance(entry, dict):
            continue
        title = entry.get("pageTitle")
        if not isinstance(title, str):
            continue
        if entry.get("sourcePath"):
            # Post-fix entries carry their own identity; trust it directly
            # rather than re-deriving liveness from a title lookup.
            source_path = entry["sourcePath"]
            if (REPO_ROOT / source_path).exists():
                live += 1
            else:
                orphans.append({"index": idx, "pageTitle": title, "sourcePath": source_path, "reason": "sourcePath_missing_on_disk"})
            continue
        if title in real_titles:
            live += 1
        else:
            orphans.append({"index": idx, "pageTitle": title, "sourcePath": None, "reason": "no_matching_title_anywhere_in_content"})

    has_content = family_has_launched_content(family)
    return {
        "family": family,
        "file": path.name,
        "family_has_launched_content": has_content,
        "total_entries": len([e for e in raw if isinstance(e, dict)]),
        "live_entries": live,
        "orphan_candidates": len(orphans),
        # Prospective: family has zero launched pages, so "no title match" is
        # expected -- these are future-content demand signal, not garbage
        # (Context section, "stub-tier families... Schema A is their only
        # keyword signal"). Drifted: family DOES have launched content, but
        # none of it matches these historical titles -- a stronger signal
        # that the underlying content was substantially reworked/regenerated
        # since these entries were created (exact-title matching cannot tell
        # "topic still covered under a new title" from "topic dropped").
        "orphan_classification": (
            "prospective_no_launched_content" if not has_content and orphans
            else "drifted_title_mismatch" if has_content and orphans
            else "n/a"
        ),
        "orphans": orphans,
    }


def run_audit() -> dict:
    real_titles = build_real_title_index()
    schema_a_files = sorted(
        p for p in KEYWORDS_DIR.glob("*.json") if classify_keyword_path(p) == SCHEMA_A
    )

    results = [audit_family_file(p, real_titles) for p in schema_a_files]
    total_entries = sum(r.get("total_entries", 0) for r in results)
    total_orphans = sum(r.get("orphan_candidates", 0) for r in results)
    prospective = sum(
        r["orphan_candidates"] for r in results if r.get("orphan_classification") == "prospective_no_launched_content"
    )
    drifted = sum(
        r["orphan_candidates"] for r in results if r.get("orphan_classification") == "drifted_title_mismatch"
    )

    report = {
        "meta": {
            "generated_by": "audit_schema_a.py",
            "real_page_titles_indexed": len(real_titles),
            "schema_a_files_audited": len(results),
            "total_entries": total_entries,
            "total_orphan_candidates": total_orphans,
            "orphans_prospective_no_launched_content": prospective,
            "orphans_drifted_title_mismatch": drifted,
        },
        "families": results,
    }
    return report


def main() -> None:
    report = run_audit()
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = REPORTS_DIR / "schema_a_stale_audit.json"
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    print("=== Schema A Stale-Entry Audit ===")
    print(f"Real page titles indexed : {report['meta']['real_page_titles_indexed']}")
    print(f"Schema A files audited   : {report['meta']['schema_a_files_audited']}")
    print(f"Total entries            : {report['meta']['total_entries']}")
    print(f"Total orphan candidates  : {report['meta']['total_orphan_candidates']}")
    print(f"  prospective (no launched content -- future-content signal, do NOT quarantine): {report['meta']['orphans_prospective_no_launched_content']}")
    print(f"  drifted (family HAS launched content, but titles don't match)                 : {report['meta']['orphans_drifted_title_mismatch']}")
    print()
    for fam in sorted(report["families"], key=lambda r: -r.get("orphan_candidates", 0)):
        if fam.get("orphan_candidates"):
            print(f"  {fam['family']:<12} {fam['orphan_candidates']:>4} orphan(s) / {fam.get('total_entries', 0)} total  [{fam.get('orphan_classification')}]")
    print(f"\nFull report: {out_path}")


if __name__ == "__main__":
    main()
