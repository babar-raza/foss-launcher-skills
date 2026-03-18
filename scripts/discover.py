"""discover.py — GitHub org scanner for FOSS product discovery.

Scans GitHub organizations listed in configs/intake_config.yaml, discovers
public repositories, extracts family/platform from repo names, and optionally
clones them for immediate use with scripts/scout.py.

Adapted from foss-launcher/src/launcher/intake/org_scanner.py. Self-contained:
no dependency on the foss-launcher package.

Usage:
    python scripts/discover.py                            # all orgs
    python scripts/discover.py --org aspose-cells-foss   # single org
    python scripts/discover.py --clone-dir repos/        # also git clone
    python scripts/discover.py --output discovered.json  # write manifest
    python scripts/discover.py --force-rescan            # ignore seen-repos cache
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import yaml

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.WARNING,
    format="%(levelname)s %(message)s",
)
LOG = logging.getLogger("discover")

# ---------------------------------------------------------------------------
# GitHub API constants
# ---------------------------------------------------------------------------

GITHUB_API_BASE = "https://api.github.com"

_REPO_KEYS = frozenset({
    "id", "full_name", "name", "html_url", "description", "fork",
    "archived", "is_template", "size", "stargazers_count", "language",
    "license", "pushed_at", "created_at", "updated_at", "default_branch",
    "topics", "owner",
})

# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------

def _find_config_dir() -> Path:
    """Walk up from CWD or script dir to find configs/ directory."""
    for start in (Path.cwd(), Path(__file__).resolve().parent.parent):
        candidate = start / "configs"
        if candidate.is_dir():
            return candidate
    return Path("configs")


def _load_main_config() -> dict:
    """Load config.yaml from CWD or repo root (same walk-up as config_loader)."""
    for start in (Path.cwd(), Path(__file__).resolve().parent.parent):
        candidate = start / "config.yaml"
        if candidate.is_file():
            with open(candidate, encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
    return {}


def _load_intake_config(config_path: Optional[Path] = None) -> dict:
    if config_path is None:
        # Honour config.yaml intake_config key if present
        main_cfg = _load_main_config()
        cfg_key = main_cfg.get("intake_config", "")
        if cfg_key and Path(cfg_key).is_file():
            config_path = Path(cfg_key)
        else:
            config_path = _find_config_dir() / "intake_config.yaml"
    if not config_path.is_file():
        raise FileNotFoundError(f"intake_config.yaml not found at {config_path}")
    with open(config_path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _load_families(families_path: Optional[Path] = None) -> dict:
    if families_path is None:
        # Honour config.yaml families_config key if present
        main_cfg = _load_main_config()
        cfg_key = main_cfg.get("families_config", "")
        if cfg_key and Path(cfg_key).is_file():
            families_path = Path(cfg_key)
        else:
            families_path = _find_config_dir() / "families.yaml"
    if not families_path.is_file():
        return {}
    with open(families_path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}

# ---------------------------------------------------------------------------
# Name parsing — extract family + platform from GitHub repo name/language
# ---------------------------------------------------------------------------

# Maps GitHub language field → platform key
_LANG_TO_PLATFORM: Dict[str, str] = {
    "Python": "python",
    "C#": "dotnet",
    "Java": "java",
    "C++": "cpp",
    "TypeScript": "typescript",
    "JavaScript": "javascript",
    "Go": "go",
    "Rust": "rust",
    "PHP": "php",
    "Ruby": "ruby",
    "Kotlin": "kotlin",
    "Swift": "swift",
}

# Repo name suffixes → platform key (e.g. "-for-Python" → "python")
_SUFFIX_TO_PLATFORM: Dict[str, str] = {
    "python": "python",
    "java": "java",
    ".net": "dotnet",
    "dotnet": "dotnet",
    "net": "dotnet",
    "c++": "cpp",
    "cpp": "cpp",
    "typescript": "typescript",
    "javascript": "javascript",
    "nodejs": "javascript",
    "node.js": "javascript",
    "go": "go",
    "rust": "rust",
    "php": "php",
    "ruby": "ruby",
    "kotlin": "kotlin",
    "swift": "swift",
}


def _parse_repo_name(repo_name: str, org_name: str, families: dict) -> Tuple[Optional[str], Optional[str]]:
    """Extract (family, platform) from a GitHub repo name.

    Patterns tried:
      1. Aspose.{Family}-FOSS-for-{Platform}   e.g. Aspose.Cells-FOSS-for-Python
      2. aspose-{family}-for-{platform}         e.g. aspose-cells-for-python
      3. Org name: aspose-{family}-foss         → family only; platform from language
    """
    name_lower = repo_name.lower()
    family_names = set((families.get("families") or {}).keys())

    # Pattern 1 & 2: name contains "-for-"
    for_match = re.search(r"-for-(.+?)(?:$|-foss)", name_lower)
    if for_match:
        platform_raw = for_match.group(1).rstrip("-")
        platform = _SUFFIX_TO_PLATFORM.get(platform_raw)

        # Extract family from org or name
        family = _extract_family_from_org(org_name, family_names)
        if family and platform:
            return family, platform

    # Pattern 3: try to get family from org, platform from repo name suffix
    family = _extract_family_from_org(org_name, family_names)
    if family:
        for suffix, platform in _SUFFIX_TO_PLATFORM.items():
            if name_lower.endswith(f"-{suffix}") or f"-{suffix}-" in name_lower:
                return family, platform

    return family, None


def _extract_family_from_org(org_name: str, family_names: Set[str]) -> Optional[str]:
    """Extract family key from org name like 'aspose-cells-foss' → 'cells'."""
    # Strip common prefix/suffix
    name = org_name.lower()
    name = re.sub(r"^aspose-", "", name)
    name = re.sub(r"-foss$", "", name)
    # Direct match
    if name in family_names:
        return name
    # Partial match
    for fam in family_names:
        if fam in name or name in fam:
            return fam
    return name if name else None

# ---------------------------------------------------------------------------
# GitHub API helpers (adapted from org_scanner.py)
# ---------------------------------------------------------------------------

def _build_headers(token: Optional[str]) -> Dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"token {token}"
    return headers


def _parse_link_header(link_header: str) -> Dict[str, str]:
    links: Dict[str, str] = {}
    for part in link_header.split(","):
        part = part.strip()
        match = re.match(r'<([^>]+)>;\s*rel="([^"]+)"', part)
        if match:
            links[match.group(2)] = match.group(1)
    return links


def _slim_repo(repo: Dict[str, Any]) -> Dict[str, Any]:
    slim: Dict[str, Any] = {}
    for key in _REPO_KEYS:
        if key in repo:
            val = repo[key]
            if key == "license" and isinstance(val, dict):
                slim["license"] = {"spdx_id": val.get("spdx_id"), "name": val.get("name")}
            elif key == "owner" and isinstance(val, dict):
                slim["owner"] = {"login": val.get("login"), "type": val.get("type")}
            else:
                slim[key] = val
    return slim


def _check_rate_limit(resp: Any, delay_s: float = 1.0) -> None:
    """Sleep if rate limit is low; raise on exhausted limit."""
    remaining = resp.headers.get("X-RateLimit-Remaining")
    reset_at = resp.headers.get("X-RateLimit-Reset")

    if resp.status_code == 403:
        body_lower = resp.text.lower()
        if "rate limit" in body_lower or "api rate" in body_lower:
            if reset_at:
                wait_s = max(0, int(reset_at) - int(time.time())) + 1
                if wait_s <= 300:
                    LOG.warning("Rate limited. Waiting %d seconds.", wait_s)
                    time.sleep(wait_s)
                    return
            raise RuntimeError(f"GitHub API rate limit exceeded. Reset at: {reset_at}")

    if remaining is not None and int(remaining) < 10 and reset_at:
        wait_s = max(0, int(reset_at) - int(time.time())) + 1
        if wait_s <= 60:
            LOG.info("Rate limit low (%s remaining). Sleeping %ds.", remaining, wait_s)
            time.sleep(wait_s)

# ---------------------------------------------------------------------------
# Core scanner
# ---------------------------------------------------------------------------

def scan_org(
    org: str,
    *,
    token: Optional[str] = None,
    per_page: int = 100,
    max_pages: int = 10,
    activity_months: int = 12,
    rate_limit_delay_s: float = 1.0,
    seen_repos: Optional[Set[str]] = None,
    force_rescan: bool = False,
) -> List[Dict[str, Any]]:
    """Scan one GitHub org and return slim repo dicts."""
    try:
        import requests
    except ImportError:
        raise RuntimeError("requests is required: pip install requests")

    if seen_repos is None:
        seen_repos = set()

    cutoff = datetime.now(timezone.utc) - timedelta(days=activity_months * 30)
    headers = _build_headers(token)
    url: Optional[str] = f"{GITHUB_API_BASE}/orgs/{org}/repos?type=public&per_page={per_page}"

    discovered: List[Dict[str, Any]] = []
    pages_fetched = 0

    while url and pages_fetched < max_pages:
        LOG.debug("Fetching %s (page %d)", url, pages_fetched + 1)
        resp = requests.get(url, headers=headers, timeout=30)

        _check_rate_limit(resp, rate_limit_delay_s)

        if resp.status_code == 404:
            LOG.warning("Organization not found: %s", org)
            return []
        if resp.status_code != 200:
            raise RuntimeError(f"GitHub API error {resp.status_code} for org '{org}': {resp.text[:200]}")

        repos = resp.json()
        if not isinstance(repos, list):
            raise RuntimeError(f"Unexpected response type for org '{org}': {type(repos)}")

        for repo in repos:
            full_name = repo.get("full_name", "")
            if not force_rescan and full_name in seen_repos:
                continue
            if repo.get("archived", False) or repo.get("fork", False) or repo.get("size", 0) == 0:
                continue

            pushed_at_str = repo.get("pushed_at")
            if pushed_at_str:
                pushed_at = datetime.fromisoformat(pushed_at_str.replace("Z", "+00:00"))
                if pushed_at < cutoff:
                    continue

            discovered.append(_slim_repo(repo))

        link_header = resp.headers.get("Link", "")
        links = _parse_link_header(link_header) if link_header else {}
        url = links.get("next")
        pages_fetched += 1

        if url:
            time.sleep(rate_limit_delay_s)

    return discovered

# ---------------------------------------------------------------------------
# Cloning
# ---------------------------------------------------------------------------

def clone_repo(repo_url: str, dest_dir: Path) -> bool:
    """git clone repo_url into dest_dir. Returns True if cloned, False if already exists."""
    if dest_dir.exists():
        LOG.debug("Already exists, skipping clone: %s", dest_dir)
        return False
    dest_dir.parent.mkdir(parents=True, exist_ok=True)
    LOG.info("Cloning %s → %s", repo_url, dest_dir)
    result = subprocess.run(
        ["git", "clone", "--depth=1", repo_url, str(dest_dir)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        LOG.warning("Clone failed for %s: %s", repo_url, result.stderr.strip())
        return False
    return True

# ---------------------------------------------------------------------------
# Discovery manifest builder
# ---------------------------------------------------------------------------

def _load_scan_state(state_dir: Optional[Path]) -> Set[str]:
    """Load seen_repos set from scan_state.json, if it exists."""
    if state_dir is None:
        return set()
    state_path = Path(state_dir) / "scan_state.json"
    if state_path.is_file():
        try:
            data = json.loads(state_path.read_text(encoding="utf-8"))
            return set(data.get("seen_repos", []))
        except (json.JSONDecodeError, OSError) as e:
            LOG.warning("Could not read scan state: %s", e)
    return set()


def _save_scan_state(state_dir: Optional[Path], seen: Set[str]) -> None:
    """Persist seen_repos to scan_state.json (atomic write via temp file)."""
    if state_dir is None:
        return
    state_dir = Path(state_dir)
    try:
        state_dir.mkdir(parents=True, exist_ok=True)
        state_path = state_dir / "scan_state.json"
        tmp_path = state_dir / "scan_state.json.tmp"
        data = {
            "seen_repos": sorted(seen),
            "last_scan_ts": datetime.now(timezone.utc).isoformat(),
        }
        tmp_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        tmp_path.replace(state_path)
        LOG.info("Scan state persisted: %d repos", len(seen))
    except OSError as e:
        LOG.warning("Could not save scan state: %s", e)


def discover(
    orgs: List[str],
    *,
    token: Optional[str] = None,
    families: Optional[dict] = None,
    per_page: int = 100,
    activity_months: int = 12,
    rate_limit_delay_s: float = 1.0,
    clone_dir: Optional[Path] = None,
    force_rescan: bool = False,
    state_dir: Optional[Path] = None,
) -> List[Dict[str, Any]]:
    """Scan orgs, extract family/platform, optionally clone.

    Args:
        state_dir: If set, load/save seen_repos from state_dir/scan_state.json
                   so repeated runs skip already-discovered repos.
    """
    if families is None:
        families = {}

    manifest: List[Dict[str, Any]] = []
    seen: Set[str] = set() if force_rescan else _load_scan_state(state_dir)

    for org in orgs:
        repos = scan_org(
            org,
            token=token,
            per_page=per_page,
            activity_months=activity_months,
            rate_limit_delay_s=rate_limit_delay_s,
            seen_repos=seen,
            force_rescan=force_rescan,
        )
        for r in repos:
            full_name = r["full_name"]
            if full_name in seen:
                continue
            seen.add(full_name)
            name = r["name"]
            html_url = r.get("html_url", "")
            language = r.get("language", "")

            family, platform = _parse_repo_name(name, org, families)

            # Fall back to GitHub language field for platform
            if platform is None and language:
                platform = _LANG_TO_PLATFORM.get(language)

            entry: Dict[str, Any] = {
                "family": family,
                "platform": platform,
                "repo_url": html_url,
                "full_name": full_name,
                "language": language,
                "stars": r.get("stargazers_count", 0),
            }

            if clone_dir is not None:
                dest = clone_dir / full_name
                cloned = clone_repo(html_url, dest)
                entry["clone_dir"] = str(dest)
                entry["cloned"] = cloned

            manifest.append(entry)

    _save_scan_state(state_dir, seen)
    return manifest

# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Discover FOSS products from configured GitHub organizations.",
    )
    parser.add_argument(
        "--org",
        metavar="ORG",
        help="Scan only this org (default: all orgs in intake_config.yaml).",
    )
    parser.add_argument(
        "--clone-dir",
        metavar="DIR",
        type=Path,
        help="Clone discovered repos into DIR/{org}/{repo}.",
    )
    parser.add_argument(
        "--output",
        metavar="FILE",
        type=Path,
        help="Write discovery manifest JSON to FILE (default: print to stdout).",
    )
    parser.add_argument(
        "--token",
        metavar="TOKEN",
        help="GitHub API token (default: $GITHUB_TOKEN env var).",
    )
    parser.add_argument(
        "--force-rescan",
        action="store_true",
        help="Re-scan repos even if already seen.",
    )
    parser.add_argument(
        "--state-dir",
        metavar="DIR",
        type=Path,
        default=Path("intake"),
        help="Directory for scan_state.json persistence (default: intake/).",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose logging.",
    )
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    token = args.token or os.environ.get("GITHUB_TOKEN")

    # Load configs
    try:
        intake = _load_intake_config()
    except FileNotFoundError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    families = _load_families()

    scanner_cfg = intake.get("scanner", {})
    per_page = scanner_cfg.get("per_page", 100)
    activity_months = scanner_cfg.get("activity_months", 12)
    rate_limit_delay_s = scanner_cfg.get("rate_limit_delay_s", 1.0)

    if args.org:
        orgs = [args.org]
    else:
        orgs = [o["name"] for o in intake.get("organizations", [])]

    if not orgs:
        print("ERROR: No organizations configured in intake_config.yaml", file=sys.stderr)
        sys.exit(1)

    print(f"Scanning {len(orgs)} organization(s)...", file=sys.stderr)

    manifest = discover(
        orgs,
        token=token,
        families=families,
        per_page=per_page,
        activity_months=activity_months,
        rate_limit_delay_s=rate_limit_delay_s,
        clone_dir=args.clone_dir,
        force_rescan=args.force_rescan,
        state_dir=args.state_dir,
    )

    # Print summary table
    print(f"\nDiscovered {len(manifest)} repo(s):\n", file=sys.stderr)
    print(f"{'FAMILY':<12} {'PLATFORM':<12} {'REPO'}", file=sys.stderr)
    print("-" * 60, file=sys.stderr)
    for e in manifest:
        fam = e["family"] or "?"
        plat = e["platform"] or "?"
        print(f"{fam:<12} {plat:<12} {e['repo_url']}", file=sys.stderr)

    # Output manifest
    manifest_json = json.dumps(manifest, indent=2, ensure_ascii=False)
    if args.output:
        args.output.write_text(manifest_json, encoding="utf-8")
        print(f"\nManifest written to: {args.output}", file=sys.stderr)
    else:
        print(manifest_json)

    if args.clone_dir:
        cloned_count = sum(1 for e in manifest if e.get("cloned"))
        print(f"\nCloned: {cloned_count} new repo(s) into {args.clone_dir}", file=sys.stderr)
        print("\nNext step:", file=sys.stderr)
        print("  python scripts/scout.py {family} {platform} {clone_dir}/{full_name} knowledge/{family}/{platform}/scout/", file=sys.stderr)


if __name__ == "__main__":
    main()
