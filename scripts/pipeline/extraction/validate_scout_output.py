"""validate_scout_output.py -- Post-scout extraction validation gate.

Detects silent extraction failures by cross-checking scout output (class_count)
against the actual repository contents.  When scout reports 0 classes but the
repo contains class-bearing source files, this module emits an
EXTRACTION_FAILURE verdict instead of silently propagating empty knowledge.

Usage (standalone)::

    python -m extraction.validate_scout_output {model_yaml} {repo_path} {platform}

Usage (library)::

    from extraction.validate_scout_output import validate_scout_output
    result = validate_scout_output(model, repo_path, platform)
    if result["verdict"] == "EXTRACTION_FAILURE":
        ...
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

# Extension sets per platform that can declare classes/structs/types.
_CLASS_BEARING_EXTENSIONS: dict[str, list[str]] = {
    "python": [".py"],
    "csharp": [".cs"],
    "java": [".java"],
    "cpp": [".hpp", ".h", ".cpp"],
    "typescript": [".ts"],
    "javascript": [".js"],
    "go": [".go"],
    "rust": [".rs"],
}

_PLATFORM_TO_LANG: dict[str, str] = {
    "python": "python",
    "net": "csharp",
    "dotnet": "csharp",
    "java": "java",
    "cpp": "cpp",
    "typescript": "typescript",
    "javascript": "javascript",
    "nodejs": "javascript",
    "go": "go",
    "rust": "rust",
}

# Maturity tier thresholds.
_TIERS = [
    ("full",    50, 500),
    ("reduced", 10, 50),
    ("minimal",  1, 10),
]


def _count_class_bearing_files(repo_path: Path, platform: str) -> int:
    """Count source files that could contain class definitions."""
    lang = _PLATFORM_TO_LANG.get(platform, platform)
    exts = _CLASS_BEARING_EXTENSIONS.get(lang, [])
    count = 0
    for ext in exts:
        count += len(list(repo_path.rglob(f"*{ext}"))[:200])
    return count


def classify_tier(class_count: int, claim_count: int | None = None) -> str:
    """Return maturity tier based on class and claim counts.

    When claim_count is unavailable (scout-only models), tier is based on
    class_count alone with an estimated claim count of ~5x classes.
    """
    effective_claims = claim_count if claim_count else class_count * 5
    for tier_name, min_classes, min_claims in _TIERS:
        if class_count >= min_classes and effective_claims >= min_claims:
            return tier_name
    return "skip"


def validate_scout_output(
    model: dict,
    repo_path: Path,
    platform: str,
) -> dict:
    """Validate scout output and return a structured verdict.

    Returns a dict with keys:
        verdict: "OK" | "EXTRACTION_FAILURE" | "PRE_ALPHA"
        tier: "full" | "reduced" | "minimal" | "defer" | "skip"
        class_count: int
        claim_count: int
        class_bearing_files: int (only if class_count == 0)
        message: str
    """
    stats = model.get("stats", {})
    class_count = stats.get("class_count", 0)
    # Claim count lives in different fields depending on scout vs merged model
    claim_count = (stats.get("total_claims")
                   or stats.get("scout_claims")
                   or stats.get("merged_claims")
                   or None)  # None signals "unavailable" to classify_tier

    if class_count > 0:
        tier = classify_tier(class_count, claim_count)
        return {
            "verdict": "OK",
            "tier": tier,
            "class_count": class_count,
            "claim_count": claim_count,
            "message": f"{class_count} classes, {claim_count} claims -> tier: {tier}",
        }

    # class_count == 0: check if repo has class-bearing source files
    class_files = _count_class_bearing_files(repo_path, platform)

    if class_files > 0:
        return {
            "verdict": "EXTRACTION_FAILURE",
            "tier": "defer",
            "class_count": 0,
            "claim_count": claim_count,
            "class_bearing_files": class_files,
            "message": (
                f"Scout produced 0 classes but repo contains {class_files} "
                f"class-bearing source files. Extraction likely failed silently."
            ),
        }

    return {
        "verdict": "PRE_ALPHA",
        "tier": "skip",
        "class_count": 0,
        "claim_count": claim_count,
        "class_bearing_files": 0,
        "message": "Repository contains no class-bearing source files.",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Post-scout extraction validation gate")
    parser.add_argument("model_yaml", type=Path,
                        help="Path to scout model.yaml")
    parser.add_argument("repo_path", type=Path,
                        help="Path to cloned repository")
    parser.add_argument("platform",
                        help="Platform name (e.g. python, net, cpp)")
    parser.add_argument("--json", action="store_true",
                        help="Output as JSON")
    args = parser.parse_args(argv)

    model = yaml.safe_load(args.model_yaml.read_text(encoding="utf-8"))
    result = validate_scout_output(model, args.repo_path, args.platform)

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"VERDICT: {result['verdict']}")
        print(f"TIER: {result['tier']}")
        print(f"MESSAGE: {result['message']}")

    if result["verdict"] == "EXTRACTION_FAILURE":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
