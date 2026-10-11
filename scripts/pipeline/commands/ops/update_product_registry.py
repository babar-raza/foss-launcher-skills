"""Update data/products.json by scanning the GitHub org and local knowledge dirs.

Usage:
    python scripts/pipeline/commands/ops/update_product_registry.py [--token TOKEN] [--force]
    python scripts/pipeline/commands/ops/update_product_registry.py --local-only
    python scripts/pipeline/commands/ops/update_product_registry.py --reconcile

Modes:
    Default:      Scan GitHub org for FOSS repos, merge with local knowledge dirs.
    --local-only: Skip GitHub — build registry from knowledge/ dirs only.
    --force:      Overwrite active/inactive status even for repos already in registry.
                  (active = not archived AND the default branch contains product
                  source; push recency is NOT considered -- MT075 TC-RPG-04.)
    --reconcile:  Read-only check: verify all 8 content/knowledge/package-registry
                  signals for each registered product. Prints a per-product table
                  and exits 1 if any signal is MISSING.

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

Exit codes:
    0  registry written (or dry-run/reconcile OK)
    1  --reconcile found a MISSING/STALE signal, or a read error
    2  no credential, or the GitHub scan reached no org — the tracked registry is
       left UNCHANGED rather than rewritten from unverified data (ST-058)

Environment:
    GH_TOKEN      GitHub classic PAT — preferred credential (alternative to --token).
    GITHUB_TOKEN  Fallback only. The aspose-*-foss orgs reject fine-grained PATs with
                  a lifetime over 366 days, so this variable 403s here (ST-058).
    ASPOSE_ORG    Comma-separated GitHub organisations to scan
                  (default: all 26 aspose-{family}-foss orgs).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Callable

try:
    import requests  # noqa: F401
except ImportError:
    requests = None  # type: ignore[assignment]

_DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[4]
REPO_ROOT = _DEFAULT_REPO_ROOT
KNOWLEDGE_ROOT = REPO_ROOT / "knowledge"
DATA_DIR = REPO_ROOT / "data"
REGISTRY_PATH = DATA_DIR / "products.json"


def configure(*, repo_root: "Path | str | None" = None) -> None:
    """Override module-level path constants for testing."""
    global REPO_ROOT, KNOWLEDGE_ROOT, DATA_DIR, REGISTRY_PATH
    REPO_ROOT = Path(repo_root) if repo_root is not None else _DEFAULT_REPO_ROOT
    KNOWLEDGE_ROOT = REPO_ROOT / "knowledge"
    DATA_DIR = REPO_ROOT / "data"
    REGISTRY_PATH = DATA_DIR / "products.json"

_PIPELINE_DIR = Path(__file__).resolve().parents[2]  # commands/ops/ -> commands/ -> pipeline/
_LIB_DIR = _PIPELINE_DIR / "lib"
for _p in (str(_PIPELINE_DIR), str(_LIB_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)
from core.env_loader import load_env  # noqa: E402
load_env()

# "active" is NOT a push-recency heuristic (MT075 TC-RPG-04): a repo is active iff
# it is not archived AND its DEFAULT branch contains product source, however long
# ago anyone last pushed. See org_scanner.has_product_source().

# Orgs to scan — one per Aspose family, overrideable via ASPOSE_ORG env var
_DEFAULT_ORGS = [
    "aspose-3d-foss",
    "aspose-barcode-foss",
    "aspose-cad-foss",
    "aspose-cells-foss",
    "aspose-diagram-foss",
    "aspose-drawing-foss",
    "aspose-email-foss",
    "aspose-finance-foss",
    "aspose-font-foss",
    "aspose-gis-foss",
    "aspose-html-foss",
    "aspose-imaging-foss",
    "aspose-medical-foss",
    "aspose-note-foss",
    "aspose-ocr-foss",
    "aspose-omr-foss",
    "aspose-page-foss",
    "aspose-pdf-foss",
    "aspose-psd-foss",
    "aspose-pub-foss",
    "aspose-slides-foss",
    "aspose-svg-foss",
    "aspose-tasks-foss",
    "aspose-tex-foss",
    "aspose-words-foss",
    "aspose-zip-foss",
]

# Pattern: Aspose.{Family}-FOSS-for-{Platform}  (e.g. Aspose.3D-FOSS-for-Python)
# Also accepts legacy: aspose-{family}-{platform}
# Also accepts lowercase foss-for: aspose-{family}-foss-for-{platform} (e.g. aspose-pdf-foss-for-go)
# IGNORECASE (2026-09-11): the literal "FOSS" token is not itself part of the
# naming CONVENTION being enforced -- it's incidental casing. Confirmed live
# while registering imaging/net: the real upstream repo is
# "Aspose.Imaging-Foss-for-.NET" (mixed-case "Foss"), which the previously
# case-sensitive pattern silently failed to classify with no error, and the
# lowercase fallback below doesn't cover either (it requires all-hyphen
# separators, not the dotted "Aspose.{Family}" prefix shape).
_REPO_PATTERN_FOSS = re.compile(
    r"^Aspose\.([A-Za-z0-9]+)-FOSS-for-([A-Za-z0-9.]+)$", re.IGNORECASE
)
_REPO_PATTERN_FOSS_LOWER = re.compile(
    r"^aspose-([a-z0-9]+)-foss-for-([a-z0-9]+)$"
)
_REPO_PATTERN_LEGACY = re.compile(r"^aspose-([a-z0-9]+)-([a-z0-9]+)$")

# Normalise platform name to internal identifier
_PLATFORM_MAP = {
    "python": "python",
    "java": "java",
    ".net": "net",
    "net": "net",
    "cpp": "cpp",
    "typescript": "typescript",
    "javascript": "javascript",
    "nodejs": "nodejs",
    "go": "go",
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

    # Lowercase foss-for convention: aspose-pdf-foss-for-go
    m = _REPO_PATTERN_FOSS_LOWER.match(repo_name.lower())
    if m:
        platform_raw = m.group(2)
        platform = _PLATFORM_MAP.get(platform_raw, platform_raw)
        return m.group(1), platform

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
# Registry exclusions (data/registry_exclusions.json)
# ---------------------------------------------------------------------------
# Duplicated in repo_patrol.py per PIPELINE.md's "2 scripts need it -> duplicate
# and comment" rule (no lib/ module for exactly 2 consumers).

def _load_exclusions() -> list[dict]:
    path = DATA_DIR / "registry_exclusions.json"
    if not path.is_file():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []


def _is_excluded(exclusions: list[dict], *, repo_name: str = "", family: str = "", platform: str = "") -> bool:
    for ex in exclusions:
        if ex.get("match") == "repo_name" and repo_name and ex.get("value", "").lower() == repo_name.lower():
            return True
        if ex.get("match") == "family_platform" and family and platform \
                and ex.get("family") == family and ex.get("platform") == platform:
            return True
    return False


def _enforce_exclusions(merged: list[dict], exclusions: list[dict]) -> list[dict]:
    """Force active=False on any entry matching an exclusion, in place.

    Safety net independent of the discovery-time skip in _discover_from_github:
    catches an excluded entry regardless of which code path produced or
    preserved it (existing registry state, --local-only knowledge_dir
    discovery, --force, etc). Mutates and returns *merged* for convenience.
    """
    for entry in merged:
        if _is_excluded(exclusions, repo_name=entry.get("repo_name", ""),
                         family=entry["family"], platform=entry["platform"]):
            entry["active"] = False
            entry["excluded"] = True
    return merged


# ---------------------------------------------------------------------------
# Discover products from GitHub
# ---------------------------------------------------------------------------

def _import_org_scanner():
    """Import org_scanner, tolerating invocation from the repo root."""
    try:
        import org_scanner  # noqa: PLC0415  (local import)
        return org_scanner
    except ImportError:
        # fallback-import guard: when invoked from repo root, scripts/pipeline/ is not on sys.path.
        # Try absolute import when running from repo root; also add lib/ since org_scanner lives there.
        _pipeline = Path(__file__).resolve().parents[2]
        for _fb_p in (str(_pipeline), str(_pipeline / "lib")):
            if _fb_p not in sys.path:
                sys.path.insert(0, _fb_p)
        import org_scanner  # type: ignore[no-redef]
        return org_scanner


def _compute_active(
    repo: dict,
    previous: dict | None,
    token: str | None,
    has_source_fn: "Callable[..., bool | None]",
) -> bool:
    """Registry ``active`` for one scanned repo: not archived AND default branch has source.

    Push recency is deliberately ignored (an uploaded-once product stays active).
    When the source probe cannot answer (``None``: API/network/rate-limit error), the
    result is never silently demoted: an existing registry entry keeps its previous
    ``active``; a brand-new pair is recorded ``False`` and a warning is printed.
    """
    if repo.get("archived"):
        return False
    has_source = has_source_fn(
        repo.get("full_name") or repo["name"],
        repo["name"],
        repo.get("default_branch", ""),
        token=token,
    )
    if has_source is not None:
        return bool(has_source)
    if previous is not None:
        kept = bool(previous.get("active"))
        print(f"  WARN: could not verify product source for {repo['name']} "
              f"(branch {repo.get('default_branch') or '?'!r}); keeping previous active={kept}",
              file=sys.stderr)
        return kept
    print(f"  WARN: could not verify product source for NEW repo {repo['name']} "
          f"(branch {repo.get('default_branch') or '?'!r}); recording active=False",
          file=sys.stderr)
    return False


def _discover_from_github(
    orgs: list[str],
    token: str | None,
    *,
    existing: "list[dict] | None" = None,
    scan_orgs_fn: "Callable[..., tuple[list[dict], list[dict]]] | None" = None,
    has_source_fn: "Callable[..., bool | None] | None" = None,
) -> tuple[list[dict], list[dict]]:
    """Return ``(products, outcomes)`` discovered by scanning one or more GitHub orgs.

    *outcomes* is the per-org result list from ``org_scanner.scan_orgs``; callers
    MUST inspect it before treating an empty product list as "no products exist"
    (ST-058).

    *existing* is the current registry (used so an unknown source probe never flips
    a previously-active entry). *scan_orgs_fn* / *has_source_fn* are test seams that
    default to ``org_scanner.scan_orgs`` / ``org_scanner.has_product_source``.
    """
    scanner = _import_org_scanner()
    scan_orgs = scan_orgs_fn or scanner.scan_orgs
    has_source_fn = has_source_fn or scanner.has_product_source
    previous_by_key = {_key(e): e for e in (existing or [])}

    products: list[dict] = []
    exclusions = _load_exclusions()
    repos, outcomes = scan_orgs(orgs, token=token)
    for repo in repos:
        pair = _classify_repo(repo["name"])
        if pair is None:
            continue
        family, platform = pair
        if _is_excluded(exclusions, repo_name=repo["name"], family=family, platform=platform):
            continue
        active = _compute_active(repo, previous_by_key.get((family, platform)), token, has_source_fn)
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
    return products, outcomes


# ---------------------------------------------------------------------------
# Merge strategy
# ---------------------------------------------------------------------------

def _key(entry: dict) -> tuple[str, str]:
    return (entry["family"], entry["platform"])


_DISCOVERY_FIELDS = ("status", "confidence", "first_seen_at", "last_scanned_at", "rejection_reason")


def _merge(existing: list[dict], incoming: list[dict], force: bool) -> list[dict]:
    """Merge *incoming* entries into *existing* registry.

    - GitHub entries (discovered_via=github) take precedence over knowledge_dir entries.
    - When *force* is True, active/inactive status is always overwritten.
    - When *force* is False, existing active=True entries are preserved.
    - Discovery fields (status, confidence, first_seen_at, last_scanned_at,
      rejection_reason) are preserved from existing entries when incoming
      entries lack them.
    - Rejected entries (status="rejected") keep their status unless *force*
      is True.
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
                merged = {
                    **prev,
                    "repo_name": entry["repo_name"],
                    "repo_url": entry["repo_url"],
                    "clone_url": entry["clone_url"],
                    "discovered_via": "github",
                }
                if force or not prev.get("active"):
                    merged["active"] = entry["active"]
                # Reconcile discovery fields: incoming value wins if present,
                # otherwise preserve from existing entry
                for field in _DISCOVERY_FIELDS:
                    if field in entry:
                        merged[field] = entry[field]
                    elif field in prev:
                        merged[field] = prev[field]
                # Protect rejected status unless --force
                if not force and prev.get("status") == "rejected":
                    merged["status"] = "rejected"
                    merged["rejection_reason"] = prev.get("rejection_reason")
                registry[k] = merged
            elif force:
                registry[k]["active"] = entry["active"]

    # Sort by family then platform for stable output
    return sorted(registry.values(), key=lambda e: (e["family"], e["platform"]))


