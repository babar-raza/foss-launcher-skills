"""Auto-refresh knowledge from clone cache when stale.

Compares repo HEAD in the clone cache against the repo_sha recorded in
knowledge/{family}/{platform}/merged/model.yaml.  When they differ (or
merged/ does not exist yet), runs scripts/scout.py then scripts/merge.py to rebuild.

Usage:
    python scripts/pipeline/refresh_knowledge.py {family} {platform}
    python scripts/pipeline/refresh_knowledge.py --all
    python scripts/pipeline/refresh_knowledge.py --check {family} {platform}

Environment:
    ASPOSE_CLONE_CACHE  Override the default clone-cache location.
                        Defaults to runs/.clone_cache inside this repo.

Auto-clone behaviour (default on):
    When the clone cache directory for a product is missing, refresh_knowledge
    looks up clone_url in data/products.json and runs `git clone --depth 1`.
    Disable with --no-auto-clone or by keeping clone_url empty in products.json.
    Populate clone_url by running: python scripts/pipeline/update_product_registry.py --token $GITHUB_TOKEN
"""
import argparse
import json
import os
import site
import subprocess
import sys
import yaml
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
KNOWLEDGE_ROOT = REPO_ROOT / "knowledge"
_REGISTRY_PATH = REPO_ROOT / "data" / "products.json"

# Clone-cache location (single canonical path inside this repo).
_CANDIDATE_CACHE_PATHS = [
    REPO_ROOT / "runs" / ".clone_cache",
]


def _clone_cache_root() -> Path:
    env = os.environ.get("ASPOSE_CLONE_CACHE")
    if env:
        return Path(env).resolve()
    for candidate in _CANDIDATE_CACHE_PATHS:
        resolved = candidate.resolve()
        if resolved.is_dir():
            return resolved
    # Fall back to the first candidate even if it doesn't exist
    return _CANDIDATE_CACHE_PATHS[0].resolve()


def _clone_dir(family: str, platform: str) -> Path:
    return _clone_cache_root() / f"aspose_{family}_{platform}"


def _head_sha(clone_path: Path) -> str | None:
    """Return the full HEAD sha of the cloned repo, or None."""
    if not clone_path.is_dir():
        return None
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(clone_path),
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return None


def _model_sha(family: str, platform: str) -> str | None:
    """Return repo_sha from merged/model.yaml, falling back to scout/."""
    for layer in ("merged", "scout"):
        path = KNOWLEDGE_ROOT / family / platform / layer / "model.yaml"
        if path.exists():
            try:
                data = yaml.safe_load(path.read_text(encoding="utf-8"))
                if data and data.get("repo_sha"):
                    return data["repo_sha"]
            except Exception:
                pass
    return None


def _run(cmd: list[str], label: str) -> bool:
    print(f"  [{label}] {' '.join(cmd)}")
    env = os.environ.copy()
    # Propagate user site-packages so tree_sitter_language_pack and other
    # user-installed packages are found when invoking subprocesses via sys.executable.
    user_site = site.getusersitepackages()
    if user_site and os.path.isdir(user_site):
        env["PYTHONPATH"] = user_site + os.pathsep + env.get("PYTHONPATH", "")
    result = subprocess.run(cmd, cwd=str(REPO_ROOT), env=env)
    if result.returncode != 0:
        print(f"  [{label}] FAILED (exit {result.returncode})")
        return False
    return True


