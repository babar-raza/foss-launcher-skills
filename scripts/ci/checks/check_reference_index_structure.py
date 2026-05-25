#!/usr/bin/env python3
"""
Reference index structure validator for reference.aspose.org.

Scans reference platform _index.md files and warns when a flat
``{{< children >}}`` shortcode is used as the only body content
while a sufficiently large api_surface.json exists that could
provide grouped tables.

Exit code: 0 if clean, 1 if warnings found, 2 if setup error.

Usage:
    python scripts/ci/checks/check_reference_index_structure.py
"""
import json
import re
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
_REF_CONTENT = _REPO_ROOT / "content" / "reference.aspose.org" / "en"
_KNOWLEDGE_ROOT = _REPO_ROOT / "knowledge"
_MIN_API_ENTRIES = 5


def _extract_body(text: str) -> str:
    """Return markdown body after YAML frontmatter."""
    if text.startswith("---"):
        end = text.find("---", 3)
        if end != -1:
            return text[end + 3:].strip()
    return text.strip()


def _is_flat(body: str) -> bool:
    """Return True if the body is essentially just {{< children >}}."""
    # Strip whitespace and common decorations
    stripped = re.sub(r"##\s*See Also.*", "", body, flags=re.DOTALL).strip()
    # Check if what remains is only the children shortcode + optional intro paragraph
    lines = [l.strip() for l in stripped.splitlines() if l.strip()]
    content_lines = [l for l in lines if not l.startswith("{{<") and not l.startswith("Browse all")]
    has_h2 = any(l.startswith("## ") for l in lines)
    has_table = any(l.startswith("|") for l in lines)
    if has_h2 and has_table:
        return False  # Has grouped content
    return "{{< children" in stripped


def _is_manually_curated(text: str) -> bool:
    """Check if the page was manually curated (should not be auto-healed)."""
    return bool(re.search(r"last_mechanism:\s*(manual-edit-skill|human-edit|agent-edit)", text))


def run() -> int:
    """Run the validator. Returns exit code."""
    if not _REF_CONTENT.is_dir():
        print(f"ERROR: Reference content root not found: {_REF_CONTENT}", file=sys.stderr)
        return 2

    warnings = []
    checked = 0

    for family_dir in sorted(_REF_CONTENT.iterdir()):
        if not family_dir.is_dir():
            continue
        family = family_dir.name
        for plat_dir in sorted(family_dir.iterdir()):
            if not plat_dir.is_dir():
                continue
            platform = plat_dir.name
            index_path = plat_dir / "_index.md"
            if not index_path.exists():
                continue

            checked += 1
            text = index_path.read_text(encoding="utf-8")
            body = _extract_body(text)

            if not _is_flat(body):
                continue  # Already grouped or has rich content

            if _is_manually_curated(text):
                continue  # Manually curated — skip

            # Check if api_surface exists with enough entries
            api_path = _KNOWLEDGE_ROOT / family / platform / "merged" / "api_surface.json"
            if not api_path.exists():
                continue  # No knowledge — flat is the only option

            try:
                api = json.loads(api_path.read_text(encoding="utf-8"))
            except Exception:
                continue

            if len(api) < _MIN_API_ENTRIES:
                continue  # Too small to group

            warnings.append({
                "family": family,
                "platform": platform,
                "path": str(index_path.relative_to(_REPO_ROOT)),
                "api_count": len(api),
                "api_path": str(api_path.relative_to(_REPO_ROOT)),
            })

    if warnings:
        print(f"WARN: {len(warnings)} reference index page(s) use flat "
              f"{{{{< children >}}}} when grouped metadata is available:")
        print()
        for w in warnings:
            print(f"  {w['family']}/{w['platform']}: "
                  f"{w['api_count']} API entries available")
            print(f"    Path:   {w['path']}")
            print(f"    Fix:    .venv/Scripts/python scripts/pipeline/commands/content/"
                  f"batch_reference.py {w['family']} {w['platform']} --generate-index")
            print()
        print(f"Checked: {checked} reference roots")
        print(f"Flat with metadata: {len(warnings)}")
        return 1

    print(f"OK: {checked} reference index pages checked, all have appropriate structure.")
    return 0


if __name__ == "__main__":
    sys.exit(run())
