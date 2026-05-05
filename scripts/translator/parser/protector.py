"""
Placeholder protect/restore for Hugo markdown body content.

Replaces protected regions (shortcodes, code fences, inline code, URLs)
with placeholder tokens before translation, then restores them after.

Invariant: all placeholder tokens must be present after translation.
If any are missing, PlaceholderLeakError is raised.
"""
from __future__ import annotations
import re
import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from translator import PlaceholderLeakError


def protect(text: str, patterns: list[dict], placeholder_format: str = "⟦PH_{index:04d}⟧") -> tuple[str, dict[str, str]]:
    """
    Replace all protected regions in text with placeholder tokens.

    Returns:
        (protected_text, placeholder_map) where placeholder_map maps token → original
    """
    placeholder_map: dict[str, str] = {}
    counter = [0]

    def make_token() -> str:
        tok = placeholder_format.format(index=counter[0])
        counter[0] += 1
        return tok

    def replacer(match_obj):
        original = match_obj.group(0)
        tok = make_token()
        placeholder_map[tok] = original
        return tok

    result = text
    for pattern_def in patterns:
        pattern_str = pattern_def.get("pattern", "")
        flags_val = pattern_def.get("flags", 0)
        if not pattern_str:
            continue
        try:
            compiled = re.compile(pattern_str, flags_val)
            result = compiled.sub(replacer, result)
        except re.error:
            # Skip invalid patterns silently (log in production)
            continue

    return result, placeholder_map


def restore(text: str, placeholder_map: dict[str, str]) -> str:
    """
    Restore placeholder tokens back to their original content.
    Raises PlaceholderLeakError if any placeholder is missing from text.
    """
    result = text
    missing = []

    for token, original in placeholder_map.items():
        if token in result:
            result = result.replace(token, original)
        else:
            missing.append(token)

    if missing:
        raise PlaceholderLeakError(
            f"Translation lost {len(missing)} placeholder(s): {missing[:3]}"
        )

    return result


def check_no_placeholders(text: str) -> bool:
    """Return True if no placeholder tokens remain in text."""
    return "⟦PH_" not in text
