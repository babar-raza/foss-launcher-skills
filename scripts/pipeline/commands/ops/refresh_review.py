#!/usr/bin/env python3
"""Record refresh decisions and generate coverage reports."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
REVIEW_ROOT = REPO_ROOT / "reports" / "refresh_review"
VALID_DECISIONS = frozenset({"BODY_UPDATED", "EVIDENCE_ONLY", "NOT_AFFECTED", "RETIRED"})
SUBDOMAIN_ORDER = ["docs", "kb", "blog", "products", "reference", "unknown"]


def decisions_path(family: str, platform: str, *, review_root: Path | None = None) -> Path:
    return (review_root or REVIEW_ROOT) / family / platform / "page_decisions.json"


def load_decisions(family: str, platform: str, *, review_root: Path | None = None) -> dict:
    path = decisions_path(family, platform, review_root=review_root)
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return {"family": family, "platform": platform, "generated_at": None, "refresh_sha": None, "pages": {}}


def save_decisions(family: str, platform: str, data: dict, *, review_root: Path | None = None) -> None:
    path = decisions_path(family, platform, review_root=review_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(path)


def record_decision(
    family: str,
    platform: str,
    path: str,
    decision: str,
    reason: str,
    *,
    body_hash_changed: bool = False,
    review_root: Path | None = None,
) -> None:
    if decision not in VALID_DECISIONS:
        raise ValueError(f"invalid decision: {decision}")
    data = load_decisions(family, platform, review_root=review_root)
    data.setdefault("pages", {})[path] = {
        "decision": decision,
        "reason": reason,
        "body_hash_changed": body_hash_changed,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
    }
    data["generated_at"] = datetime.now(timezone.utc).isoformat()
    save_decisions(family, platform, data, review_root=review_root)


def infer_subdomain(path: str) -> str:
    for host, label in {
        "docs.aspose.org": "docs",
        "kb.aspose.org": "kb",
        "blog.aspose.org": "blog",
        "products.aspose.org": "products",
        "reference.aspose.org": "reference",
    }.items():
        if host in path:
            return label
    return "unknown"


def generate_coverage_report(family: str, platform: str, *, review_root: Path | None = None) -> str:
    data = load_decisions(family, platform, review_root=review_root)
    pages = data.get("pages", {})
    counts: dict[str, dict[str, int]] = {}
    for path, entry in pages.items():
        subdomain = infer_subdomain(path)
        counts.setdefault(subdomain, {decision: 0 for decision in VALID_DECISIONS} | {"total": 0})
        decision = entry.get("decision")
        if decision in VALID_DECISIONS:
            counts[subdomain][decision] += 1
        counts[subdomain]["total"] += 1
    lines = [
        f"# Coverage Report: {family}/{platform}",
        "",
        f"Generated: {data.get('generated_at', 'unknown')}",
        f"Total pages decided: {len(pages)}",
        "",
        "| Subdomain | Total | BODY_UPDATED | EVIDENCE_ONLY | NOT_AFFECTED | RETIRED |",
        "|-----------|-------|--------------|---------------|--------------|---------|",
    ]
    grand = {decision: 0 for decision in VALID_DECISIONS} | {"total": 0}
    for subdomain in SUBDOMAIN_ORDER:
        if subdomain not in counts:
            continue
        row = counts[subdomain]
        lines.append(f"| {subdomain} | {row['total']} | {row.get('BODY_UPDATED', 0)} | {row.get('EVIDENCE_ONLY', 0)} | {row.get('NOT_AFFECTED', 0)} | {row.get('RETIRED', 0)} |")
        for key in grand:
            grand[key] += row.get(key, 0)
    lines.append(f"| **TOTAL** | **{grand['total']}** | **{grand.get('BODY_UPDATED', 0)}** | **{grand.get('EVIDENCE_ONLY', 0)}** | **{grand.get('NOT_AFFECTED', 0)}** | **{grand.get('RETIRED', 0)}** |")
    report = "\n".join(lines) + "\n"
    out = (review_root or REVIEW_ROOT) / family / platform / "coverage_report.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report, encoding="utf-8")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("family")
    parser.add_argument("platform")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--record-decision", action="store_true")
    mode.add_argument("--report", action="store_true")
    mode.add_argument("--status", action="store_true")
    parser.add_argument("--path")
    parser.add_argument("--decision", choices=sorted(VALID_DECISIONS))
    parser.add_argument("--reason", default="")
    parser.add_argument("--body-changed", action="store_true")
    parser.add_argument("--review-root", type=Path)
    args = parser.parse_args(argv)
    if args.record_decision:
        if not args.path or not args.decision:
            print("error: --record-decision requires --path and --decision", file=sys.stderr)
            return 1
        record_decision(args.family, args.platform, args.path, args.decision, args.reason, body_hash_changed=args.body_changed, review_root=args.review_root)
        print("decision recorded")
    elif args.report:
        print(generate_coverage_report(args.family, args.platform, review_root=args.review_root))
    else:
        data = load_decisions(args.family, args.platform, review_root=args.review_root)
        print(json.dumps({"pages": len(data.get("pages", {}))}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
