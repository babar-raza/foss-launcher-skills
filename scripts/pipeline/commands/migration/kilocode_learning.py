# Adapted from aspose.org
"""Violation-driven learning: generate learning examples from violations.

This module generates learning examples from compliance violations
to help Kilo Code improve its rule-following behavior.

Usage:
    # Import and use in other scripts
    from kilocode_learning import generate_learning_examples

    examples = generate_learning_examples(violations)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List

_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SCRIPT_DIR.parent.parent.parent.parent


def generate_learning_examples(violations: List[Dict]) -> List[Dict]:
    """Generate learning examples from violations.

    Args:
        violations: List of violation dictionaries with keys:
            - type: Type of violation (e.g., "skill_bypass")
            - violation: Description of the violation
            - request: Original user request
            - action: Wrong action taken
            - correct_action: Correct action that should have been taken

    Returns:
        List of learning example dictionaries with keys:
            - instruction: What to fix
            - context: Original request, wrong action, correct action
            - response: Reasoning for the correct approach
    """
    examples: List[Dict] = []

    for v in violations:
        if v.get("type") == "skill_bypass":
            examples.append({
                "instruction": f"Fix: {v.get('violation', 'Unknown violation')}",
                "context": {
                    "original_request": v.get("request", ""),
                    "wrong_action": v.get("action", ""),
                    "correct_action": v.get("correct_action", "")
                },
                "response": {
                    "reasoning": f"Per AGENTS.md §6a, I must use registered skills. The correct approach is to invoke {v.get('correct_action', '')} instead of {v.get('action', '')}."
                }
            })

    return examples


def load_violations(violations_file: Path | None = None) -> List[Dict]:
    """Load violations from file.

    Args:
        violations_file: Path to violations file. Defaults to reports/kilocode_violations.json

    Returns:
        List of violation dictionaries
    """
    if violations_file is None:
        violations_file = _REPO_ROOT / "reports" / "kilocode" / "violations.json"

    if not violations_file.exists():
        return []

    try:
        with open(violations_file, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return []


def generate_examples_from_file(violations_file: Path | None = None) -> List[Dict]:
    """Generate learning examples from violations in file.

    Args:
        violations_file: Path to violations file. Defaults to reports/kilocode_violations.json

    Returns:
        List of learning example dictionaries
    """
    violations = load_violations(violations_file)
    return generate_learning_examples(violations)


def save_examples(examples: List[Dict], output_file: Path) -> None:
    """Save learning examples to file.

    Args:
        examples: List of learning example dictionaries
        output_file: Path to output file
    """
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(examples, f, indent=2)


def main(argv: list[str] | None = None) -> int:
    import argparse
    parser = argparse.ArgumentParser(
        prog="kilocode_learning",
        description="Generate learning examples from violations."
    )
    parser.add_argument("--input", "-i", help="Input violations file")
    parser.add_argument("--output", "-o", help="Output examples file")
    args = parser.parse_args(argv)

    violations_file = Path(args.input) if args.input else None
    examples = generate_examples_from_file(violations_file)

    if args.output:
        save_examples(examples, Path(args.output))
        print(f"Saved {len(examples)} examples to {args.output}")
    else:
        print(json.dumps(examples, indent=2))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
