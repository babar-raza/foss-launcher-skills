# Adapted from aspose.org scripts/ci/checks/ for standalone use
"""generate_proof_bundle.py — Create a machine-readable proof bundle for governance events.

Writes a JSON proof bundle to reports/proof-bundles/ and updates reports/proof-index.json.

Usage:
  python scripts/ci/checks/generate_proof_bundle.py \\
    --event skill_chain_execution \\
    --slug family-sync-2026-03-31 \\
    --skills S-48,S-23,S-01 \\
    --result PASS_WITH_DEVIATIONS \\
    --agent "claude-sonnet-4-6" \\
    --work-commit 56b2efa3b \\
    --artifacts reports/compliance/2026-03-31-family-sync-observation.md \\
    --deviations "DEV-001:S-01 invoked inline not as skill:minor:output correct process non-compliant"

Event types:
  skill_chain_execution   — skill chain was run for a content task
  compliance_observation  — governance deviation or compliance finding recorded
  override_grant          — protected-path write permitted via override
  dar_assessment          — DAR capability classification was performed
  observability_postmortem — retrospective review of a past claim's accuracy
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(os.environ.get("REPO_ROOT", Path(__file__).resolve().parent.parent.parent.parent))
BUNDLES_DIR = REPO_ROOT / "reports" / "proof-bundles"
INDEX_FILE = REPO_ROOT / "reports" / "proof-index.json"

VALID_EVENTS = {
    "skill_chain_execution",
    "compliance_observation",
    "override_grant",
    "dar_assessment",
    "observability_postmortem",
}

VALID_RESULTS = {
    "PASS",
    "PASS_WITH_DEVIATIONS",
    "FAIL",
    "PARTIAL",
    "BLOCKED",
}


def parse_deviation(dev_str: str) -> dict:
    """Parse 'id:description:severity:impact' into a deviation dict."""
    parts = dev_str.split(":", 3)
    if len(parts) < 2:
        return {"deviation_id": "DEV-???", "description": dev_str, "severity": "unknown", "impact": ""}
    return {
        "deviation_id": parts[0],
        "description": parts[1],
        "severity": parts[2] if len(parts) > 2 else "unknown",
        "impact": parts[3] if len(parts) > 3 else "",
    }


def load_index() -> list[dict]:
    if INDEX_FILE.exists():
        try:
            with INDEX_FILE.open("r", encoding="utf-8") as fh:
                return json.load(fh)
        except (json.JSONDecodeError, OSError):
            return []
    return []


def save_index(entries: list[dict]) -> None:
    INDEX_FILE.parent.mkdir(parents=True, exist_ok=True)
    with INDEX_FILE.open("w", encoding="utf-8") as fh:
        json.dump(entries, fh, indent=2, ensure_ascii=False)
        fh.write("\n")


def generate_bundle(
    event: str,
    slug: str,
    skills: list[str],
    result: str,
    agent: str,
    work_commit_sha: str | None,
    artifacts: list[str],
    deviations: list[dict],
    extra_fields: dict | None = None,
) -> Path:
    """Write the proof bundle and update the index. Returns the bundle path."""
    BUNDLES_DIR.mkdir(parents=True, exist_ok=True)

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    date_prefix = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    bundle_filename = f"{date_prefix}-{slug}.json"
    bundle_path = BUNDLES_DIR / bundle_filename

    bundle: dict = {
        "schema_version": "1.0",
        "event_type": event,
        "recorded_at": now,
        "agent": agent,
        "work_commit_sha": work_commit_sha,
        "skill_chain": skills,
        "deviations": deviations,
        "result": result,
        "artifacts": artifacts,
    }
    if extra_fields:
        bundle.update(extra_fields)

    with bundle_path.open("w", encoding="utf-8") as fh:
        json.dump(bundle, fh, indent=2, ensure_ascii=False)
        fh.write("\n")

    # Update index
    index = load_index()
    index_entry = {
        "bundle_file": f"reports/proof-bundles/{bundle_filename}",
        "event_type": event,
        "recorded_at": now,
        "work_commit_sha": work_commit_sha,
        "result": result,
        "skills": skills,
        "slug": slug,
    }
    # Remove any existing entry for this slug
    index = [e for e in index if e.get("slug") != slug]
    index.append(index_entry)
    save_index(index)

    return bundle_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="generate_proof_bundle",
        description="Create a machine-readable proof bundle for a governance event.",
    )
    parser.add_argument("--event", required=True, choices=sorted(VALID_EVENTS))
    parser.add_argument("--slug", required=True, help="Short identifier for the bundle filename (no spaces)")
    parser.add_argument("--skills", default="", help="Comma-separated skill IDs, e.g. S-48,S-23,S-01")
    parser.add_argument("--result", required=True, choices=sorted(VALID_RESULTS))
    parser.add_argument("--agent", default="claude-sonnet-4-6")
    parser.add_argument("--work-commit", dest="work_commit", default=None,
                        help="Commit SHA of the work this proof describes")
    parser.add_argument("--artifacts", nargs="*", default=[],
                        help="Paths to related artifact files")
    parser.add_argument("--deviations", nargs="*", default=[],
                        help="Deviation strings in format 'id:description:severity:impact'")
    args = parser.parse_args(argv)

    skills = [s.strip() for s in args.skills.split(",") if s.strip()] if args.skills else []
    deviations = [parse_deviation(d) for d in args.deviations] if args.deviations else []

    bundle_path = generate_bundle(
        event=args.event,
        slug=args.slug,
        skills=skills,
        result=args.result,
        agent=args.agent,
        work_commit_sha=args.work_commit,
        artifacts=args.artifacts or [],
        deviations=deviations,
    )

    print(f"Proof bundle written: {bundle_path.relative_to(REPO_ROOT)}")
    print(f"Index updated: {INDEX_FILE.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
