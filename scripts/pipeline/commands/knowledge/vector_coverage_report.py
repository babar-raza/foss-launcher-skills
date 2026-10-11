#!/usr/bin/env python3
"""Vector coverage report (TC-VEC-06, RC3).

Cross-references knowledge/_index.json's live product list against
knowledge/_vectors/{family}/{platform}/active.json to show which products
currently have generated vectors -- replacing the hand-maintained table in
docs/pipeline/vector-regeneration-procedure.md, which went stale (listed
products that no longer exist and omitted real ones) because nothing kept it
in sync with the live repo.

Usage:
    .venv/Scripts/python scripts/pipeline/commands/knowledge/vector_coverage_report.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_DEFAULT_KNOWLEDGE_ROOT = Path(__file__).resolve().parents[4] / "knowledge"
_knowledge_root = _DEFAULT_KNOWLEDGE_ROOT


def configure(*, knowledge_root: "Path | str | None" = None) -> None:
    """Override external boundaries for tests; call without arguments to reset."""
    global _knowledge_root
    _knowledge_root = (
        Path(knowledge_root) if knowledge_root is not None else _DEFAULT_KNOWLEDGE_ROOT
    )


def coverage_rows() -> list[dict]:
    """One row per product in knowledge/_index.json, with live vector coverage."""
    index_path = _knowledge_root / "_index.json"
    if not index_path.exists():
        return []
    data = json.loads(index_path.read_text(encoding="utf-8"))
    rows = []
    for entry in data.get("products", []):
        family = entry.get("family", "")
        platform = entry.get("platform", "")
        active_path = _knowledge_root / "_vectors" / family / platform / "active.json"
        rows.append(
            {
                "family": family,
                "platform": platform,
                "has_vectors": active_path.exists(),
            }
        )
    return sorted(rows, key=lambda r: (r["family"], r["platform"]))


def render_markdown_table(rows: list[dict]) -> str:
    lines = ["| Family | Platform | Vectors |", "|--------|----------|---------|"]
    for row in rows:
        status = "yes" if row["has_vectors"] else "MISSING"
        lines.append(f"| {row['family']} | {row['platform']} | {status} |")
    return "\n".join(lines)


def main() -> None:
    rows = coverage_rows()
    if not rows:
        print("No products found in knowledge/_index.json. Run index.py first.")
        sys.exit(1)
    print(render_markdown_table(rows))
    missing = [r for r in rows if not r["has_vectors"]]
    print(f"\n{len(rows)} product(s), {len(missing)} missing vectors.")


if __name__ == "__main__":
    main()
