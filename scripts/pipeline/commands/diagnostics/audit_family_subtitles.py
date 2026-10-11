#!/usr/bin/env python3
"""
Audit family-level _index.md subtitles across docs/kb/reference sites.

Checks each family root page for subtitle presence, length, and
platform-specific wording. Produces a JSON audit report and exits
non-zero if any FAIL-level issues are found.

Designed to be called standalone or from refresh/launch pipelines
as a fail-closed validation step.

Exit codes:
  0  All families pass
  1  One or more FAIL-level issues found
  2  Setup error
"""
import argparse
import json
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML not installed", file=sys.stderr)
    sys.exit(2)

_REPO_ROOT = Path(__file__).resolve().parents[4]

_SITES = [
    "docs.aspose.org",
    "kb.aspose.org",
    "reference.aspose.org",
]

_SUBTITLE_MAX = 55

_PLATFORM_TERMS = ["Python", "Java", ".NET", "C++", "Node.js", "Go ", "TypeScript"]


def _parse_frontmatter(path: Path) -> dict | None:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return None
    end = text.find("\n---", 3)
    if end == -1:
        return None
    try:
        fm = yaml.safe_load(text[3:end])
    except yaml.YAMLError:
        return None
    return fm if isinstance(fm, dict) else None


def audit_subtitle(path: Path, site: str, family: str) -> dict:
    """Audit a single family _index.md. Returns an audit entry dict."""
    entry = {
        "site": site,
        "family": family,
        "file": str(path.relative_to(_REPO_ROOT)) if path.is_relative_to(_REPO_ROOT) else str(path),
        "exists": path.exists(),
        "subtitle": None,
        "chars": 0,
        "issues": [],
        "severity": "OK",
    }

    if not path.exists():
        entry["issues"].append({"code": "FILE_MISSING", "severity": "FAIL",
                                 "message": f"Family index not found: {path}"})
        entry["severity"] = "FAIL"
        return entry

    fm = _parse_frontmatter(path)
    if fm is None:
        entry["issues"].append({"code": "PARSE_ERROR", "severity": "FAIL",
                                 "message": "Cannot parse frontmatter"})
        entry["severity"] = "FAIL"
        return entry

    subtitle = fm.get("subtitle")

    if subtitle is None:
        entry["issues"].append({"code": "MISSING", "severity": "FAIL",
                                 "message": "subtitle field missing from frontmatter"})
        entry["severity"] = "FAIL"
        return entry

    if not isinstance(subtitle, str) or not subtitle.strip():
        entry["issues"].append({"code": "EMPTY", "severity": "FAIL",
                                 "message": "subtitle is empty or non-string"})
        entry["severity"] = "FAIL"
        return entry

    entry["subtitle"] = subtitle
    entry["chars"] = len(subtitle)

    if len(subtitle) > _SUBTITLE_MAX:
        entry["issues"].append({
            "code": "OVER_LENGTH",
            "severity": "FAIL",
            "message": f"subtitle is {len(subtitle)} chars (max {_SUBTITLE_MAX})",
        })
        entry["severity"] = "FAIL"

    for term in _PLATFORM_TERMS:
        if term in subtitle:
            entry["issues"].append({
                "code": "PLATFORM_SPECIFIC",
                "severity": "WARN",
                "message": f"subtitle contains platform term '{term.strip()}'",
            })
            if entry["severity"] == "OK":
                entry["severity"] = "WARN"

    return entry


def run_audit(
    sites: list[str] | None = None,
    families: list[str] | None = None,
) -> list[dict]:
    """Run the full audit. Returns list of entry dicts."""
    sites = sites or _SITES
    results = []

    for site in sites:
        en_root = _REPO_ROOT / "content" / site / "en"
        if not en_root.exists():
            continue

        family_dirs = sorted(en_root.iterdir()) if families is None else [
            en_root / f for f in families
        ]

        for family_dir in family_dirs:
            if not family_dir.is_dir():
                continue
            family = family_dir.name
            index_md = family_dir / "_index.md"
            results.append(audit_subtitle(index_md, site, family))

    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site", action="append", help="Site(s) to audit")
    parser.add_argument("--family", action="append", help="Family(ies) to audit")
    parser.add_argument("--json", dest="json_output", help="Write JSON report to path")
    parser.add_argument("--repair", action="store_true",
                        help="Attempt repair of missing/invalid subtitles (NOT IMPLEMENTED — fail-closed)")
    args = parser.parse_args()

    if args.repair:
        print("ERROR: --repair is not implemented. Family subtitles on docs/kb/reference "
              "are structural pages (auto_updatable: false) with no automated authority source. "
              "Use /manual-edit (S-73) to repair individual subtitles.", file=sys.stderr)
        return 2

    results = run_audit(sites=args.site, families=args.family)

    if args.json_output:
        Path(args.json_output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json_output).write_text(
            json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")

    fails = [r for r in results if r["severity"] == "FAIL"]
    warns = [r for r in results if r["severity"] == "WARN"]
    ok = [r for r in results if r["severity"] == "OK"]

    for r in results:
        if r["issues"]:
            for issue in r["issues"]:
                print(f"{issue['severity']} {r['file']}: {issue['code']} — {issue['message']}")

    print(f"\n{len(results)} entries audited: {len(ok)} OK, {len(warns)} WARN, {len(fails)} FAIL")

    if fails:
        print(f"\n{len(fails)} FAIL — subtitle audit did not pass.", file=sys.stderr)
        return 1

    status = "PASS"
    if warns:
        status += f" (with {len(warns)} warning(s))"
    print(f"\n{status}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
