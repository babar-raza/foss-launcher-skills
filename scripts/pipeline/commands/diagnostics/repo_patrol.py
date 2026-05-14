#!/usr/bin/env python3
"""Repo patrol: discovery scan, change sweep, and combined reporting."""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PIPELINE_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT_DEFAULT = Path(__file__).resolve().parents[4]
if str(PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(PIPELINE_ROOT))
if str(REPO_ROOT_DEFAULT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT_DEFAULT))

REPO_ROOT = REPO_ROOT_DEFAULT
DATA_DIR = REPO_ROOT / "data"
REGISTRY_PATH = DATA_DIR / "products.json"
KNOWLEDGE_ROOT = REPO_ROOT / "knowledge"
REPORTS_DIR = REPO_ROOT / "reports" / "discovery"
HISTORY_DIR = REPORTS_DIR / "history"
_DEFAULT_INACTIVE_DAYS = 180


def configure(*, repo_root: Path | str | None = None) -> None:
    global REPO_ROOT, DATA_DIR, REGISTRY_PATH, KNOWLEDGE_ROOT, REPORTS_DIR, HISTORY_DIR
    REPO_ROOT = Path(repo_root).resolve() if repo_root is not None else REPO_ROOT_DEFAULT
    DATA_DIR = REPO_ROOT / "data"
    REGISTRY_PATH = DATA_DIR / "products.json"
    KNOWLEDGE_ROOT = REPO_ROOT / "knowledge"
    REPORTS_DIR = REPO_ROOT / "reports" / "discovery"
    HISTORY_DIR = REPORTS_DIR / "history"


def _load_registry() -> list[dict[str, Any]]:
    if not REGISTRY_PATH.is_file():
        return []
    try:
        data = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return data if isinstance(data, list) else []


def _save_registry(data: list[dict[str, Any]]) -> None:
    REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=REGISTRY_PATH.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
        Path(tmp).replace(REGISTRY_PATH)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _write_report(filename: str, data: dict[str, Any]) -> Path:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    path = REPORTS_DIR / filename
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def _archive_report(filename: str, data: dict[str, Any]) -> Path:
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    stem = filename.replace("_report.json", "")
    path = HISTORY_DIR / f"{today}-{stem}.json"
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def _read_report(filename: str) -> dict[str, Any] | None:
    path = REPORTS_DIR / filename
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _key(entry: dict[str, Any]) -> tuple[str, str]:
    return str(entry.get("family", "")), str(entry.get("platform", ""))


def _is_recently_pushed(pushed_at: str, days: int = _DEFAULT_INACTIVE_DAYS) -> bool:
    if not pushed_at:
        return False
    try:
        dt = datetime.fromisoformat(pushed_at.replace("Z", "+00:00"))
    except ValueError:
        return False
    return (datetime.now(timezone.utc) - dt).days <= days


def _classify_repo_name(repo_name: str) -> tuple[str, str] | None:
    try:
        from commands.ops.update_product_registry import _classify_repo
    except Exception:
        from update_product_registry import _classify_repo  # type: ignore
    return _classify_repo(repo_name)


def score_confidence(repo: dict[str, Any], *, clone_path: Path | None = None) -> float:
    score = 0.0
    if repo.get("description"):
        score += 0.10
    if _is_recently_pushed(str(repo.get("pushed_at", ""))):
        score += 0.20
    if not repo.get("archived", False):
        score += 0.15
    if _classify_repo_name(str(repo.get("name", ""))) is not None:
        score += 0.15 if str(repo.get("name", "")).startswith("Aspose.") else 0.05
    if clone_path and clone_path.is_dir():
        if any((clone_path / name).is_file() for name in ("README.md", "README.rst", "README.txt", "README")):
            score += 0.15
        source_exts = {".py", ".java", ".cs", ".ts", ".js", ".cpp", ".h", ".hpp"}
        if any(path.is_file() and path.suffix in source_exts for path in clone_path.rglob("*")):
            score += 0.25
    return min(score, 1.0)


def _scan_orgs(orgs: list[str], token: str | None) -> list[dict[str, Any]]:
    try:
        from org_scanner import scan_orgs
    except Exception:
        from commands.launch.site_planner import scan_orgs  # type: ignore
    return scan_orgs(orgs, token=token)


