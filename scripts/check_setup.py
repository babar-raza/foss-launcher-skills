"""check_setup.py — Validate operator environment before content-writing skills run.

CLI:
    python scripts/check_setup.py [--family <family> --platform <platform>]

Exit codes:
    0: OK   — all checks passed
    1: WARN — non-fatal issues found
    2: ERROR — fatal issues
"""
import argparse
import importlib
import sys
from pathlib import Path

# Allow direct execution as well as import
sys.path.insert(0, str(Path(__file__).resolve().parent))

import yaml  # noqa: E402

import config_loader  # noqa: E402 (must come after sys.path manipulation)
from config_loader import ConfigError  # noqa: E402

# ---------------------------------------------------------------------------
# Level constants
# ---------------------------------------------------------------------------
OK = "OK"
NOTE = "NOTE"   # informational: optional feature unavailable; does not affect exit code
WARN = "WARN"
ERROR = "ERROR"

_LEVEL_RANK = {OK: 0, NOTE: 0, WARN: 1, ERROR: 2}

# Knowledge readiness thresholds — override via config.yaml:knowledge_readiness
_DEFAULT_MIN_CLAIMS = 50
_DEFAULT_MIN_CLASSES = 10

# Required and optional packages
_REQUIRED_PACKAGES = ["yaml", "json", "pathlib"]
_OPTIONAL_PACKAGES = {
    "tree_sitter": "tree-sitter language packs required for repo-scout",
}


# ---------------------------------------------------------------------------
# Core check function (unit-testable; no I/O side-effects except return value)
# ---------------------------------------------------------------------------

