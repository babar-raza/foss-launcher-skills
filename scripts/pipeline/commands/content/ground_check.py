"""Ground check — S-23 grounding ratio gate.

Extracts all backtick API identifiers from a content page and measures
what fraction are verifiable against the product knowledge model
(classes, methods, properties, enum members in api_surface.json).

Usage:
    python scripts/pipeline/commands/content/ground_check.py {family} {platform} {content_file}

Exit codes:
    0  PASS  -- grounding ratio >= 80%
    1  WARN  -- grounding ratio 60-79%
    2  FAIL  -- grounding ratio < 60%  (or missing knowledge / file)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
_DEFAULT_REPO_ROOT = _SCRIPT_DIR.parent.parent.parent.parent
_REPO_ROOT = _DEFAULT_REPO_ROOT
KNOWLEDGE_ROOT = _REPO_ROOT / "knowledge"


def configure(*, repo_root: "Path | str | None" = None, knowledge_root: "Path | str | None" = None) -> None:
    """Override module-level path constants for testing."""
    global _REPO_ROOT, KNOWLEDGE_ROOT
    _REPO_ROOT = Path(repo_root) if repo_root is not None else _DEFAULT_REPO_ROOT
    KNOWLEDGE_ROOT = Path(knowledge_root) if knowledge_root is not None else _REPO_ROOT / "knowledge"

PASS_THRESHOLD = 0.80
WARN_THRESHOLD = 0.60

# Match backtick identifiers: `ClassName`, `ClassName.method_name`, `method_name`
_IDENTIFIER_RE = re.compile(r"`(\w+(?:\.\w+)*)`")

# Strip YAML frontmatter (first --- ... --- block)
_FRONTMATTER_RE = re.compile(r"^---\n.*?\n---\n?", re.DOTALL)


def _build_known_identifiers(api_surface: list[dict]) -> set[str]:
    """Build a lowercase set of all known identifiers from api_surface.json."""
    known: set[str] = set()
    for cls in api_surface:
        name = cls.get("name", "")
        if name:
            known.add(name.lower())
        for method in cls.get("methods", []) + cls.get("method_details", []):
            m = method.get("name", "")
            if m:
                known.add(m.lower())
        for prop in cls.get("properties", []) + cls.get("property_details", []):
            p = prop.get("name", "")
            if p:
                known.add(p.lower())
        for em in cls.get("enum_members", []):
            e = em.get("name", "")
            if e:
                known.add(e.lower())
    return known


def compute_grounding_ratio(
    content_file: Path,
    api_surface_path: Path,
) -> tuple[float, int, int, list[str]]:
    """Compute grounding ratio for a content file.

    Returns:
        (ratio, matched, total, ungrounded_identifiers)
        When no identifiers are found: (1.0, 0, 0, []) — treated as PASS.

    Raises:
        FileNotFoundError: if api_surface_path does not exist.
    """
    if not api_surface_path.exists():
        raise FileNotFoundError(f"api_surface.json not found: {api_surface_path}")

    api_data = json.loads(api_surface_path.read_text(encoding="utf-8"))
    known = _build_known_identifiers(api_data)

    text = content_file.read_text(encoding="utf-8")
    body = _FRONTMATTER_RE.sub("", text, count=1)

    identifiers = _IDENTIFIER_RE.findall(body)
    if not identifiers:
        return 1.0, 0, 0, []

    ungrounded: list[str] = []
    matched = 0
    for ident in identifiers:
        parts = ident.lower().split(".")
        if any(p in known for p in parts):
            matched += 1
        else:
            ungrounded.append(ident)

    total = len(identifiers)
    ratio = matched / total
    return ratio, matched, total, ungrounded


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="ground_check",
        description="S-23 grounding ratio gate — verify content identifiers against knowledge model",
    )
    parser.add_argument("family", help="Product family (e.g. cells, slides, 3d)")
    parser.add_argument("platform", help="Platform (e.g. python, net, java)")
    parser.add_argument("content_file", help="Content file to check")
    args = parser.parse_args(argv)

    content_file = Path(args.content_file)
    if not content_file.exists():
        print(f"GROUND_CHECK: ERROR -- file not found: {content_file}", file=sys.stderr)
        return 2

    api_surface_path = KNOWLEDGE_ROOT / args.family / args.platform / "merged" / "api_surface.json"

    try:
        ratio, matched, total, ungrounded = compute_grounding_ratio(content_file, api_surface_path)
    except FileNotFoundError as exc:
        print(f"GROUND_CHECK: FAIL -- {exc}", file=sys.stderr)
        return 2

    if total == 0:
        print("GROUND_CHECK: PASS (no backtick identifiers found -- no grounding required)")
        return 0

    pct = f"{ratio:.0%}"
    if ratio >= PASS_THRESHOLD:
        print(f"GROUND_CHECK: PASS ({pct}) -- {matched}/{total} identifiers grounded")
        return 0
    elif ratio >= WARN_THRESHOLD:
        print(f"GROUND_CHECK: WARN ({pct}) -- {matched}/{total} identifiers grounded")
        if ungrounded:
            sample = ", ".join(f"`{u}`" for u in ungrounded[:10])
            print(f"  Ungrounded: {sample}")
        return 1
    else:
        print(
            f"GROUND_CHECK: FAIL ({pct}) -- {matched}/{total} identifiers grounded, "
            f"{len(ungrounded)} ungrounded"
        )
        if ungrounded:
            sample = ", ".join(f"`{u}`" for u in ungrounded[:20])
            print(f"  Ungrounded: {sample}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
