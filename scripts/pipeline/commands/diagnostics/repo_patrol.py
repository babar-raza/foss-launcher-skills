"""Repo patrol — discovery scan, change sweep, and combined reporting.

Subcommands:
    scan   Scan GitHub orgs, diff against registry, score confidence for new repos.
    sweep  Batch SHA comparison across all active launched products.
    report Generate a combined human-readable markdown report from latest scan+sweep.

Usage:
    python scripts/pipeline/commands/diagnostics/repo_patrol.py scan  [--apply] [--inactive-days N] [--force] [--orgs ORG,...]
    python scripts/pipeline/commands/diagnostics/repo_patrol.py sweep
    python scripts/pipeline/commands/diagnostics/repo_patrol.py report

Default behaviour:
    scan:   dry-run — produces patrol_report.json only; --apply also writes to products.json.
    sweep:  read-only — fetches upstream clones, compares SHAs, writes sweep_report.json.
    report: read-only — reads latest reports and generates combined_report.md.

Environment:
    GITHUB_TOKEN   GitHub personal access token (needed for scan).
    ASPOSE_ORG     Comma-separated GitHub organisations (overrides default 25).

Output:
    reports/discovery/patrol_report.json
    reports/discovery/sweep_report.json
    reports/discovery/combined_report.md
    reports/discovery/history/YYYY-MM-DD-patrol.json
    reports/discovery/history/YYYY-MM-DD-sweep.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

_PIPELINE_DIR = Path(__file__).resolve().parents[2]  # commands/diagnostics/ -> commands/ -> pipeline/
if str(_PIPELINE_DIR) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_DIR))

from core.env_loader import load_env  # noqa: E402
load_env()

# ---------------------------------------------------------------------------
# Module-level paths (overridable via configure() for testing)
# ---------------------------------------------------------------------------
_DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[4]
REPO_ROOT = _DEFAULT_REPO_ROOT
DATA_DIR = REPO_ROOT / "data"
REGISTRY_PATH = DATA_DIR / "products.json"
KNOWLEDGE_ROOT = REPO_ROOT / "knowledge"
REPORTS_DIR = REPO_ROOT / "reports" / "discovery"
HISTORY_DIR = REPORTS_DIR / "history"


def configure(*, repo_root: "Path | str | None" = None) -> None:
    """Override module-level path constants for testing."""
    global REPO_ROOT, DATA_DIR, REGISTRY_PATH, KNOWLEDGE_ROOT, REPORTS_DIR, HISTORY_DIR
    REPO_ROOT = Path(repo_root) if repo_root is not None else _DEFAULT_REPO_ROOT
    DATA_DIR = REPO_ROOT / "data"
    REGISTRY_PATH = DATA_DIR / "products.json"
    KNOWLEDGE_ROOT = REPO_ROOT / "knowledge"
    REPORTS_DIR = REPO_ROOT / "reports" / "discovery"
    HISTORY_DIR = REPORTS_DIR / "history"


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_DEFAULT_INACTIVE_DAYS = 180


# ---------------------------------------------------------------------------
# Registry I/O
# ---------------------------------------------------------------------------

def _load_registry() -> list[dict]:
    if not REGISTRY_PATH.is_file():
        return []
    try:
        return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        print(f"WARN: could not read registry: {exc}", file=sys.stderr)
        return []


def _save_registry(data: list[dict]) -> None:
    REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp_fd, tmp_path = tempfile.mkstemp(dir=REGISTRY_PATH.parent, suffix=".tmp")
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
        Path(tmp_path).replace(REGISTRY_PATH)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def _key(entry: dict) -> tuple[str, str]:
    return (entry["family"], entry["platform"])


# ---------------------------------------------------------------------------
# Registry exclusions (data/registry_exclusions.json)
# ---------------------------------------------------------------------------
# Duplicated in update_product_registry.py per PIPELINE.md's "2 scripts need it
# -> duplicate and comment" rule (no lib/ module for exactly 2 consumers).

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


# ---------------------------------------------------------------------------
# Report I/O
# ---------------------------------------------------------------------------

def _write_report(filename: str, data: dict) -> Path:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    path = REPORTS_DIR / filename
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def _archive_report(filename: str, data: dict) -> Path:
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    today = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
    prefix = filename.replace("_report.json", "")
    dest = HISTORY_DIR / f"{today}-{prefix}.json"
    dest.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return dest


def _read_report(filename: str) -> dict | None:
    path = REPORTS_DIR / filename
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


# ---------------------------------------------------------------------------
# Confidence scoring
# ---------------------------------------------------------------------------

def score_confidence(repo: dict, *, clone_path: "Path | None" = None) -> float:
    """Score a repository's readiness for documentation (0.0 - 1.0).

    Signals used (all from GitHub API metadata or shallow clone):
    - has_description:  repo has a non-empty description           (+0.10)
    - recently_pushed:  pushed_at within 180 days                  (+0.20)
    - not_archived:     repo is not archived                       (+0.15)
    - has_readme:       clone has a README file                    (+0.15)
    - has_src_files:    clone has source files (*.py, *.java, etc) (+0.25)
    - name_matches:     name matches FOSS naming convention        (+0.15)

    When no clone is available, max score is 0.35.
    """
    score = 0.0

    # API-only signals
    if repo.get("description"):
        score += 0.10
    if repo.get("pushed_at") and _is_recently_pushed(repo["pushed_at"]):
        score += 0.20
    if not repo.get("archived", False):
        score += 0.15

    # Name quality signal
    from commands.ops.update_product_registry import _classify_repo, _REPO_PATTERN_FOSS
    pair = _classify_repo(repo.get("name", ""))
    if pair is not None:
        m = _REPO_PATTERN_FOSS.match(repo.get("name", ""))
        if m:
            score += 0.15  # new convention match
        else:
            score += 0.05  # legacy convention

    # Clone-based signals
    if clone_path and clone_path.is_dir():
        readme_names = ["README.md", "README.rst", "README.txt", "README"]
        if any((clone_path / n).is_file() for n in readme_names):
            score += 0.15

        src_extensions = {".py", ".java", ".cs", ".ts", ".js", ".cpp", ".h", ".go"}
        has_src = False
        for child in clone_path.rglob("*"):
            if child.suffix in src_extensions and child.is_file():
                has_src = True
                break
        if has_src:
            score += 0.25

    return min(score, 1.0)


def _is_recently_pushed(pushed_at: str, days: int = _DEFAULT_INACTIVE_DAYS) -> bool:
    if not pushed_at:
        return False
    try:
        dt = datetime.fromisoformat(pushed_at.replace("Z", "+00:00"))
        age = datetime.now(tz=timezone.utc) - dt
        return age.days <= days
    except ValueError:
        return False


# ---------------------------------------------------------------------------
# Scan subcommand
# ---------------------------------------------------------------------------

def cmd_scan(
    *,
    orgs: list[str] | None = None,
    token: str | None = None,
    apply: bool = False,
    inactive_days: int = _DEFAULT_INACTIVE_DAYS,
    force: bool = False,
) -> dict:
    """Scan GitHub orgs and produce a patrol report.

    Returns the patrol report dict.
    """
    from lib.org_scanner import scan_orgs
    from commands.ops.update_product_registry import _classify_repo, _DEFAULT_ORGS

    if orgs is None:
        env_orgs = os.environ.get("ASPOSE_ORG", "")
        orgs = [o.strip() for o in env_orgs.split(",") if o.strip()] if env_orgs else list(_DEFAULT_ORGS)

    registry = _load_registry()
    registry_index = {_key(e): e for e in registry}
    exclusions = _load_exclusions()

    print(f"Scanning {len(orgs)} GitHub orgs...", file=sys.stderr)
    all_repos = scan_orgs(orgs, token=token)
    print(f"  Found {len(all_repos)} total repos", file=sys.stderr)

    now = datetime.now(tz=timezone.utc).isoformat()

    new_candidates: list[dict] = []
    status_changes: list[dict] = []
    unclassifiable: list[dict] = []
    skipped: list[dict] = []
    excluded_count = 0

    for repo in all_repos:
        if _is_excluded(exclusions, repo_name=repo["name"]):
            # Permanently excluded (e.g. not a docs-able product type) — do not
            # surface as unclassifiable noise or re-evaluate every scan.
            excluded_count += 1
            continue

        pair = _classify_repo(repo["name"])
        if pair is None:
            unclassifiable.append({
                "repo_name": repo["name"],
                "html_url": repo.get("html_url", ""),
                "reason": "name does not match FOSS or legacy naming pattern",
            })
            continue

        family, platform = pair
        if _is_excluded(exclusions, family=family, platform=platform):
            excluded_count += 1
            continue

        k = (family, platform)

        if k in registry_index:
            existing = registry_index[k]
            existing_status = existing.get("status", "launched")

            if existing_status == "launched":
                if repo.get("archived"):
                    status_changes.append({
                        "family": family,
                        "platform": platform,
                        "change": "newly_archived",
                        "repo_name": repo["name"],
                    })
                elif not _is_recently_pushed(repo.get("pushed_at", ""), inactive_days):
                    status_changes.append({
                        "family": family,
                        "platform": platform,
                        "change": "gone_inactive",
                        "repo_name": repo["name"],
                        "pushed_at": repo.get("pushed_at", ""),
                        "inactive_days": inactive_days,
                    })
                else:
                    skipped.append({"family": family, "platform": platform, "reason": "launched, no change"})
            elif existing_status == "rejected" and not force:
                skipped.append({
                    "family": family,
                    "platform": platform,
                    "reason": "previously rejected",
                    "rejection_reason": existing.get("rejection_reason", ""),
                })
                existing["last_scanned_at"] = now
            elif existing_status in ("candidate", "investigating"):
                conf = score_confidence(repo)
                existing["confidence"] = round(conf, 2)
                existing["last_scanned_at"] = now
                skipped.append({
                    "family": family,
                    "platform": platform,
                    "reason": f"existing {existing_status}, re-scored to {conf:.2f}",
                })
            continue

        # New repo
        conf = score_confidence(repo)
        conf = round(conf, 2)

        if conf >= 0.70:
            action = "launch_candidate"
            status = "candidate"
        elif conf >= 0.40:
            action = "investigate"
            status = "investigating"
        else:
            action = "likely_placeholder"
            status = None

        entry_data = {
            "family": family,
            "platform": platform,
            "repo_name": repo["name"],
            "html_url": repo.get("html_url", ""),
            "confidence": conf,
            "action": action,
            "pushed_at": repo.get("pushed_at", ""),
            "archived": repo.get("archived", False),
            "description": repo.get("description", ""),
        }

        if status is None:
            unclassifiable.append({
                **entry_data,
                "reason": f"confidence {conf:.2f} below 0.40 threshold",
            })
        else:
            new_candidates.append(entry_data)

            if apply:
                new_entry = {
                    "family": family,
                    "platform": platform,
                    "repo_name": repo["name"],
                    "repo_url": repo.get("html_url", ""),
                    "clone_url": repo.get("clone_url", ""),
                    "active": not repo.get("archived", False) and _is_recently_pushed(
                        repo.get("pushed_at", ""), inactive_days
                    ),
                    "discovered_via": "github",
                    "status": status,
                    "confidence": conf,
                    "first_seen_at": now,
                    "last_scanned_at": now,
                    "rejection_reason": None,
                }
                registry.append(new_entry)
                registry_index[k] = new_entry

    report = {
        "generated_at": now,
        "orgs_scanned": orgs,
        "total_repos": len(all_repos),
        "registry_applied": apply,
        "inactive_days_threshold": inactive_days,
        "new_candidates": new_candidates,
        "status_changes": status_changes,
        "unclassifiable": unclassifiable,
        "skipped_count": len(skipped),
        "excluded_count": excluded_count,
        "summary": {
            "new_candidates": len(new_candidates),
            "status_changes": len(status_changes),
            "unclassifiable": len(unclassifiable),
            "skipped": len(skipped),
            "excluded": excluded_count,
        },
    }

    _write_report("patrol_report.json", report)
    _archive_report("patrol_report.json", report)

    if apply:
        sorted_reg = sorted(registry, key=lambda e: (e["family"], e["platform"]))
        _save_registry(sorted_reg)
        print(f"  Registry updated: {len(new_candidates)} new entries added", file=sys.stderr)

    print(f"  Patrol report: {report['summary']}", file=sys.stderr)
    return report


# ---------------------------------------------------------------------------
# Sweep subcommand
# ---------------------------------------------------------------------------

def cmd_sweep() -> dict:
    """Batch SHA comparison across all active launched products.

    Returns the sweep report dict.
    """
    from core.clone_cache import clone_exists, clone_head_sha, update_clone

    registry = _load_registry()
    now = datetime.now(tz=timezone.utc).isoformat()

    changed: list[dict] = []
    unchanged: list[dict] = []
    fetch_failures: list[dict] = []

    active_launched = [
        e for e in registry
        if e.get("active") and e.get("status", "launched") == "launched"
    ]

    print(f"Sweeping {len(active_launched)} active launched products...", file=sys.stderr)

    for entry in active_launched:
        family = entry["family"]
        platform = entry["platform"]

        if not clone_exists(family, platform):
            fetch_failures.append({
                "family": family,
                "platform": platform,
                "error": "no local clone exists",
            })
            continue

        stored_sha = _get_stored_sha(family, platform)

        new_sha = update_clone(family, platform)
        if new_sha is None:
            new_sha = clone_head_sha(family, platform)
            if new_sha is None:
                fetch_failures.append({
                    "family": family,
                    "platform": platform,
                    "error": "fetch failed and no existing HEAD",
                })
                continue

        if stored_sha and stored_sha == new_sha:
            unchanged.append({
                "family": family,
                "platform": platform,
                "sha": new_sha,
            })
        else:
            impact = _classify_impact(family, platform, stored_sha, new_sha)
            changed.append({
                "family": family,
                "platform": platform,
                "stored_sha": stored_sha,
                "current_sha": new_sha,
                "impact": impact,
            })

    report = {
        "generated_at": now,
        "total_products": len(active_launched),
        "changed": changed,
        "unchanged": unchanged,
        "fetch_failures": fetch_failures,
        "summary": {
            "changed": len(changed),
            "unchanged": len(unchanged),
            "fetch_failures": len(fetch_failures),
            "high_impact": sum(1 for c in changed if c["impact"] == "HIGH"),
            "medium_impact": sum(1 for c in changed if c["impact"] == "MEDIUM"),
            "low_impact": sum(1 for c in changed if c["impact"] == "LOW"),
        },
    }

    _write_report("sweep_report.json", report)
    _archive_report("sweep_report.json", report)

    print(f"  Sweep report: {report['summary']}", file=sys.stderr)
    return report


def _get_stored_sha(family: str, platform: str) -> str | None:
    """Read repo_sha from knowledge/{family}/{platform}/merged/model.yaml."""
    model_path = KNOWLEDGE_ROOT / family / platform / "merged" / "model.yaml"
    if not model_path.is_file():
        return None
    try:
        text = model_path.read_text(encoding="utf-8")
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("repo_sha:"):
                val = stripped.split(":", 1)[1].strip().strip("'\"")
                return val if val else None
        return None
    except OSError:
        return None


def _classify_impact(
    family: str,
    platform: str,
    stored_sha: str | None,
    current_sha: str,
) -> str:
    """Classify the impact of a SHA change as HIGH, MEDIUM, or LOW.

    - No stored SHA → HIGH
    - Source files changed → HIGH
    - Only non-source files changed → LOW
    - Cannot determine → MEDIUM
    """
    if stored_sha is None:
        return "HIGH"

    from core.clone_cache import clone_path
    cp = clone_path(family, platform)
    if not cp.is_dir():
        return "MEDIUM"

    try:
        import subprocess
        result = subprocess.run(
            ["git", "diff", "--name-only", stored_sha, current_sha],
            cwd=str(cp),
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            return "MEDIUM"

        changed_files = result.stdout.strip().splitlines()
        if not changed_files:
            return "LOW"

        api_extensions = {".py", ".java", ".cs", ".ts", ".js", ".cpp", ".h", ".hpp"}
        api_files = [f for f in changed_files if Path(f).suffix in api_extensions]

        if api_files:
            return "HIGH"
        else:
            return "LOW"
    except Exception:
        return "MEDIUM"


# ---------------------------------------------------------------------------
# Report subcommand
# ---------------------------------------------------------------------------

def cmd_report() -> str:
    """Generate a combined human-readable markdown report.

    Returns the markdown text.
    """
    patrol = _read_report("patrol_report.json")
    sweep = _read_report("sweep_report.json")
    now = datetime.now(tz=timezone.utc).isoformat()

    lines = [
        "# Discovery & Change Detection — Combined Report",
        "",
        f"Generated: {now}",
        "",
    ]

    if patrol:
        lines.append("## Patrol Scan")
        lines.append("")
        lines.append(f"- **Scan time**: {patrol.get('generated_at', 'unknown')}")
        lines.append(f"- **Orgs scanned**: {len(patrol.get('orgs_scanned', []))}")
        lines.append(f"- **Total repos found**: {patrol.get('total_repos', 0)}")
        lines.append(f"- **Registry applied**: {patrol.get('registry_applied', False)}")
        lines.append("")

        summary = patrol.get("summary", {})
        lines.append("| Metric | Count |")
        lines.append("|--------|-------|")
        lines.append(f"| New candidates | {summary.get('new_candidates', 0)} |")
        lines.append(f"| Status changes | {summary.get('status_changes', 0)} |")
        lines.append(f"| Unclassifiable | {summary.get('unclassifiable', 0)} |")
        lines.append(f"| Skipped (no change) | {summary.get('skipped', 0)} |")
        lines.append("")

        candidates = patrol.get("new_candidates", [])
        if candidates:
            lines.append("### New Candidates")
            lines.append("")
            lines.append("| Family | Platform | Confidence | Action | Repo |")
            lines.append("|--------|----------|------------|--------|------|")
            for c in candidates:
                lines.append(
                    f"| {c['family']} | {c['platform']} | {c['confidence']:.2f} "
                    f"| {c['action']} | {c.get('repo_name', '')} |"
                )
            lines.append("")

        changes = patrol.get("status_changes", [])
        if changes:
            lines.append("### Status Changes")
            lines.append("")
            lines.append("| Family | Platform | Change | Repo |")
            lines.append("|--------|----------|--------|------|")
            for c in changes:
                lines.append(
                    f"| {c['family']} | {c['platform']} | {c['change']} | {c.get('repo_name', '')} |"
                )
            lines.append("")

        unclass = patrol.get("unclassifiable", [])
        if unclass:
            lines.append("### Unclassifiable Repos")
            lines.append("")
            lines.append("| Repo | Reason |")
            lines.append("|------|--------|")
            for u in unclass:
                lines.append(f"| {u.get('repo_name', '')} | {u.get('reason', '')} |")
            lines.append("")
    else:
        lines.append("## Patrol Scan")
        lines.append("")
        lines.append("_No patrol report found. Run `repo_patrol.py scan` first._")
        lines.append("")

    if sweep:
        lines.append("## Change Sweep")
        lines.append("")
        lines.append(f"- **Sweep time**: {sweep.get('generated_at', 'unknown')}")
        lines.append(f"- **Products swept**: {sweep.get('total_products', 0)}")
        lines.append("")

        summary = sweep.get("summary", {})
        lines.append("| Metric | Count |")
        lines.append("|--------|-------|")
        lines.append(f"| Changed (HIGH) | {summary.get('high_impact', 0)} |")
        lines.append(f"| Changed (MEDIUM) | {summary.get('medium_impact', 0)} |")
        lines.append(f"| Changed (LOW) | {summary.get('low_impact', 0)} |")
        lines.append(f"| Unchanged | {summary.get('unchanged', 0)} |")
        lines.append(f"| Fetch failures | {summary.get('fetch_failures', 0)} |")
        lines.append("")

        changed = sweep.get("changed", [])
        if changed:
            lines.append("### Changed Products")
            lines.append("")
            lines.append("| Family | Platform | Impact | Stored SHA | Current SHA |")
            lines.append("|--------|----------|--------|------------|-------------|")
            for c in changed:
                stored = (c.get("stored_sha") or "none")[:8]
                current = (c.get("current_sha") or "none")[:8]
                lines.append(
                    f"| {c['family']} | {c['platform']} | {c['impact']} "
                    f"| `{stored}` | `{current}` |"
                )
            lines.append("")

        failures = sweep.get("fetch_failures", [])
        if failures:
            lines.append("### Fetch Failures")
            lines.append("")
            lines.append("| Family | Platform | Error |")
            lines.append("|--------|----------|-------|")
            for f in failures:
                lines.append(f"| {f['family']} | {f['platform']} | {f.get('error', '')} |")
            lines.append("")
    else:
        lines.append("## Change Sweep")
        lines.append("")
        lines.append("_No sweep report found. Run `repo_patrol.py sweep` first._")
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("_This report is informational. Run `/discovery-triage` to route findings to backlog._")
    lines.append("")

    md = "\n".join(lines)

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    (REPORTS_DIR / "combined_report.md").write_text(md, encoding="utf-8")

    print("  Combined report written to reports/discovery/combined_report.md", file=sys.stderr)
    return md


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Repo patrol — discovery scan, change sweep, and reporting"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_scan = sub.add_parser("scan", help="Scan GitHub orgs for new/changed repos")
    p_scan.add_argument("--apply", action="store_true",
                        help="Write discovered candidates to products.json (default: dry-run)")
    p_scan.add_argument("--inactive-days", type=int, default=_DEFAULT_INACTIVE_DAYS,
                        help=f"Days since last push to consider inactive (default: {_DEFAULT_INACTIVE_DAYS})")
    p_scan.add_argument("--force", action="store_true",
                        help="Re-evaluate rejected repos")
    p_scan.add_argument("--orgs", default=None,
                        help="Comma-separated GitHub orgs to scan (overrides default)")
    p_scan.add_argument("--token", default=None,
                        help="GitHub token (falls back to GITHUB_TOKEN env var)")

    sub.add_parser("sweep", help="Batch SHA comparison across active launched products")

    sub.add_parser("report", help="Generate combined markdown report")

    args = parser.parse_args(argv)

    if args.command == "scan":
        orgs = [o.strip() for o in args.orgs.split(",") if o.strip()] if args.orgs else None
        token = args.token or os.environ.get("GITHUB_TOKEN")
        cmd_scan(
            orgs=orgs,
            token=token,
            apply=args.apply,
            inactive_days=args.inactive_days,
            force=args.force,
        )
    elif args.command == "sweep":
        cmd_sweep()
    elif args.command == "report":
        cmd_report()

    return 0


if __name__ == "__main__":
    sys.exit(main())
