#!/usr/bin/env python3
"""Check upstream FOSS repositories for SHA drift against committed baselines.

FRESH-001 (2026-08-14): rewritten to fix the confirmed alert-fatigue failure from
the cells/net incident -- the weekly upstream-monitor.yml workflow correctly
detected drift for 11 consecutive Mondays (2026-07-20 through 2026-08-10) but only
ever filed a generic "Upstream drift detected — {date}" issue that never named the
affected product in its body (only in the raw CI log), and never deduplicated --
11 open issues, 0 comments, ignored because they looked like unactionable noise.

Two changes:
  1. Issue creation/dedup logic moved OUT of the workflow's untestable inline
     actions/github-script JS block into this testable Python module (`gh_runner`
     is an injectable seam -- tests never actually shell out to `gh`).
  2. One issue PER distinct (family, platform) finding, named and deduped by
     labels (`upstream-drift` + `product:{family}-{platform}`) -- a repeat
     finding comments on the existing open issue instead of creating a
     duplicate. data/upstream_drift_state.json (git-tracked) additionally
     persists per-product level/SHAs/checked_at/last_issue_number/
     consecutive_weeks_flagged so a fresh checkout / different session can see
     current drift state without re-querying GitHub.

Reads data/upstream_baselines.json (committed) and data/products.json,
fetches HEAD SHA from each active product's GitHub repo, and reports drift.

Exit codes:
  0 — no drift detected (all SHAs match)
  1 — drift detected (at least one HIGH or MEDIUM change)
  2 — configuration error

Requires GH_TOKEN environment variable for GitHub API access.

Usage:
    python scripts/ci/checks/check_upstream_drift.py
    python scripts/ci/checks/check_upstream_drift.py --file-issues
    python scripts/ci/checks/check_upstream_drift.py --file-issues --repo Aspose/aspose.org
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

_DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[3]
REPO_ROOT = _DEFAULT_REPO_ROOT
BASELINES_PATH = REPO_ROOT / "data" / "upstream_baselines.json"
PRODUCTS_PATH = REPO_ROOT / "data" / "products.json"
DRIFT_STATE_PATH = REPO_ROOT / "data" / "upstream_drift_state.json"

SOURCE_EXTENSIONS = frozenset({
    ".py", ".java", ".cs", ".ts", ".js", ".cpp", ".h", ".hpp",
    ".go", ".rs", ".kt", ".swift", ".rb",
})

ISSUE_LABEL = "upstream-drift"


def configure(*, repo_root: "Path | str | None" = None) -> None:
    """Override module-level path constants for testing."""
    global REPO_ROOT, BASELINES_PATH, PRODUCTS_PATH, DRIFT_STATE_PATH
    REPO_ROOT = Path(repo_root) if repo_root is not None else _DEFAULT_REPO_ROOT
    BASELINES_PATH = REPO_ROOT / "data" / "upstream_baselines.json"
    PRODUCTS_PATH = REPO_ROOT / "data" / "products.json"
    DRIFT_STATE_PATH = REPO_ROOT / "data" / "upstream_drift_state.json"


CommandRunner = Callable[..., "subprocess.CompletedProcess[str]"]


# ---------------------------------------------------------------------------
# GitHub API (drift detection) -- unchanged logic, runner now injectable
# ---------------------------------------------------------------------------

def _gh_api(endpoint: str, *, runner: CommandRunner = subprocess.run) -> "str | None":
    try:
        result = runner(
            ["gh", "api", endpoint, "--jq", ".sha"],
            capture_output=True, text=True, timeout=30,
            encoding="utf-8", errors="replace",
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return None


def _gh_compare(owner_repo: str, base: str, head: str, *, runner: CommandRunner = subprocess.run) -> str:
    try:
        result = runner(
            ["gh", "api", f"repos/{owner_repo}/compare/{base}...{head}",
             "--jq", "[.files[].filename] | join(\"\\n\")"],
            capture_output=True, text=True, timeout=60,
            encoding="utf-8", errors="replace",
        )
        if result.returncode != 0:
            return "MEDIUM"
        files = result.stdout.strip().split("\n") if result.stdout.strip() else []
        for f in files:
            if any(f.endswith(ext) for ext in SOURCE_EXTENSIONS):
                return "HIGH"
        return "LOW" if files else "NO_CHANGE"
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return "MEDIUM"


def check_drift(*, runner: CommandRunner = subprocess.run) -> dict:
    """Run the drift check. Returns {findings: [...], no_drift_count, error_count}.

    Pure(ish) function -- does not write anything, does not require GH_TOKEN to be
    validated by the caller (main() checks that before calling this).
    """
    baselines: dict = json.loads(BASELINES_PATH.read_text(encoding="utf-8"))
    products: list = json.loads(PRODUCTS_PATH.read_text(encoding="utf-8"))
    active_products = [p for p in products if p.get("active", False)]

    findings: list[dict] = []
    no_drift_count = 0
    error_count = 0

    for product in active_products:
        family, platform = product["family"], product["platform"]
        key = f"{family}/{platform}"
        stored_sha = baselines.get(key, "")
        repo_url = product.get("repo_url", "")

        if not repo_url:
            continue

        owner_repo = repo_url.replace("https://github.com/", "").rstrip("/")
        head_sha = _gh_api(f"repos/{owner_repo}/commits/HEAD", runner=runner)

        if not head_sha:
            findings.append({"family": family, "platform": platform, "level": "MEDIUM",
                              "reason": "API_FETCH_FAILED", "stored": stored_sha, "head": None})
            error_count += 1
            continue

        if not stored_sha:
            findings.append({"family": family, "platform": platform, "level": "HIGH",
                              "reason": "NO_BASELINE", "stored": None, "head": head_sha})
            continue

        if head_sha == stored_sha:
            no_drift_count += 1
            continue

        level = _gh_compare(owner_repo, stored_sha, head_sha, runner=runner)
        if level == "NO_CHANGE":
            no_drift_count += 1
            continue

        findings.append({"family": family, "platform": platform, "level": level,
                          "reason": "SHA_DRIFT", "stored": stored_sha, "head": head_sha})

    return {"findings": findings, "no_drift_count": no_drift_count, "error_count": error_count}


# ---------------------------------------------------------------------------
# Drift state persistence (git-tracked; survives a fresh checkout)
# ---------------------------------------------------------------------------

def load_drift_state() -> dict:
    try:
        return json.loads(DRIFT_STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def save_drift_state(state: dict) -> None:
    DRIFT_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    DRIFT_STATE_PATH.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def update_drift_state(state: dict, finding: dict, *, checked_at: str, issue_number: "int | None") -> dict:
    """Return a new state dict with this finding's product entry updated.

    consecutive_weeks_flagged increments only when the level is HIGH/MEDIUM (an
    active, unresolved finding); resets to 0 once a product stops appearing in
    findings (main() handles that reset for products no longer flagged).
    """
    key = f"{finding['family']}/{finding['platform']}"
    prior = state.get(key, {})
    new_state = dict(state)
    new_state[key] = {
        "level": finding["level"],
        "stored_sha": finding.get("stored"),
        "head_sha": finding.get("head"),
        "checked_at": checked_at,
        "last_issue_number": issue_number if issue_number is not None else prior.get("last_issue_number"),
        "consecutive_weeks_flagged": prior.get("consecutive_weeks_flagged", 0) + 1,
    }
    return new_state


# ---------------------------------------------------------------------------
# Issue filing (dedup by label pair; testable via injected runner)
# ---------------------------------------------------------------------------

def _product_label(family: str, platform: str) -> str:
    return f"product:{family}-{platform}"


def find_existing_issue(family: str, platform: str, *, repo: str, runner: CommandRunner) -> "int | None":
    """Search open issues carrying BOTH ISSUE_LABEL and this product's label.
    Returns the issue number, or None if no such issue is open."""
    try:
        result = runner(
            ["gh", "issue", "list", "--repo", repo,
             "--label", ISSUE_LABEL, "--label", _product_label(family, platform),
             "--state", "open", "--json", "number", "--limit", "1"],
            capture_output=True, text=True, timeout=30,
            encoding="utf-8", errors="replace",
        )
        if result.returncode != 0:
            return None
        data = json.loads(result.stdout or "[]")
        return data[0]["number"] if data else None
    except (subprocess.TimeoutExpired, FileNotFoundError, json.JSONDecodeError, KeyError, IndexError):
        return None


def _issue_body(finding: dict, *, run_url: "str | None") -> str:
    family, platform = finding["family"], finding["platform"]
    level, reason = finding["level"], finding["reason"]
    stored, head = finding.get("stored"), finding.get("head")
    lines = [
        f"## Upstream drift: {family}/{platform}",
        "",
        f"- **Impact**: {level}",
        f"- **Reason**: {reason}",
        f"- **Stored (baseline) SHA**: `{stored or 'none'}`",
        f"- **Live upstream HEAD**: `{head or 'unknown'}`",
        "",
        "### Next step",
    ]
    if reason == "NO_BASELINE":
        lines.append(f"Run `/knowledge-update {family} {platform}` to establish an initial baseline.")
    elif level == "HIGH":
        lines.append(
            f"API-surface-affecting change detected. Run `/change-sweep` to confirm impact, "
            f"then `/knowledge-update {family} {platform}` before any content generation for "
            f"this product."
        )
    else:
        lines.append(f"Run `/knowledge-update {family} {platform}` to refresh knowledge.")
    if run_url:
        lines += ["", f"Triggered by: [workflow run]({run_url})"]
    return "\n".join(lines)


def file_or_update_issue(
    finding: dict, *, repo: str, runner: CommandRunner, run_url: "str | None" = None,
) -> dict:
    """Create a new issue for this finding, or comment on the existing deduped
    issue if one is already open. Returns {"action": "created"|"commented"|"failed",
    "issue_number": int|None}."""
    family, platform = finding["family"], finding["platform"]
    existing = find_existing_issue(family, platform, repo=repo, runner=runner)
    body = _issue_body(finding, run_url=run_url)

    if existing is not None:
        try:
            result = runner(
                ["gh", "issue", "comment", str(existing), "--repo", repo, "--body", body],
                capture_output=True, text=True, timeout=30,
                encoding="utf-8", errors="replace",
            )
            if result.returncode == 0:
                return {"action": "commented", "issue_number": existing}
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
        return {"action": "failed", "issue_number": existing}

    title = f"Upstream drift: {family}/{platform} — {(finding.get('head') or 'unknown')[:10]}"
    try:
        result = runner(
            ["gh", "issue", "create", "--repo", repo, "--title", title, "--body", body,
             "--label", ISSUE_LABEL, "--label", _product_label(family, platform)],
            capture_output=True, text=True, timeout=30,
            encoding="utf-8", errors="replace",
        )
        if result.returncode == 0:
            # gh issue create prints the issue URL; extract the trailing number.
            url = result.stdout.strip()
            number = int(url.rsplit("/", 1)[-1]) if url.rsplit("/", 1)[-1].isdigit() else None
            return {"action": "created", "issue_number": number}
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return {"action": "failed", "issue_number": None}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: "list[str] | None" = None) -> int:
    parser = argparse.ArgumentParser(description="Check upstream FOSS repos for SHA drift")
    parser.add_argument("--file-issues", action="store_true",
                         help="Create/update deduped GitHub issues for HIGH/MEDIUM findings")
    parser.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY", "Aspose/aspose.org"))
    parser.add_argument("--run-url", default=None)
    args = parser.parse_args(argv)

    if not BASELINES_PATH.exists():
        print(f"ERROR: {BASELINES_PATH} not found", file=sys.stderr)
        return 2
    if not PRODUCTS_PATH.exists():
        print(f"ERROR: {PRODUCTS_PATH} not found", file=sys.stderr)
        return 2
    if not os.environ.get("GH_TOKEN") and not os.environ.get("GITHUB_TOKEN"):
        print("ERROR: GH_TOKEN or GITHUB_TOKEN required", file=sys.stderr)
        return 2

    # Pass subprocess.run explicitly (looked up here, at call time) rather than
    # relying on check_drift()'s own default parameter binding, which is captured
    # once at function-definition time and would not observe a test's
    # monkeypatch.setattr(module.subprocess, "run", fake) applied afterward.
    result = check_drift(runner=subprocess.run)
    findings = result["findings"]
    for f in findings:
        print(f"  {f['level']} {f['family']}/{f['platform']}: "
              f"{(f.get('stored') or 'none')[:12]} -> {(f.get('head') or 'unknown')[:12]} ({f['reason']})")
    print(f"\nSummary: {result['no_drift_count']} unchanged, {len(findings)} drift, "
          f"{result['error_count']} errors")

    high_medium = [f for f in findings if f["level"] in ("HIGH", "MEDIUM")]

    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    state = load_drift_state()
    flagged_keys = {f"{f['family']}/{f['platform']}" for f in high_medium}

    if args.file_issues and high_medium:
        print(f"\nFiling/updating issues for {len(high_medium)} product(s)...")
        for f in high_medium:
            outcome = file_or_update_issue(f, repo=args.repo, runner=subprocess.run, run_url=args.run_url)
            print(f"  {f['family']}/{f['platform']}: {outcome['action']} "
                  f"(#{outcome['issue_number']})" if outcome["issue_number"] else
                  f"  {f['family']}/{f['platform']}: {outcome['action']}")
            state = update_drift_state(state, f, checked_at=now, issue_number=outcome["issue_number"])
    elif high_medium:
        for f in high_medium:
            state = update_drift_state(state, f, checked_at=now, issue_number=None)

    # Reset consecutive_weeks_flagged for products no longer flagged this run.
    for key in list(state.keys()):
        if key not in flagged_keys and state[key].get("consecutive_weeks_flagged", 0) != 0:
            state[key]["consecutive_weeks_flagged"] = 0
            state[key]["checked_at"] = now
            state[key]["level"] = "NONE"

    save_drift_state(state)

    if high_medium:
        print(f"\nACTION REQUIRED: {len(high_medium)} product(s) have upstream changes")
        for f in high_medium:
            print(f"  - {f['family']}/{f['platform']}: {f['level']}")
        return 1

    print("\nAll baselines current.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
