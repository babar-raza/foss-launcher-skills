#!/usr/bin/env python3
"""audit_content_hash.py — content-hash integrity + frontmatter-only-refresh detection.

Two capabilities:

1. (original) Report files where the stored ``content_hash`` provenance value no
   longer matches the SHA-256 of the page body (integrity/drift).

2. (RPR-F-04) Detect a **frontmatter-only refresh**: a change where a page's
   ``evidence:`` block moved (e.g. ``evidence.model_sha`` bumped) but the page BODY
   is byte-identical — and, worst of all, its grade regressed anyway. This is the
   literal PDF-NET-REFRESH-001 v26.7.0 defect: a KB page graded A->C purely from
   re-evaluating unchanged prose against a bumped evidence pointer (plan §2.4). It
   reuses this module's body hashing (via ``provenance.compute_content_hash``'s
   normalization) — before RPR-F-04, this module had ZERO callers; it is now wired
   into ``post_refresh_verify.py`` Check 10.

Usage:
    python audit_content_hash.py                          # integrity scan (English content)
    python audit_content_hash.py --files a.md b.md        # integrity of specific files
    python audit_content_hash.py --detect-evidence-only --base HEAD --files a.md
                                                          # frontmatter-only-refresh detection vs a git ref
    python audit_content_hash.py --json                   # JSON output
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE.parent.parent))  # scripts/pipeline/
    _LIB_DIR = str(Path(_HERE) / "lib") if isinstance(_HERE, str) else str(_HERE / "lib")
    if _LIB_DIR not in sys.path:
        sys.path.insert(0, _LIB_DIR)

from provenance import read_provenance, compute_content_hash  # noqa: E402

_REPO_ROOT = _HERE.parent.parent.parent.parent
_FRONTMATTER_SPLIT = re.compile(r"^---\n(.*?)\n---\n?", re.DOTALL)


def audit_file(filepath: Path) -> dict | None:
    """Check a single file. Returns a mismatch dict or None if OK/skipped."""
    prov = read_provenance(filepath)
    if prov is None:
        return None
    stored = prov.get("content_hash", "")
    if not stored:
        return None  # no hash to compare — not a mismatch, just absent
    computed = compute_content_hash(filepath)
    if not computed:
        return None
    if stored != computed:
        return {
            "path": str(filepath),
            "stored": stored,
            "computed": computed,
        }
    return None


def scan_directory(root: Path) -> list[dict]:
    """Scan all .md files under root for stale hashes."""
    mismatches = []
    for md_file in sorted(root.rglob("*.md")):
        result = audit_file(md_file)
        if result:
            mismatches.append(result)
    return mismatches


# ── RPR-F-04: frontmatter-only-refresh detection ─────────────────────────────

def _split_frontmatter_body(text: str) -> tuple[str, str]:
    """Return (frontmatter_text, body_text). Empty frontmatter if none present."""
    m = _FRONTMATTER_SPLIT.match(text)
    if not m:
        return "", text
    return m.group(1), text[m.end():]


def _body_hash(text: str) -> str:
    """Normalized body hash — same normalization as provenance.compute_content_hash,
    so this shares that utility's notion of 'the body' (CRLF/whitespace-insensitive)."""
    from provenance import _normalize_body  # reuse the exact normalization
    _, body = _split_frontmatter_body(text)
    return hashlib.sha256(_normalize_body(body).encode("utf-8")).hexdigest()[:32]


def _frontmatter_top_keys(fm_text: str) -> dict:
    """Parse frontmatter YAML into a dict of top-level keys (best-effort)."""
    try:
        import yaml
        data = yaml.safe_load(fm_text)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def is_frontmatter_only_change(old_text: str, new_text: str) -> dict | None:
    """Return a violation dict when the BODY is byte-identical (normalized) between
    old and new, but the frontmatter's ``evidence:`` block changed. None otherwise.

    Reuses check_evidence_churn.py's YAML top-level-key comparison technique (plan §16b):
    compare the parsed ``evidence`` sub-dict, not a line regex, since evidence is
    nested/variable-shape.
    """
    if _body_hash(old_text) != _body_hash(new_text):
        return None  # body changed — not a frontmatter-only change

    old_fm, _ = _split_frontmatter_body(old_text)
    new_fm, _ = _split_frontmatter_body(new_text)
    old_ev = _frontmatter_top_keys(old_fm).get("evidence")
    new_ev = _frontmatter_top_keys(new_fm).get("evidence")
    if old_ev == new_ev:
        return None  # evidence unchanged too — nothing to flag

    return {
        "body_identical": True,
        "evidence_changed": True,
        "old_model_sha": (old_ev or {}).get("model_sha") if isinstance(old_ev, dict) else None,
        "new_model_sha": (new_ev or {}).get("model_sha") if isinstance(new_ev, dict) else None,
    }


