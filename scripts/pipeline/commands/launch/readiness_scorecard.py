#!/usr/bin/env python3
"""Compute a standalone launch-readiness scorecard from local fixtures."""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
CONTENT = ROOT / "content"
PHASE_STATE = ROOT / "reports" / "phase_state.json"
SUBDOMAINS = ["products.aspose.org", "docs.aspose.org", "kb.aspose.org", "reference.aspose.org", "blog.aspose.org"]
HGATES = ["h01", "h02", "h03", "h04", "h05"]


def configure(*, repo_root: Path | str | None = None) -> None:
    global ROOT, CONTENT, PHASE_STATE
    ROOT = Path(repo_root) if repo_root is not None else Path(__file__).resolve().parents[4]
    CONTENT = ROOT / "content"
    PHASE_STATE = ROOT / "reports" / "phase_state.json"


def collect_grades(family: str, platform: str, content_root: Path = CONTENT) -> dict[str, int]:
    grades = {"A": 0, "B": 0, "C": 0, "D": 0, "F": 0, "ungraded": 0}
    grade_re = re.compile(r"^grade:\s*([A-F])\s*$", re.MULTILINE)
    roots = [
        content_root / "blog.aspose.org" / family / platform,
        *(content_root / site / "en" / family / platform for site in SUBDOMAINS if site != "blog.aspose.org"),
    ]
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*.md"):
            text = path.read_text(encoding="utf-8", errors="replace")[:2000]
            match = grade_re.search(text)
            grades[match.group(1) if match else "ungraded"] += 1
    return grades


def read_checkpoints(state_file: Path, family: str, platform: str) -> dict:
    if not state_file.exists():
        return {}
    data = json.loads(state_file.read_text(encoding="utf-8"))
    entry = data.get(f"{family}/{platform}", {})
    return entry.get("values", {}) if isinstance(entry, dict) else {}


def read_hgate_signoffs(root: Path, family: str, platform: str) -> dict[str, str]:
    results: dict[str, str] = {}
    review_dir = root / "reports" / "human-review"
    for gate in HGATES:
        path = review_dir / f"{family}-{platform}-{gate}-sample.md"
        if not path.exists():
            results[gate] = ""
            continue
        match = re.search(r'^result:\s*"?(PASS|FAIL|CONDITIONAL)"?\s*$', path.read_text(encoding="utf-8", errors="replace"), re.MULTILINE | re.IGNORECASE)
        results[gate] = match.group(1).upper() if match else ""
    return results


def compute_verdict(grades: dict[str, int], checkpoints: dict, hgate_results: dict[str, str], *, skip_human_review: bool = False) -> tuple[bool, list[str]]:
    blockers: list[str] = []
    df_count = grades.get("D", 0) + grades.get("F", 0)
    if df_count:
        blockers.append(f"{df_count} page(s) graded D or F")
    if not checkpoints.get("truth_audit_done"):
        blockers.append("truth_audit_done checkpoint not set")
    if not skip_human_review:
        for gate in HGATES:
            result = hgate_results.get(gate, "")
            if result != "PASS":
                blockers.append(f"{gate.upper()}: {result or 'not reviewed'}")
    return not blockers, blockers


def scorecard(family: str, platform: str, *, root: Path = ROOT, skip_human_review: bool = False) -> dict:
    grades = collect_grades(family, platform, root / "content")
    checkpoints = read_checkpoints(root / "reports" / "phase_state.json", family, platform)
    hgate_results = read_hgate_signoffs(root, family, platform)
    ready, blockers = compute_verdict(grades, checkpoints, hgate_results, skip_human_review=skip_human_review)
    return {"family": family, "platform": platform, "grades": grades, "checkpoints": checkpoints, "hgate_results": hgate_results, "ready": ready, "verdict": "READY TO SHIP" if ready else "NOT READY", "blockers": blockers}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--family", required=True)
    parser.add_argument("--platform", required=True)
    parser.add_argument("--repo-root")
    parser.add_argument("--skip-human-review", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    root = Path(args.repo_root) if args.repo_root else ROOT
    payload = scorecard(args.family, args.platform, root=root, skip_human_review=args.skip_human_review)
    print(json.dumps(payload, indent=2) if args.json else payload["verdict"])
    return 0 if payload["ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