# ---------------------------------------------------------------------------
# Reconcile — read-only 7-signal check
# ---------------------------------------------------------------------------

_SIGNAL_LABELS = [
    "registry_entry",
    "knowledge_model_yaml",
    "site_plan_yaml",
    "blog_content",
    "docs_content",
    "kb_content",
    "reference_content",
    "package_registry",
]

# MT015: platform -> the package_registry.json registry_type it should carry
# an entry under. Platforms not listed here have no tracked package-manager
# identity yet (vcpkg/Conan were confirmed never implemented in practice; any
# other unmapped platform is "not applicable" rather than a real gap).
_PLATFORM_TO_REGISTRY_TYPE = {
    "python": "pypi", "net": "nuget", "cpp": "nuget", "java": "maven",
    "npm": "npm", "typescript": "npm", "javascript": "npm",
    "go": "go_modules", "rust": "cargo",
}


def _load_package_registry() -> dict:
    path = REPO_ROOT / "data" / "package_registry.json"
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _check_signals(entry: dict) -> list[tuple[str, str]]:
    """Return list of (signal_label, status) for all 8 signals.

    status is "OK", "MISSING", "STALE", "SKIPPED", "UNVERIFIED", or "N/A".
    """
    family = entry["family"]
    platform = entry["platform"]

    results: list[tuple[str, str]] = []

    # Signal 1: registry entry exists — by definition true if we have the entry
    results.append(("registry_entry", "OK"))

    # Signal 2: knowledge/{family}/{platform}/merged/model.yaml exists and not stale
    model_path = KNOWLEDGE_ROOT / family / platform / "merged" / "model.yaml"
    if model_path.is_file():
        # Check for stale_since: non-null
        try:
            import yaml  # type: ignore[import]
            with open(model_path, encoding="utf-8") as fh:
                data = yaml.safe_load(fh) or {}
            stale_since = data.get("stale_since")
            if stale_since:
                results.append(("knowledge_model_yaml", "STALE"))
            else:
                results.append(("knowledge_model_yaml", "OK"))
        except Exception:
            results.append(("knowledge_model_yaml", "OK"))  # file exists, yaml parse error is non-critical
    else:
        results.append(("knowledge_model_yaml", "MISSING"))

    # Signal 3: site_plan.yaml exists
    plan_path = REPO_ROOT / "reports" / "plans" / family / platform / "site_plan.yaml"
    results.append(("site_plan_yaml", "OK" if plan_path.is_file() else "MISSING"))

    # Signal 4: blog_content — special-cased. The site planner (site_planner.py
    # plan_blog()) only plans blog pages when total_claims/snippet_count clear
    # a minimum bar; below that bar it correctly and deliberately plans 0 pages
    # (sections.blog.justified: false). An absent blog dir is only a real gap
    # when blog WAS justified — otherwise it's working as designed, not MISSING.
    blog_path = REPO_ROOT / "content" / "blog.aspose.org" / family / platform
    if blog_path.is_dir():
        results.append(("blog_content", "OK"))
    else:
        blog_justified = _read_blog_justified(plan_path)
        if blog_justified is False:
            results.append(("blog_content", "SKIPPED"))
        else:
            # justified True, or unknown (missing/corrupt site plan) — fail
            # conservative, same as the other signals above.
            results.append(("blog_content", "MISSING"))

    # Signal 5–7: content directories exist
    content_sites = [
        ("docs_content", REPO_ROOT / "content" / "docs.aspose.org" / "en" / family / platform),
        ("kb_content", REPO_ROOT / "content" / "kb.aspose.org" / "en" / family / platform),
        ("reference_content", REPO_ROOT / "content" / "reference.aspose.org" / "en" / family / platform),
    ]
    for label, path in content_sites:
        results.append((label, "OK" if path.is_dir() else "MISSING"))

    # Signal 8 (MT015): package_registry -- does data/package_registry.json
    # track this family/platform's package-manager identity at all? MISSING
    # here is exactly the "launched but package-unverified" discrepancy this
    # signal exists to surface (closing the words/net-style bidirectional-
    # sequencing gap: a product can launch content before its package exists,
    # or vice versa, and nothing previously cross-referenced the two states).
    # The inverse discrepancy ("published in the registry but content still
    # says unpublished") is a content-text concern, out of scope here --
    # covered by the audit gate (TC-MT015-05), not this file-existence check.
    registry_type = _PLATFORM_TO_REGISTRY_TYPE.get(platform)
    if registry_type is None:
        results.append(("package_registry", "N/A"))
    else:
        pr_entry = _load_package_registry().get(family, {}).get(platform)
        if pr_entry is None:
            results.append(("package_registry", "MISSING"))
        elif not pr_entry.get("verification", {}).get("published"):
            results.append(("package_registry", "UNVERIFIED"))
        else:
            results.append(("package_registry", "OK"))

    return results