def cmd_scan(
    *,
    orgs: list[str] | None = None,
    token: str | None = None,
    apply: bool = False,
    inactive_days: int = _DEFAULT_INACTIVE_DAYS,
    force: bool = False,
    repos: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    try:
        from commands.ops.update_product_registry import _DEFAULT_ORGS
    except Exception:
        from update_product_registry import _DEFAULT_ORGS  # type: ignore

    if orgs is None:
        env_orgs = os.environ.get("ASPOSE_ORG", "")
        orgs = [item.strip() for item in env_orgs.split(",") if item.strip()] if env_orgs else list(_DEFAULT_ORGS)

    registry = _load_registry()
    registry_index = {_key(entry): entry for entry in registry}
    all_repos = repos if repos is not None else _scan_orgs(orgs, token)
    now = datetime.now(timezone.utc).isoformat()

    new_candidates: list[dict[str, Any]] = []
    status_changes: list[dict[str, Any]] = []
    unclassifiable: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []

    for repo in all_repos:
        pair = _classify_repo_name(str(repo.get("name", "")))
        if pair is None:
            unclassifiable.append({
                "repo_name": repo.get("name", ""),
                "html_url": repo.get("html_url", ""),
                "reason": "name does not match FOSS or legacy naming pattern",
            })
            continue
        family, platform = pair
        existing = registry_index.get((family, platform))
        if existing:
            if existing.get("status") == "rejected" and not force:
                skipped.append({"family": family, "platform": platform, "reason": "previously rejected"})
                continue
            if repo.get("archived"):
                status_changes.append({"family": family, "platform": platform, "change": "newly_archived", "repo_name": repo.get("name", "")})
            elif not _is_recently_pushed(str(repo.get("pushed_at", "")), inactive_days):
                status_changes.append({"family": family, "platform": platform, "change": "gone_inactive", "repo_name": repo.get("name", "")})
            else:
                skipped.append({"family": family, "platform": platform, "reason": "known active product"})
            continue

        confidence = score_confidence(repo)
        action = "candidate" if confidence >= 0.70 else "investigate" if confidence >= 0.40 else "ignore"
        candidate = {
            "family": family,
            "platform": platform,
            "repo_name": repo.get("name", ""),
            "repo_url": repo.get("html_url", ""),
            "clone_url": repo.get("clone_url", ""),
            "confidence": confidence,
            "action": action,
            "first_seen_at": now,
        }
        new_candidates.append(candidate)
        if apply and action != "ignore":
            registry.append({
                "family": family,
                "platform": platform,
                "repo_name": candidate["repo_name"],
                "repo_url": candidate["repo_url"],
                "clone_url": candidate["clone_url"],
                "active": True,
                "status": action,
                "discovered_via": "repo-patrol",
                "first_seen_at": now,
            })

    if apply:
        _save_registry(registry)

    report = {
        "generated_at": now,
        "orgs_scanned": orgs,
        "total_repos": len(all_repos),
        "registry_applied": apply,
        "new_candidates": new_candidates,
        "status_changes": status_changes,
        "unclassifiable": unclassifiable,
        "skipped": skipped,
        "summary": {
            "new_candidates": len(new_candidates),
            "status_changes": len(status_changes),
            "unclassifiable": len(unclassifiable),
            "skipped": len(skipped),
        },
    }
    _write_report("patrol_report.json", report)
    _archive_report("patrol_report.json", report)
    return report


def _get_stored_sha(family: str, platform: str) -> str | None:
    path = KNOWLEDGE_ROOT / family / platform / "merged" / "model.yaml"
    if not path.is_file():
        return None
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.strip().startswith("repo_sha:"):
            value = line.split(":", 1)[1].strip().strip("'\"")
            return value or None
    return None


def _classify_impact(family: str, platform: str, stored_sha: str | None, current_sha: str) -> str:
    if stored_sha is None:
        return "HIGH"
    try:
        from core.clone_cache import clone_path
        clone = clone_path(family, platform)
    except Exception:
        return "MEDIUM"
    if not clone.is_dir():
        return "MEDIUM"
    try:
        import subprocess
        result = subprocess.run(
            ["git", "diff", "--name-only", stored_sha, current_sha],
            cwd=str(clone),
            capture_output=True,
            text=True,
            timeout=30,
        )
    except Exception:
        return "MEDIUM"
    if result.returncode != 0:
        return "MEDIUM"
    changed = result.stdout.strip().splitlines()
    if not changed:
        return "LOW"
    source_exts = {".py", ".java", ".cs", ".ts", ".js", ".cpp", ".h", ".hpp"}
    return "HIGH" if any(Path(item).suffix in source_exts for item in changed) else "LOW"


def cmd_sweep() -> dict[str, Any]:
    try:
        from core.clone_cache import clone_exists, clone_head_sha, update_clone
    except Exception:
        from scripts.pipeline.core.clone_cache import clone_exists, clone_head_sha, update_clone

    registry = _load_registry()
    active = [
        item for item in registry
        if item.get("active", True) and item.get("status", "launched") == "launched"
    ]
    changed: list[dict[str, Any]] = []
    unchanged: list[dict[str, Any]] = []
    fetch_failures: list[dict[str, Any]] = []
    now = datetime.now(timezone.utc).isoformat()

    for item in active:
        family, platform = _key(item)
        stored_sha = _get_stored_sha(family, platform)
        if not clone_exists(family, platform):
            fetch_failures.append({"family": family, "platform": platform, "error": "clone missing"})
            continue
        current_sha = update_clone(family, platform) or clone_head_sha(family, platform)
        if current_sha is None:
            fetch_failures.append({"family": family, "platform": platform, "error": "fetch failed and no existing HEAD"})
            continue
        if stored_sha and stored_sha == current_sha:
            unchanged.append({"family": family, "platform": platform, "sha": current_sha})
        else:
            changed.append({
                "family": family,
                "platform": platform,
                "stored_sha": stored_sha,
                "current_sha": current_sha,
                "impact": _classify_impact(family, platform, stored_sha, current_sha),
            })

    report = {
        "generated_at": now,
        "total_products": len(active),
        "changed": changed,
        "unchanged": unchanged,
        "fetch_failures": fetch_failures,
        "summary": {
            "changed": len(changed),
            "unchanged": len(unchanged),
            "fetch_failures": len(fetch_failures),
            "high_impact": sum(1 for item in changed if item["impact"] == "HIGH"),
            "medium_impact": sum(1 for item in changed if item["impact"] == "MEDIUM"),
            "low_impact": sum(1 for item in changed if item["impact"] == "LOW"),
        },
    }
    _write_report("sweep_report.json", report)
    _archive_report("sweep_report.json", report)
    return report


def cmd_report() -> str:
    patrol = _read_report("patrol_report.json")
    sweep = _read_report("sweep_report.json")
    now = datetime.now(timezone.utc).isoformat()
    lines = ["# Discovery & Change Detection - Combined Report", "", f"Generated: {now}", ""]
    if patrol:
        summary = patrol.get("summary", {})
        lines.extend([
            "## Patrol Scan",
            "",
            f"- New candidates: {summary.get('new_candidates', 0)}",
            f"- Status changes: {summary.get('status_changes', 0)}",
            f"- Unclassifiable: {summary.get('unclassifiable', 0)}",
            f"- Skipped: {summary.get('skipped', 0)}",
            "",
        ])
    else:
        lines.extend(["## Patrol Scan", "", "_No patrol report found._", ""])
    if sweep:
        summary = sweep.get("summary", {})
        lines.extend([
            "## Change Sweep",
            "",
            f"- Changed: {summary.get('changed', 0)}",
            f"- Unchanged: {summary.get('unchanged', 0)}",
            f"- Fetch failures: {summary.get('fetch_failures', 0)}",
            "",
        ])
    else:
        lines.extend(["## Change Sweep", "", "_No sweep report found._", ""])
    md = "\n".join(lines)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    (REPORTS_DIR / "combined_report.md").write_text(md, encoding="utf-8")
    return md


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Repo patrol discovery and sweep utility")
    sub = parser.add_subparsers(dest="command", required=True)
    scan = sub.add_parser("scan")
    scan.add_argument("--apply", action="store_true")
    scan.add_argument("--inactive-days", type=int, default=_DEFAULT_INACTIVE_DAYS)
    scan.add_argument("--force", action="store_true")
    scan.add_argument("--orgs")
    scan.add_argument("--token")
    sub.add_parser("sweep")
    sub.add_parser("report")
    args = parser.parse_args(argv)
    if args.command == "scan":
        orgs = [item.strip() for item in args.orgs.split(",") if item.strip()] if args.orgs else None
        cmd_scan(orgs=orgs, token=args.token or os.environ.get("GITHUB_TOKEN"), apply=args.apply, inactive_days=args.inactive_days, force=args.force)
    elif args.command == "sweep":
        cmd_sweep()
    elif args.command == "report":
        cmd_report()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
