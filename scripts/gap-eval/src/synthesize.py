#!/usr/bin/env python3
"""Synthesize standalone gap-eval reports into a cross-product summary."""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
SCRIPTS_ROOT = REPO_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from scripts.content_repo_adapter import assert_write_allowed, resolve_output_root  # noqa: E402


def load_all_findings(reports_dir: Path, products: list[str] | None = None) -> list[dict[str, Any]]:
    allowed = {product.replace("/", "-") for product in products or []}
    findings: list[dict[str, Any]] = []
    for path in sorted(reports_dir.glob("*.json")):
        if path.name.endswith("-origin.json") or path.name == "MASTER-SYNTHESIS.json":
            continue
        repo_key = path.stem
        if allowed and repo_key not in allowed:
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        for finding in data.get("findings", []):
            if isinstance(finding, dict) and finding.get("status") not in {"fixed", "wontfix"}:
                findings.append({**finding, "_repo": repo_key})
    return findings


def cluster_findings(findings: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    clusters: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for finding in findings:
        key = str(finding.get("type") or "unknown")
        clusters[key].append(finding)
    return dict(sorted(clusters.items()))


def synthesize(findings: list[dict[str, Any]]) -> dict[str, Any]:
    clusters = cluster_findings(findings)
    severity_counts = Counter(str(finding.get("severity", "?")) for finding in findings)
    repo_counts = Counter(str(finding.get("_repo", "?")) for finding in findings)
    return {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "findings_count": len(findings),
        "severity_counts": dict(sorted(severity_counts.items())),
        "repo_counts": dict(sorted(repo_counts.items())),
        "clusters": {
            name: {
                "count": len(items),
                "repos": sorted({str(item.get("_repo", "?")) for item in items}),
                "sample_ids": [str(item.get("id", "?")) for item in items[:5]],
            }
            for name, items in clusters.items()
        },
    }


def render_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# Gap Analysis Master Synthesis",
        "",
        f"- Generated at: `{summary['generated_at']}`",
        f"- Open findings: `{summary['findings_count']}`",
        "",
        "## Clusters",
        "",
    ]
    for name, cluster in summary["clusters"].items():
        safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "-", name).strip("-") or "unknown"
        lines.extend(
            [
                f"### {safe_name}",
                f"- Count: `{cluster['count']}`",
                f"- Repos: {', '.join(cluster['repos'])}",
                f"- Sample IDs: {', '.join(cluster['sample_ids'])}",
                "",
            ]
        )
    if not summary["clusters"]:
        lines.append("- No open findings discovered.")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reports-dir", type=Path)
    parser.add_argument("--output-root")
    parser.add_argument("--products")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    output_root = resolve_output_root(args.output_root)
    reports_dir = args.reports_dir or (output_root / "gap-analysis")
    products = [item.strip() for item in args.products.split(",") if item.strip()] if args.products else None
    findings = load_all_findings(reports_dir, products)
    summary = synthesize(findings)
    if args.dry_run:
        print(json.dumps(summary, indent=2, sort_keys=True))
        return 0
    md_path = reports_dir / "MASTER-SYNTHESIS.md"
    json_path = reports_dir / "MASTER-SYNTHESIS.json"
    try:
        assert_write_allowed(md_path, dry_run=False)
        assert_write_allowed(json_path, dry_run=False)
        reports_dir.mkdir(parents=True, exist_ok=True)
        md_path.write_text(render_markdown(summary), encoding="utf-8")
        json_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    except Exception as exc:
        print(f"error: failed to write synthesis: {exc}", file=sys.stderr)
        return 1
    print(json_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
