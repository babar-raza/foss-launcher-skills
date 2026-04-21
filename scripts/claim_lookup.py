#!/usr/bin/env python3
"""
claim_lookup.py — Deterministic claim ID resolver from PEF.

Usage:
    python scripts/claim_lookup.py <family> <platform> <api_ref>

Example:
    python scripts/claim_lookup.py email python MapiMessage.from_file
    -> CLM-email-9db99c

Returns:
    Exact match on ClassName.method_name or ClassName alone.
    Exits 0 on match, 1 on no match.
"""
import json
import sys
from pathlib import Path


def lookup(family: str, platform: str, api_ref: str) -> str | None:
    """Return the first claim_id matching api_ref, or None."""
    pef_path = Path(f"evidence/{family}/{platform}/pef.json")
    if not pef_path.exists():
        raise FileNotFoundError(f"PEF not found: {pef_path}. Run materialize first.")

    pef = json.loads(pef_path.read_text())
    claims = pef.get("claims", [])

    # Normalize: "MapiMessage.from_file" → class_part="MapiMessage", method_part="from_file"
    parts = api_ref.split(".", 1)
    class_part = parts[0]
    method_part = parts[1] if len(parts) > 1 else None

    # First pass: exact substring match on full api_ref
    for claim in claims:
        text = claim.get("text", "")
        if api_ref in text:
            return claim["claim_id"]

    # Second pass: class match only (for property-style refs)
    if method_part is None:
        for claim in claims:
            text = claim.get("text", "")
            if class_part in text:
                return claim["claim_id"]

    return None


def main() -> int:
    if len(sys.argv) != 4:
        print(f"Usage: {sys.argv[0]} <family> <platform> <api_ref>", file=sys.stderr)
        return 2

    family, platform, api_ref = sys.argv[1], sys.argv[2], sys.argv[3]
    try:
        claim_id = lookup(family, platform, api_ref)
    except FileNotFoundError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    if claim_id:
        print(claim_id)
        return 0
    else:
        print(f"NOT FOUND: {api_ref}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