def check_setup(
    config: dict,
    content_root: Path | None,
    family: str = "",
    platform: str = "",
    _required_packages: list[str] | None = None,
    _optional_packages: dict[str, str] | None = None,
    _min_claims: int | None = None,
    _min_classes: int | None = None,
) -> list[tuple[str, str]]:
    """Run all environment checks and return a list of (level, message) tuples.

    Args:
        config: Parsed config dict (may be empty if config.yaml absent).
        content_root: Resolved content repo root path (or None to trigger error).
        family: Optional product family for knowledge model check.
        platform: Optional product platform for knowledge model check.

    Returns:
        List of (level, message) pairs — one per check.
    """
    req_pkgs = _required_packages if _required_packages is not None else _REQUIRED_PACKAGES
    opt_pkgs = _optional_packages if _optional_packages is not None else _OPTIONAL_PACKAGES

    readiness_cfg = config.get("knowledge_readiness", {})
    min_claims = _min_claims if _min_claims is not None else readiness_cfg.get(
        "min_claims", _DEFAULT_MIN_CLAIMS
    )
    min_classes = _min_classes if _min_classes is not None else readiness_cfg.get(
        "min_classes", _DEFAULT_MIN_CLASSES
    )

    issues: list[tuple[str, str]] = []

    # -------------------------------------------------------------------------
    # Check 1: config.yaml present
    # -------------------------------------------------------------------------
    if not config:
        issues.append((WARN, "config.yaml not found or empty — using defaults"))
    else:
        issues.append((OK, "config.yaml loaded"))

    # -------------------------------------------------------------------------
    # Check 2: CONTENT_REPO_PATH
    # -------------------------------------------------------------------------
    if content_root is None:
        issues.append((ERROR, "CONTENT_REPO_PATH not set and config.yaml:content_repo is empty"))
    else:
        cwd = Path.cwd().resolve()
        if content_root.resolve() == cwd:
            # Fallback to CWD — only acceptable if there's an actual content/ dir
            content_dir = cwd / "content"
            if content_dir.is_dir():
                issues.append((
                    WARN,
                    f"CONTENT_REPO_PATH fell back to CWD ({cwd}) — "
                    "content/ dir present, but explicit path is recommended",
                ))
            else:
                issues.append((
                    ERROR,
                    f"CONTENT_REPO_PATH not set and config.yaml:content_repo is empty "
                    f"(fell back to CWD: {cwd})",
                ))
        else:
            issues.append((OK, f"CONTENT_REPO_PATH resolved to {content_root}"))

    # -------------------------------------------------------------------------
    # Check 3: Required packages
    # -------------------------------------------------------------------------
    for pkg in req_pkgs:
        try:
            importlib.import_module(pkg)
            issues.append((OK, f"package '{pkg}' importable"))
        except ImportError:
            issues.append((ERROR, f"package '{pkg}' not installed — required"))

    # -------------------------------------------------------------------------
    # Check 4: Optional packages
    # -------------------------------------------------------------------------
    for pkg, note in opt_pkgs.items():
        try:
            importlib.import_module(pkg)
            issues.append((OK, f"package '{pkg}' importable"))
        except ImportError:
            issues.append((NOTE, f"package '{pkg}' not installed — {note}"))

    # -------------------------------------------------------------------------
    # Check 5: Knowledge model existence and readiness (family + platform required)
    # -------------------------------------------------------------------------
    if family and platform:
        # Knowledge lives in the skills repo (CWD), not the content repo.
        # Use config.yaml:knowledge_root if set; otherwise default to knowledge/.
        knowledge_root = config.get("knowledge_root", "knowledge")
        merged_dir = Path(knowledge_root) / family / platform / "merged"
        index_file = merged_dir / "index.json"
        model_file = merged_dir / "model.yaml"

        if not model_file.exists():
            issues.append((
                ERROR,
                f"knowledge/{family}/{platform}/merged/model.yaml not found "
                "— run S-34 (repo-scout) -> S-35 (truth-merge) -> S-31 (truth-index) first",
            ))
        elif not index_file.exists():
            issues.append((
                ERROR,
                f"knowledge/{family}/{platform}/merged/index.json not found "
                "— run S-31 (truth-index) to generate it",
            ))
        else:
            issues.append((OK, f"knowledge/{family}/{platform}/merged/ artifacts found"))

            # Readiness check: is the knowledge model substantive enough for generation?
            try:
                model_data = yaml.safe_load(model_file.read_text(encoding="utf-8")) or {}
                stats = model_data.get("stats", {})
                claims = stats.get("merged_claims", stats.get("scout_claims", 0))
                classes = stats.get("class_count", 0)

                # Staleness check
                stale_since = model_data.get("stale_since")
                if stale_since:
                    issues.append((
                        ERROR,
                        f"knowledge/{family}/{platform} is stale since {stale_since} "
                        "— run S-12 (knowledge-diff) -> S-14 (knowledge-update) before writing content",
                    ))
                else:
                    issues.append((OK, "knowledge model is current (stale_since: null)"))

                # Depth check
                if claims < min_claims:
                    issues.append((
                        ERROR,
                        f"knowledge/{family}/{platform} has only {claims} claims "
                        f"(minimum {min_claims}) — knowledge is too thin for reliable generation. "
                        "Run S-14 (knowledge-update) or S-34 (repo-scout) to enrich.",
                    ))
                elif classes < min_classes:
                    issues.append((
                        ERROR,
                        f"knowledge/{family}/{platform} has only {classes} classes "
                        f"(minimum {min_classes}) — knowledge is skeletal. "
                        "Run S-34 (repo-scout) -> S-35 (truth-merge) to bootstrap.",
                    ))
                else:
                    issues.append((
                        OK,
                        f"knowledge ready: {claims} claims, {classes} classes "
                        f"(thresholds: {min_claims} claims, {min_classes} classes)",
                    ))

            except Exception as exc:
                issues.append((WARN, f"Could not read model.yaml stats: {exc}"))

    return issues


# ---------------------------------------------------------------------------
# CLI helpers
# ---------------------------------------------------------------------------

def _print_issues(issues: list[tuple[str, str]]) -> int:
    """Print all issues and return the worst exit code (0/1/2)."""
    worst = 0
    for level, msg in issues:
        pad = level.ljust(5)
        print(f"{pad}  {msg}")
        rank = _LEVEL_RANK.get(level, 0)
        if rank > worst:
            worst = rank
    return worst


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate operator environment for foss-launcher-skills."
    )
    parser.add_argument("--family", default="", help="Product family (e.g. words)")
    parser.add_argument("--platform", default="", help="Product platform (e.g. python)")
    args = parser.parse_args(argv)

    try:
        config = config_loader.load_config()
    except ConfigError as exc:
        print(f"ERROR  {exc}")
        return 2

    try:
        content_root = config_loader.resolve_content_repo()
    except ConfigError as exc:
        content_root = None
        # Pass None so check_setup reports it as ERROR in its Check 2
        _config_error_msg = str(exc)
    else:
        _config_error_msg = None

    issues = check_setup(
        config=config,
        content_root=content_root,
        family=args.family,
        platform=args.platform,
    )

    # If resolve_content_repo raised, inject that as an explicit ERROR
    if _config_error_msg:
        issues = [(ERROR, _config_error_msg)] + [
            (lvl, msg) for lvl, msg in issues
            if "CONTENT_REPO_PATH" not in msg  # drop the duplicate check
        ]

    return _print_issues(issues)


if __name__ == "__main__":
    sys.exit(main())
