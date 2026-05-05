"""Update data/products.json by scanning the GitHub org and local knowledge dirs.

Usage:
    python scripts/pipeline/update_product_registry.py [--token TOKEN] [--force]
    python scripts/pipeline/update_product_registry.py --local-only

Modes:
    Default:      Scan GitHub org for FOSS repos, merge with local knowledge dirs.
    --local-only: Skip GitHub — build registry from knowledge/ dirs only.
    --force:      Overwrite active/inactive status even for repos already in registry.

Output:
    data/products.json — canonical product registry

Schema:
    [
      {
        "family": "3d",
        "platform": "python",
        "repo_name": "aspose-3d-python",
        "repo_url": "https://github.com/aspose-free/aspose-3d-python",
        "clone_url": "https://github.com/aspose-free/aspose-3d-python.git",
        "active": true,
        "discovered_via": "github"
      },
      ...
    ]

Environment:
    GITHUB_TOKEN  GitHub personal access token (alternative to --token).
    ASPOSE_ORG    Comma-separated GitHub organisations to scan
                  (default: aspose-3d-foss,aspose-slides-foss,aspose-cells-foss,
                            aspose-note-foss,aspose-email-foss).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
KNOWLEDGE_ROOT = REPO_ROOT / "knowledge"
DATA_DIR = REPO_ROOT / "data"
REGISTRY_PATH = DATA_DIR / "products.json"

# Repos pushed within this many days are considered "active"
_ACTIVE_PUSH_DAYS = 180

# Orgs to scan — comma-separated, overrideable via ASPOSE_ORG env var
_DEFAULT_ORGS = [
    "aspose-3d-foss",
    "aspose-slides-foss",
    "aspose-cells-foss",
    "aspose-note-foss",
    "aspose-email-foss",
]

# Pattern: Aspose.{Family}-FOSS-for-{Platform}  (e.g. Aspose.3D-FOSS-for-Python)
# Also accepts legacy: aspose-{family}-{platform}
_REPO_PATTERN_FOSS = re.compile(
    r"^Aspose\.([A-Za-z0-9]+)-FOSS-for-([A-Za-z0-9.]+)$"
)
_REPO_PATTERN_LEGACY = re.compile(r"^aspose-([a-z0-9]+)-([a-z0-9]+)$")

# Normalise platform name to internal identifier
_PLATFORM_MAP = {
    "python": "python",
    "java": "java",
    ".net": "dotnet",
    "net": "dotnet",
    "cpp": "cpp",
    "typescript": "typescript",
    "javascript": "javascript",
    "nodejs": "nodejs",
}


# ---------------------------------------------------------------------------
# Repo name → (family, platform)
# ---------------------------------------------------------------------------

def _classify_repo(repo_name: str) -> tuple[str, str] | None:
    """Extract (family, platform) from a repo name.

    Supports two naming conventions:
    - New:    Aspose.{Family}-FOSS-for-{Platform}  (e.g. Aspose.3D-FOSS-for-Python)
    - Legacy: aspose-{family}-{platform}            (e.g. aspose-3d-python)

    Returns None when the name does not match either pattern.
    """
    # New convention: Aspose.3D-FOSS-for-Python
    m = _REPO_PATTERN_FOSS.match(repo_name)
    if m:
        family = m.group(1).lower()  # "3D" → "3d"
        platform_raw = m.group(2).lower()  # "Python" → "python", ".NET" → ".net"
        platform = _PLATFORM_MAP.get(platform_raw, platform_raw)
        return family, platform

    # Legacy convention: aspose-3d-python
    m = _REPO_PATTERN_LEGACY.match(repo_name.lower())
    if m:
        return m.group(1), m.group(2)

    return None


# ---------------------------------------------------------------------------
# Discover products from local knowledge/ directory tree
# ---------------------------------------------------------------------------

def _discover_from_knowledge() -> list[dict]:
    """Return products discovered from knowledge/{family}/{platform}/merged/model.yaml."""
    products: list[dict] = []
    if not KNOWLEDGE_ROOT.is_dir():
        return products
    for family_dir in sorted(KNOWLEDGE_ROOT.iterdir()):
        if not family_dir.is_dir() or family_dir.name.startswith(("_", "{")):
            continue
        family = family_dir.name
        for platform_dir in sorted(family_dir.iterdir()):
            if not platform_dir.is_dir():
                continue
            platform = platform_dir.name
            products.append(
                {
                    "family": family,
                    "platform": platform,
                    "repo_name": f"aspose-{family}-{platform}",
                    "repo_url": "",
                    "clone_url": "",
                    "active": True,
                    "discovered_via": "knowledge_dir",
                }
            )
    return products


# ---------------------------------------------------------------------------
# Discover products from GitHub
# ---------------------------------------------------------------------------

def _is_recently_pushed(pushed_at: str, days: int = _ACTIVE_PUSH_DAYS) -> bool:
    if not pushed_at:
        return False
    try:
        dt = datetime.fromisoformat(pushed_at.replace("Z", "+00:00"))
        age = datetime.now(tz=timezone.utc) - dt
        return age.days <= days
    except ValueError:
        return False


def _discover_from_github(orgs: list[str], token: str | None) -> list[dict]:
    """Return products discovered by scanning one or more GitHub orgs."""
    try:
        from org_scanner import scan_orgs  # noqa: PLC0415  (local import)
    except ImportError:
        # Try absolute import when running from repo root
        sys.path.insert(0, str(Path(__file__).parent))
        from org_scanner import scan_orgs  # type: ignore[no-redef]

    products: list[dict] = []
    repos = scan_orgs(orgs, token=token)
    for repo in repos:
        pair = _classify_repo(repo["name"])
        if pair is None:
            continue
        family, platform = pair
        active = not repo["archived"] and _is_recently_pushed(repo.get("pushed_at", ""))
        products.append(
            {
                "family": family,
                "platform": platform,
                "repo_name": repo["name"],
                "repo_url": repo["html_url"],
                "clone_url": repo["clone_url"],
                "active": active,
                "discovered_via": "github",
            }
        )
    return products


# ---------------------------------------------------------------------------
# Merge strategy
# ---------------------------------------------------------------------------

def _key(entry: dict) -> tuple[str, str]:
    return (entry["family"], entry["platform"])


def _merge(existing: list[dict], incoming: list[dict], force: bool) -> list[dict]:
    """Merge *incoming* entries into *existing* registry.

    - GitHub entries (discovered_via=github) take precedence over knowledge_dir entries.
    - When *force* is True, active/inactive status is always overwritten.
    - When *force* is False, existing active=True entries are preserved.
    """
    registry: dict[tuple, dict] = {_key(e): e for e in existing}

    for entry in incoming:
        k = _key(entry)
        if k not in registry:
            registry[k] = entry
        else:
            prev = registry[k]
            # GitHub source always wins for URL / repo metadata
            if entry["discovered_via"] == "github":
                registry[k] = {
                    **prev,
                    "repo_name": entry["repo_name"],
                    "repo_url": entry["repo_url"],
                    "clone_url": entry["clone_url"],
                    "discovered_via": "github",
                }
                if force or not prev.get("active"):
                    registry[k]["active"] = entry["active"]
            elif force:
                registry[k]["active"] = entry["active"]

    # Sort by family then platform for stable output
    return sorted(registry.values(), key=lambda e: (e["family"], e["platform"]))


# ---------------------------------------------------------------------------
# Atomic write
# ---------------------------------------------------------------------------

def _write_atomic(path: Path, data: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_fd, tmp_path = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
        Path(tmp_path).replace(path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    _env_orgs = os.environ.get("ASPOSE_ORG", "")
    _default_orgs_str = ",".join(_env_orgs.split(",") if _env_orgs else _DEFAULT_ORGS)
    parser.add_argument("--token", help="GitHub PAT (falls back to GITHUB_TOKEN env var)")
    parser.add_argument("--org", default=_default_orgs_str,
                        help="Comma-separated GitHub organisations to scan (default: %(default)s)")
    parser.add_argument("--local-only", action="store_true",
                        help="Skip GitHub — build registry from knowledge/ dirs only")
    parser.add_argument("--force", action="store_true",
                        help="Overwrite active status for existing entries")
    args = parser.parse_args(argv)

    token = args.token or os.environ.get("GITHUB_TOKEN")
    orgs = [o.strip() for o in args.org.split(",") if o.strip()]

    # Load existing registry (if any)
    existing: list[dict] = []
    if REGISTRY_PATH.is_file():
        try:
            existing = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            print(f"WARN: could not read existing registry: {exc}", file=sys.stderr)

    # Discover products
    incoming: list[dict] = []

    if not args.local_only:
        print(f"Scanning GitHub orgs: {orgs}…", file=sys.stderr)
        try:
            github_products = _discover_from_github(orgs, token)
            incoming.extend(github_products)
            print(f"  Found {len(github_products)} repos matching aspose-{{family}}-{{platform}}",
                  file=sys.stderr)
        except Exception as exc:  # noqa: BLE001
            print(f"WARN: GitHub scan failed ({exc}); falling back to local-only", file=sys.stderr)

    # Always add knowledge_dir entries as fallback for anything not on GitHub
    kd_products = _discover_from_knowledge()
    incoming.extend(kd_products)
    print(f"  Found {len(kd_products)} products in knowledge/ dirs", file=sys.stderr)

    # Merge
    merged = _merge(existing, incoming, force=args.force)

    # Write
    _write_atomic(REGISTRY_PATH, merged)
    print(f"OK  Wrote {len(merged)} products to {REGISTRY_PATH.relative_to(REPO_ROOT)}",
          file=sys.stderr)

    # Summary
    active = sum(1 for e in merged if e.get("active"))
    print(f"    active={active}  inactive={len(merged) - active}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