def _grade(text: str) -> str | None:
    fm, _ = _split_frontmatter_body(text)
    return _frontmatter_top_keys(fm).get("grade")


_GRADE_ORDER = {"A": 4, "B": 3, "C": 2, "D": 1, "F": 0}


def is_evidence_only_grade_regression(old_text: str, new_text: str) -> dict | None:
    """The exact PDF-NET-REFRESH-001 v26.7.0 defect: a frontmatter-only change
    (body byte-identical, evidence bumped) whose grade ALSO regressed. Returns a
    violation dict (with the grade movement) or None."""
    fm_only = is_frontmatter_only_change(old_text, new_text)
    if fm_only is None:
        return None
    old_g, new_g = _grade(old_text), _grade(new_text)
    if old_g in _GRADE_ORDER and new_g in _GRADE_ORDER and _GRADE_ORDER[new_g] < _GRADE_ORDER[old_g]:
        return {**fm_only, "grade_before": old_g, "grade_after": new_g,
                "reason": "grade regressed on a frontmatter-only change (body unchanged, "
                          "evidence pointer bumped) — the PDF-NET-REFRESH-001 v26.7.0 bug shape"}
    return None


def _git_show(ref: str, path: str) -> str | None:
    try:
        r = subprocess.run(["git", "show", f"{ref}:{path}"],
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace", cwd=str(_REPO_ROOT))
        return r.stdout if r.returncode == 0 else None
    except Exception:
        return None


def detect_evidence_only_grade_regressions(files: list[str], base_ref: str = "HEAD") -> list[dict]:
    """For each file, compare its working-tree content against ``base_ref`` and return
    a violation for any frontmatter-only change that also regressed the grade.
    A file with no base version (new file) or unreadable content is skipped."""
    violations: list[dict] = []
    for f in files:
        rel = f.replace("\\", "/")
        old = _git_show(base_ref, rel)
        if old is None:
            continue
        try:
            new = Path(f).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        v = is_evidence_only_grade_regression(old, new)
        if v:
            violations.append({"path": rel, **v})
    return violations


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Report files where stored content_hash != computed hash."
    )
    parser.add_argument(
        "--path", default=None,
        help="Directory to scan (default: content/*/en/)",
    )
    parser.add_argument(
        "--files", nargs="*", default=None,
        help="Specific files to check",
    )
    parser.add_argument(
        "--json", dest="json_output", action="store_true",
        help="Output results as JSON",
    )
    parser.add_argument(
        "--detect-evidence-only", action="store_true",
        help="(RPR-F-04) Detect frontmatter-only refreshes (body byte-identical, evidence "
             "bumped) that regressed the grade, comparing --files against --base; exit 1 on findings",
    )
    parser.add_argument(
        "--base", default="HEAD",
        help="Git ref to compare against for --detect-evidence-only (default: HEAD)",
    )
    args = parser.parse_args(argv)

    if args.detect_evidence_only:
        if not args.files:
            print("ERROR: --detect-evidence-only requires --files", file=sys.stderr)
            return 2
        violations = detect_evidence_only_grade_regressions(args.files, base_ref=args.base)
        if args.json_output:
            print(json.dumps(violations, indent=2))
        elif violations:
            print(f"FRONTMATTER_ONLY_REGRESSION: {len(violations)} file(s) — body unchanged, "
                  f"evidence bumped, grade regressed:")
            for v in violations:
                print(f"  {v['path']}: {v['grade_before']}->{v['grade_after']}")
        else:
            print("OK: no frontmatter-only grade regressions detected.")
        return 1 if violations else 0

    mismatches: list[dict] = []

    if args.files:
        for f in args.files:
            result = audit_file(Path(f))
            if result:
                mismatches.append(result)
    elif args.path:
        mismatches = scan_directory(Path(args.path))
    else:
        # Default: scan all English content directories
        repo_root = _HERE.parent.parent.parent.parent
        content_root = repo_root / "content"
        for site_dir in sorted(content_root.iterdir()):
            en_dir = site_dir / "en"
            if en_dir.is_dir():
                mismatches.extend(scan_directory(en_dir))

    if args.json_output:
        print(json.dumps(mismatches, indent=2))
    else:
        if mismatches:
            print(f"STALE: {len(mismatches)} file(s) with mismatched content_hash:")
            for m in mismatches:
                print(f"  {m['path']}")
                print(f"    stored:   {m['stored']}")
                print(f"    computed: {m['computed']}")
        else:
            print("OK: all content_hash values match computed hashes.")

    return 1 if mismatches else 0


if __name__ == "__main__":
    sys.exit(main())