def _try_auto_clone(family: str, platform: str, clone_dir: Path) -> bool:
    """Clone the product repo into clone_dir if clone_url is available in products.json.

    Returns True if the clone succeeds, False otherwise.
    """
    if not _REGISTRY_PATH.is_file():
        return False
    try:
        registry = json.loads(_REGISTRY_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return False

    clone_url = ""
    for entry in registry:
        if entry.get("family") == family and entry.get("platform") == platform:
            clone_url = entry.get("clone_url", "")
            break

    if not clone_url:
        return False

    print(f"  {family}/{platform}: auto-cloning from {clone_url}")
    clone_dir.parent.mkdir(parents=True, exist_ok=True)
    try:
        result = subprocess.run(
            ["git", "clone", "--depth", "1", clone_url, str(clone_dir)],
            capture_output=False,
            timeout=300,
        )
        return result.returncode == 0
    except Exception as exc:
        print(f"  {family}/{platform}: auto-clone failed — {exc}")
        return False


def refresh(family: str, platform: str, *, check_only: bool = False, auto_clone: bool = True) -> str:
    """Refresh knowledge for one product.

    Returns one of: "current", "refreshed", "no_clone", "failed".

    When auto_clone=True (default), attempts to clone the repo from clone_url
    in data/products.json if the clone cache directory is missing.
    """
    clone = _clone_dir(family, platform)
    head = _head_sha(clone)
    if head is None:
        if auto_clone and not check_only:
            cloned = _try_auto_clone(family, platform, clone)
            if cloned:
                head = _head_sha(clone)
        if head is None:
            print(f"  {family}/{platform}: clone cache not found at {clone}")
            return "no_clone"

    current = _model_sha(family, platform)
    if current == head:
        print(f"  {family}/{platform}: knowledge is current ({head[:10]})")
        return "current"

    print(f"  {family}/{platform}: STALE — model={current and current[:10]} vs clone={head[:10]}")

    if check_only:
        return "stale"

    scout_out = KNOWLEDGE_ROOT / family / platform / "scout"
    ok = _run(
        [sys.executable, "scripts/scout.py",
         family, platform, str(clone), str(scout_out)],
        "scout",
    )
    if not ok:
        return "failed"

    ok = _run(
        [sys.executable, "scripts/merge.py", family, platform],
        "merge",
    )
    if not ok:
        return "failed"

    print(f"  {family}/{platform}: refreshed to {head[:10]}")
    return "refreshed"


def discover_products() -> list[tuple[str, str]]:
    """Return (family, platform) pairs from registry, clone cache, or knowledge dirs.

    Priority order:
    1. data/products.json registry (active=true entries) — preferred source
    2. Clone-cache directory scan — fallback for cloned repos not yet in registry
    3. Returns empty list only when all sources are unavailable
    """
    seen: set[tuple[str, str]] = set()
    products: list[tuple[str, str]] = []

    # Source 1: product registry
    if _REGISTRY_PATH.is_file():
        try:
            registry = json.loads(_REGISTRY_PATH.read_text(encoding="utf-8"))
            for entry in registry:
                if entry.get("active", True):
                    pair = (entry["family"], entry["platform"])
                    if pair not in seen:
                        seen.add(pair)
                        products.append(pair)
        except (json.JSONDecodeError, KeyError, OSError):
            pass  # fall through to clone-cache scan

    # Source 2: clone-cache directory scan (adds any cloned repos not in registry)
    cache = _clone_cache_root()
    if cache.is_dir():
        for d in sorted(cache.iterdir()):
            if d.is_dir() and d.name.startswith("aspose_"):
                parts = d.name.removeprefix("aspose_").split("_", 1)
                if len(parts) == 2:
                    pair = (parts[0], parts[1])
                    if pair not in seen:
                        seen.add(pair)
                        products.append(pair)

    return products


def main():
    parser = argparse.ArgumentParser(
        description="Auto-refresh knowledge from clone cache")
    parser.add_argument("--all", action="store_true",
                        help="Refresh all products found in clone cache")
    parser.add_argument("--check", action="store_true",
                        help="Check only — do not run scout/merge, exit 1 if stale")
    parser.add_argument("--no-auto-clone", action="store_true",
                        help="Disable automatic cloning from clone_url in products.json")
    parser.add_argument("family", nargs="?", help="Product family (e.g. 3d)")
    parser.add_argument("platform", nargs="?", help="Platform (e.g. python)")
    args = parser.parse_args()

    if args.all:
        products = discover_products()
        if not products:
            print("No products found in registry or clone cache")
            sys.exit(1)
        results = {}
        for family, platform in products:
            results[(family, platform)] = refresh(
                family, platform, check_only=args.check, auto_clone=not args.no_auto_clone
            )
        stale = [k for k, v in results.items() if v in ("stale", "failed")]
        no_clone = [k for k, v in results.items() if v == "no_clone"]
        if no_clone:
            print(f"\n{len(no_clone)} product(s) have no local clone — "
                  f"clone repos to runs/.clone_cache/ or run repo-scout in pip-install mode")
        if stale:
            print(f"\n{len(stale)} product(s) stale or failed")
            sys.exit(1)
        current = len(products) - len(stale) - len(no_clone)
        print(f"\n{current} current, {len(no_clone)} no-clone, {len(stale)} stale")
        sys.exit(0)

    if not args.family or not args.platform:
        parser.error("Provide family and platform, or use --all")

    result = refresh(args.family, args.platform, check_only=args.check, auto_clone=not args.no_auto_clone)
    if result in ("stale", "failed", "no_clone"):
        sys.exit(1)


if __name__ == "__main__":
    main()
