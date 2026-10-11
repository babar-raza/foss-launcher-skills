"""skill_seekers_adapter.py — Advisory adapter for Skill Seekers signals.

Reads Skill Seekers output (if available) and converts it into ExternalSignal
objects. All signals are advisory-only and never override source facts.

Usage:
    python scripts/pipeline/commands/knowledge/skill_seekers_adapter.py {family} {platform} \\
        [--input PATH] [--output PATH]

If Skill Seekers is not installed, the adapter produces an empty SignalBatch
with a warning.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# --- Pipeline bootstrap ---
_PIPELINE_ROOT = Path(__file__).resolve().parents[2]
if str(_PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_ROOT))

from lib.external_signals import ExternalSignal, SignalBatch


def _try_import_skill_seekers() -> bool:
    """Check if skill_seekers is available."""
    try:
        import skill_seekers  # noqa: F401
        return True
    except ImportError:
        return False


def parse_skill_seekers_output(data: dict, family: str, platform: str) -> SignalBatch:
    """Convert Skill Seekers JSON output to a SignalBatch.

    Expected input format (from Skill Seekers README analysis):
    {
        "findings": [
            {
                "type": "readme_feature" | "doc_code_conflict" | "coverage_gap",
                "description": "...",
                "file": "...",
                "confidence": 0.0-1.0
            }
        ]
    }
    """
    batch = SignalBatch(
        family=family,
        platform=platform,
        source="skill_seekers",
    )

    findings = data.get("findings", data.get("results", []))
    if isinstance(findings, list):
        for finding in findings:
            signal_type = finding.get("type", finding.get("signal_type", "unknown"))
            text = finding.get("description", finding.get("text", ""))
            if not text:
                continue
            batch.add_signal(ExternalSignal(
                signal_type=signal_type,
                text=text,
                source="skill_seekers",
                source_file=finding.get("file", finding.get("source_file", "")),
                confidence=min(float(finding.get("confidence", 0.5)), 0.8),
                advisory=True,
            ))

    return batch


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Convert Skill Seekers output to advisory ExternalSignals.",
    )
    parser.add_argument("family", help="Product family")
    parser.add_argument("platform", help="Platform")
    parser.add_argument("--input", "-i", help="Path to Skill Seekers JSON output")
    parser.add_argument("--output", "-o", help="Output path for signals JSON (default: stdout)")
    parser.add_argument("--quiet", "-q", action="store_true")
    args = parser.parse_args(argv)

    if args.input:
        input_path = Path(args.input)
        if not input_path.exists():
            print(f"ERROR: Input file not found: {input_path}", file=sys.stderr)
            return 1
        data = json.loads(input_path.read_text(encoding="utf-8"))
        batch = parse_skill_seekers_output(data, args.family, args.platform)
    else:
        if not _try_import_skill_seekers():
            if not args.quiet:
                print("WARNING: skill_seekers not installed — producing empty batch", file=sys.stderr)
        batch = SignalBatch(family=args.family, platform=args.platform, source="skill_seekers")

    json_out = batch.to_json()

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json_out, encoding="utf-8")
        if not args.quiet:
            print(f"Wrote {out_path} ({batch.signal_count} signals)", file=sys.stderr)
    else:
        print(json_out)

    return 0


if __name__ == "__main__":
    sys.exit(main())