def _read_blog_justified(plan_path: Path) -> bool | None:
    """Read sections.blog.justified from a site_plan.yaml.

    Returns True/False if determinable, None if the file is missing, unreadable,
    or doesn't have the expected shape (caller should treat None as unknown and
    fail conservative, not assume False).
    """
    if not plan_path.is_file():
        return None
    try:
        import yaml  # type: ignore[import]
        with open(plan_path, encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        plan = data.get("plan", data)
        blog = plan.get("sections", {}).get("blog", {})
        justified = blog.get("justified")
        return bool(justified) if isinstance(justified, bool) else None
    except Exception:
        return None


def _run_reconcile(products: list[dict]) -> int:
    """Print per-product signal table.  Returns 0 if all OK, 1 if any MISSING/STALE."""
    any_bad = False

    # Header
    col_product = 28
    col_signal = 22
    col_status = 8
    header = f"{'product':<{col_product}} {'signal':<{col_signal}} {'status':<{col_status}}"
    print(header)
    print("-" * (col_product + col_signal + col_status + 2))

    for entry in products:
        key = f"{entry['family']}/{entry['platform']}"
        signals = _check_signals(entry)
        for label, status in signals:
            # UNVERIFIED (package tracked, not yet confirmed published -- a
            # normal, valid pre-publish state, not a defect) and N/A
            # (platform has no tracked registry type) never fail reconcile;
            # only a genuinely MISSING/STALE signal does.
            if status not in ("OK", "SKIPPED", "UNVERIFIED", "N/A"):
                any_bad = True
            if status == "MISSING":
                marker = " <-- MISSING"
            elif status == "STALE":
                marker = " <-- STALE"
            elif status == "SKIPPED":
                marker = " <-- skipped (below blog threshold)"
            elif status == "UNVERIFIED":
                marker = " <-- not yet confirmed published"
            else:
                marker = ""
            print(f"{key:<{col_product}} {label:<{col_signal}} {status:<{col_status}}{marker}")

    print()
    if any_bad:
        print("RECONCILE: one or more signals MISSING or STALE — exit 1")
        return 1
    print("RECONCILE: all signals OK — exit 0")
    return 0


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
    parser.add_argument("--token", help="GitHub PAT (falls back to GH_TOKEN, then GITHUB_TOKEN)")
    parser.add_argument("--org", default=_default_orgs_str,
                        help="Comma-separated GitHub organisations to scan (default: %(default)s)")
    parser.add_argument("--local-only", action="store_true",
                        help="Skip GitHub — build registry from knowledge/ dirs only")
    parser.add_argument("--force", action="store_true",
                        help="Overwrite active status for existing entries")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print discovered products; do NOT write data/products.json")
    parser.add_argument("--reconcile", "--check", action="store_true",
                        help="Read-only: check all 8 content/knowledge/package-registry "
                             "signals for each registered product. Exit 0 if all OK, exit 1 if any MISSING.")
    args = parser.parse_args(argv)

    token, auth_mode = _import_org_scanner().resolve_token(args.token)
    if token is None and not args.local_only and not args.reconcile:
        print("ERROR: no GitHub credential found. Set GH_TOKEN (classic PAT) or pass "
              "--token; use --local-only to build from knowledge/ dirs without GitHub.",
              file=sys.stderr)
        return 2

    # --reconcile: read-only signal check against the existing registry
    if args.reconcile:
        if not REGISTRY_PATH.is_file():
            print(f"ERROR: registry not found at {REGISTRY_PATH}", file=sys.stderr)
            print("Run without --reconcile first to build the registry.", file=sys.stderr)
            return 1
        try:
            products = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            print(f"ERROR: could not read registry: {exc}", file=sys.stderr)
            return 1
        return _run_reconcile(products)

    if args.token and requests is None:
        print("ERROR: requests library required for live GitHub discovery.")
        print("Activate .venv and run: pip install -r scripts/pipeline/requirements.txt")
        sys.exit(1)

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
        print(f"Scanning GitHub orgs: {orgs} (auth: {auth_mode})…", file=sys.stderr)
        try:
            github_products, outcomes = _discover_from_github(orgs, token, existing=existing)
        except Exception as exc:  # noqa: BLE001
            print(f"ERROR: GitHub scan failed ({exc})", file=sys.stderr)
            print("Refusing to rewrite the tracked registry from an unverified scan. "
                  "Fix the cause, or pass --local-only to build from knowledge/ dirs "
                  "deliberately.", file=sys.stderr)
            return 2

        failures = [o for o in outcomes if o["status"] != "ok"]
        for f in failures:
            print(f"  {f['status'].upper()} {f['org']}: {f['detail'][:160]}", file=sys.stderr)

        if failures and len(failures) == len(outcomes):
            # Total failure. data/products.json is TRACKED — overwriting it from a
            # scan that reached nothing would silently launder a failure into
            # committed state (ST-058).
            print(f"ERROR: all {len(outcomes)} orgs failed; no GitHub data obtained.",
                  file=sys.stderr)
            print(f"Refusing to rewrite {REGISTRY_PATH.name}; it is left unchanged. "
                  "Fix the credential (GH_TOKEN, classic PAT) or pass --local-only.",
                  file=sys.stderr)
            return 2

        incoming.extend(github_products)
        print(f"  Found {len(github_products)} repos matching aspose-{{family}}-{{platform}} "
              f"({len(outcomes) - len(failures)}/{len(outcomes)} orgs ok)", file=sys.stderr)
        if failures:
            print(f"  WARNING: scan DEGRADED — {len(failures)} org(s) unreachable; "
                  "registry merge is based on incomplete data.", file=sys.stderr)

    # Always add knowledge_dir entries as fallback for anything not on GitHub
    kd_products = _discover_from_knowledge()
    incoming.extend(kd_products)
    print(f"  Found {len(kd_products)} products in knowledge/ dirs", file=sys.stderr)

    # Merge
    merged = _merge(existing, incoming, force=args.force)

    # Enforce exclusions unconditionally on the final merged output (see
    # _enforce_exclusions docstring).
    merged = _enforce_exclusions(merged, _load_exclusions())

    # Dry-run: print table and exit without writing
    if args.dry_run:
        print(f"{'family':<12} {'platform':<12} {'repo_name':<40} {'active'}")
        print("-" * 72)
        for e in merged:
            print(f"{e['family']:<12} {e['platform']:<12} {e['repo_name']:<40} {e.get('active', False)}")
        active = sum(1 for e in merged if e.get("active"))
        print(f"\nTotal: {len(merged)}  active={active}  inactive={len(merged) - active}")
        print("DRY-RUN: data/products.json was NOT modified.")
        return 0

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
