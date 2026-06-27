"""
scan_stale.py — Enumerate all products with stale_since set in their model.yaml.

Iterates all knowledge/*/merged/model.yaml files and collects those where
stale_since is set (non-null). Outputs authoritative stale product list for
the backfill protocol.

IMPORTANT (C-004): This script does NOT exist until WAVE 10 creates it.
stale_since is only set by S-12 (stale_detect / refresh_knowledge.py).
Products with HIGH sweep impact but S-12 not yet run will NOT appear here
until S-12 sets stale_since. Run S-12 first, then run this script.

CLI:
    PYTHONPATH=scripts/pipeline python scripts/pipeline/commands/knowledge/scan_stale.py

Exit codes:
    0 — no stale products found
    1 — one or more stale products found (also prints the list)
"""

from pathlib import Path
import sys

_PIPELINE_ROOT = Path(__file__).resolve().parents[2]
if str(_PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_ROOT))
_LIB_DIR = str(_PIPELINE_ROOT / "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)

import argparse
import yaml
from typing import Any

# ── Configurable defaults ──────────────────────────────────────────────────

_cfg_knowledge_root: str = "knowledge"


def configure(knowledge_root: str | None = None) -> None:
    global _cfg_knowledge_root
    if knowledge_root is not None:
        _cfg_knowledge_root = knowledge_root


# ── Core logic ─────────────────────────────────────────────────────────────

def _find_all_model_yamls(knowledge_root: str) -> list[Path]:
    """Return all knowledge/{family}/{platform}/merged/model.yaml paths."""
    root = Path(knowledge_root)
    return sorted(root.glob("*/*/merged/model.yaml"))


def _is_stale(model_yaml_path: Path) -> tuple[bool, str | None]:
    """
    Return (is_stale, stale_since_value) for a model.yaml file.

    A product is stale if stale_since is a non-null, non-empty string.
    """
    try:
        with open(model_yaml_path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        stale_since = data.get("stale_since")
        if stale_since is not None and str(stale_since).strip():
            return True, str(stale_since)
    except Exception:
        pass
    return False, None


def _parse_product(model_yaml_path: Path, knowledge_root: str) -> dict:
    """Extract family/platform from model.yaml path."""
    # knowledge/{family}/{platform}/merged/model.yaml
    parts = model_yaml_path.relative_to(knowledge_root).parts
    family = parts[0] if len(parts) > 0 else "unknown"
    platform = parts[1] if len(parts) > 1 else "unknown"
    return {"family": family, "platform": platform, "model_yaml": str(model_yaml_path)}


def find_stale_products(knowledge_root: str | None = None) -> list[dict]:
    """
    Main logic: find all stale products.

    Returns list of dicts with {family, platform, stale_since, model_yaml}.
    """
    root = knowledge_root or _cfg_knowledge_root
    model_yamls = _find_all_model_yamls(root)
    stale: list[dict] = []

    for path in model_yamls:
        is_stale, stale_since = _is_stale(path)
        if is_stale:
            product = _parse_product(path, root)
            product["stale_since"] = stale_since
            stale.append(product)

    return stale


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "scan_stale — Enumerate all products with stale_since set in model.yaml. "
            "Outputs authoritative stale product list for backfill protocol."
        ),
        epilog=(
            "Note: stale_since is only set by S-12 (stale_detect). "
            "Products not yet run through S-12 will not appear here."
        ),
    )
    parser.add_argument(
        "--knowledge-root",
        default=None,
        help="Override knowledge/ directory (default: knowledge/)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON instead of human-readable text",
    )
    args = parser.parse_args()

    if args.knowledge_root:
        configure(knowledge_root=args.knowledge_root)

    stale = find_stale_products()

    if args.json:
        import json
        print(json.dumps(stale, indent=2))
    else:
        if not stale:
            print("scan_stale: no stale products found")
            print("  All products are up to date, or S-12 has not been run yet.")
            return 0

        print(f"scan_stale: {len(stale)} stale product(s) found")
        print()
        for p in stale:
            print(f"  {p['family']}/{p['platform']}")
            print(f"    stale_since : {p['stale_since']}")
            print(f"    model_yaml  : {p['model_yaml']}")
            print()

    return 1 if stale else 0


if __name__ == "__main__":
    sys.exit(main())
