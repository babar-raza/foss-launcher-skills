"""Repo patrol — discovery scan, change sweep, and combined reporting.

Subcommands:
    scan   Scan GitHub orgs, diff against registry, score confidence for new repos.
    sweep  Batch SHA comparison across all active launched products.
    report Generate a combined human-readable markdown report from latest scan+sweep.
    gate   Deterministic health gate over the latest patrol report; the required
           precondition for S-95 /discovery-triage (exit 0 ok / 1 degraded / 2 blocked).

Usage:
    python scripts/pipeline/commands/diagnostics/repo_patrol.py scan  [--apply] [--inactive-days N] [--force] [--orgs ORG,...]
    python scripts/pipeline/commands/diagnostics/repo_patrol.py sweep
    python scripts/pipeline/commands/diagnostics/repo_patrol.py report
    python scripts/pipeline/commands/diagnostics/repo_patrol.py gate [--json]

Default behaviour:
    scan:   dry-run — produces patrol_report.json only; --apply also writes to products.json.
    sweep:  read-only — fetches upstream clones, compares SHAs, writes sweep_report.json.
    report: read-only — reads latest reports and generates combined_report.md.

Exit codes (scan; ST-058 outcome contract):
    0  every org reached (scan_health.status == "ok")
    1  some orgs unreachable — report written and marked "degraded"
       (suppress with --allow-degraded)
    2  no org reached, or no credential — nothing written, last good report preserved

Environment:
    GH_TOKEN       GitHub classic PAT — preferred credential for scan.
    GITHUB_TOKEN   Fallback only. The aspose-*-foss orgs reject fine-grained PATs
                   with a lifetime over 366 days, so this variable 403s here (ST-058).
    ASPOSE_ORG     Comma-separated GitHub organisations (overrides default 26).

Output:
    reports/discovery/patrol_report.json
    reports/discovery/sweep_report.json
    reports/discovery/combined_report.md
    reports/discovery/discovery_verdict.yaml   (gate)
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
from typing import Callable

_PIPELINE_DIR = Path(__file__).resolve().parents[2]  # commands/diagnostics/ -> commands/ -> pipeline/
if str(_PIPELINE_DIR) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_DIR))
# FRESH-001 (2026-08-14): unconditional (not inside configure()) so bare imports of
# freshness_guard resolve even when configure() is never explicitly called, which is
# the normal production case -- module-level REPO_ROOT/etc. below are used directly.
_LIB_DIR = _PIPELINE_DIR / "lib"
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

from core.env_loader import load_env  # noqa: E402
load_env()

# ---------------------------------------------------------------------------
# Module-level paths (overridable via configure() for testing)
# ---------------------------------------------------------------------------
_DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[4]
REPO_ROOT = _DEFAULT_REPO_ROOT
DATA_DIR = REPO_ROOT / "data"
REGISTRY_PATH = DATA_DIR / "products.json"
UPSTREAM_BASELINES_PATH = DATA_DIR / "upstream_baselines.json"
KNOWLEDGE_ROOT = REPO_ROOT / "knowledge"
REPORTS_DIR = REPO_ROOT / "reports" / "discovery"
HISTORY_DIR = REPORTS_DIR / "history"


def configure(*, repo_root: "Path | str | None" = None) -> None:
    """Override module-level path constants for testing."""
    global REPO_ROOT, DATA_DIR, REGISTRY_PATH, UPSTREAM_BASELINES_PATH, KNOWLEDGE_ROOT, REPORTS_DIR, HISTORY_DIR
    REPO_ROOT = Path(repo_root) if repo_root is not None else _DEFAULT_REPO_ROOT
    DATA_DIR = REPO_ROOT / "data"
    REGISTRY_PATH = DATA_DIR / "products.json"
    UPSTREAM_BASELINES_PATH = DATA_DIR / "upstream_baselines.json"
    KNOWLEDGE_ROOT = REPO_ROOT / "knowledge"
    REPORTS_DIR = REPO_ROOT / "reports" / "discovery"
    HISTORY_DIR = REPORTS_DIR / "history"
    # FRESH-001 (2026-08-14): keep freshness_guard's module-level paths in lockstep
    # with this module's own configure() -- see batch_reference.py for the same
    # pattern/rationale. _get_stored_sha() below delegates to it. Imported as a bare
    # "freshness_guard" (matching batch_reference.py/refresh_run.py/launch_gate.py/
    # readiness_gate.py's import style) so all call sites share the SAME sys.modules
    # entry -- importing it as `lib.freshness_guard` instead would create a second,
    # independently-configured module object and silently break this propagation.
    #
    # IMPORTANT: the sys.path entry for lib/ must come from this FILE's own real
    # location (__file__), never from REPO_ROOT -- that is test-overridable to a
    # fake product-data root and does not point at the actual pipeline code
    # location, which is fixed regardless of what repo_root a test configures.
    try:
        real_lib_dir = str(_PIPELINE_DIR / "lib")  # _PIPELINE_DIR = scripts/pipeline/ (module-top constant)
        if real_lib_dir not in sys.path:
            sys.path.insert(0, real_lib_dir)
        import freshness_guard as _freshness_guard
        _freshness_guard.configure(repo_root=REPO_ROOT)
    except ImportError:
        pass


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_DEFAULT_INACTIVE_DAYS = 180

# Cap on a single rate-limit backoff, passed through to org_scanner. Keeps a
# throttled sweep bounded by (orgs x this) instead of by X-RateLimit-Reset.
_DEFAULT_MAX_RATE_WAIT = 300

# Exit codes (ST-058 outcome contract)
_EXIT_OK = 0
_EXIT_DEGRADED = 1
_EXIT_FAILED = 2


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
# Gate subcommand (MT021 TC-MT021-01) — deterministic discovery health gate
# ---------------------------------------------------------------------------
# Why this exists: ST-058 gave the PRODUCER a real failure contract (scan_health +
# exit codes + fail-closed writes), all enforced in code. The most consequential
# CONSUMER -- S-95 /discovery-triage, which turns the report into backlog items --
# was left enforcing that contract by reading a prose table in its skill doc. An
# agent that skips or misreads that table triages a degraded (incomplete) scan as
# complete, which is the same silent under-reporting ST-058 exists to eliminate,
# one layer downstream. This turns the consumer side into a real exit code too.
#
# Design mirrors S-112 triage-verdict-gate (skills/triage-verdict-gate.md):
# fully deterministic, no LLM, no network, read-only over a persisted artifact,
# idempotent, and it emits a verdict file alongside its exit code.
#
# It lives as a subcommand on this already-registered entrypoint rather than a new
# lib/ module because PIPELINE.md sets the extraction threshold at 3+ consumers and
# this has 2 (S-95, session-start); a new file would also trigger the New File
# Protocol. Tradeoff accepted knowingly: the producer hosts its own gate. It is
# mitigated because the gate reads only the persisted report (never in-memory scan
# state) and its behaviour is pinned by tests, including a negative control.

_GATE_OK = 0
_GATE_DEGRADED = 1
_GATE_BLOCKED = 2


def evaluate_gate(report: "dict | None") -> dict:
    """Return a verdict dict for *report* without touching the filesystem.

    Pure function so the decision logic is testable without I/O mocking.

    Absent ``scan_health`` is treated as UNKNOWN -> blocked, never as healthy: a
    report predating ST-058 cannot express whether its scan reached every org, and
    a partial scan of that era also has total_repos > 0, so nothing in the document
    can be used to infer health.
    """
    now = datetime.now(tz=timezone.utc).isoformat()

    if report is None:
        return {
            "verdict": "blocked", "exit_code": _GATE_BLOCKED, "status": "missing",
            "reason": "patrol_report.json is missing or unreadable — run /repo-patrol first.",
            "triage_allowed": False, "orgs_ok": 0, "orgs_requested": 0,
            "auth_mode": None, "failures": [], "report_generated_at": None,
            "verdict_at": now,
        }

    health = report.get("scan_health")
    if not isinstance(health, dict):
        return {
            "verdict": "blocked", "exit_code": _GATE_BLOCKED, "status": "unknown",
            "reason": ("report has no scan_health block (predates ST-058); its health is "
                       "UNKNOWN and it must not be triaged as complete — re-run /repo-patrol."),
            "triage_allowed": False, "orgs_ok": 0,
            "orgs_requested": len(report.get("orgs_scanned", [])),
            "auth_mode": None, "failures": [],
            "report_generated_at": report.get("generated_at"), "verdict_at": now,
        }

    status = health.get("status")
    failures = health.get("failures", []) or []
    common = {
        "status": status,
        "orgs_ok": health.get("orgs_ok", 0),
        "orgs_requested": health.get("orgs_requested", 0),
        "auth_mode": health.get("auth_mode"),
        "failures": failures,
        "report_generated_at": report.get("generated_at"),
        "verdict_at": now,
    }

    if status == "ok":
        return {**common, "verdict": "ok", "exit_code": _GATE_OK,
                "reason": "every org was reached; findings are complete.",
                "triage_allowed": True}

    if status == "degraded":
        missed = ", ".join(f.get("org", "?") for f in failures) or "unknown"
        return {**common, "verdict": "degraded", "exit_code": _GATE_DEGRADED,
                "reason": (f"{common['orgs_ok']}/{common['orgs_requested']} orgs reached; "
                           f"unreachable: {missed}. Findings are INCOMPLETE — every backlog "
                           f"row derived from this report must carry the degraded stamp, and "
                           f"absence of candidates must not be recorded as 'nothing new'."),
                "triage_allowed": True,
                "provenance_stamp": (f"discovery_health: degraded "
                                     f"({common['orgs_ok']}/{common['orgs_requested']} orgs, "
                                     f"missed: {missed})")}

    # status == "failed", or any unrecognised value -> fail closed.
    return {**common, "verdict": "blocked", "exit_code": _GATE_BLOCKED,
            "reason": (f"scan_health.status={status!r}; no usable discovery data. "
                       f"Do not create backlog rows from this report — fix the cause and "
                       f"re-run /repo-patrol."),
            "triage_allowed": False}


def _read_report_path(path: "Path") -> "dict | None":
    """Read an arbitrary report file, returning None when absent or unparseable."""
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def cmd_gate(*, as_json: bool = False, report_path: "str | Path | None" = None) -> int:
    """Deterministic gate over a patrol report. Returns the exit code.

    0 = ok (triage freely) | 1 = degraded (triage WITH provenance) | 2 = blocked.

    *report_path* evaluates an arbitrary report instead of the current one. This is
    what makes the "no archived report can be read as verified healthy" guarantee
    checkable rather than assumed (TC-MT021-08): every `history/` archive predating
    ST-058 lacks `scan_health` and must therefore gate as unknown -> blocked. The
    archives are gitignored local artifacts, so stamping them would only bind this
    one clone; enforcing it in the gate binds every clone.
    """
    if report_path is not None:
        source = Path(report_path)
        verdict = evaluate_gate(_read_report_path(source))
    else:
        source = REPORTS_DIR / "patrol_report.json"
        verdict = evaluate_gate(_read_report("patrol_report.json"))
    verdict["report_path"] = str(source)

    # Only the operative report produces the canonical verdict artifact. Inspecting an
    # archive with --report must NOT clobber the live verdict: that would let a
    # read-only inspection silently overwrite the state S-95 and session-start consume
    # -- the same class of quiet state corruption this whole mission exists to remove.
    out = None
    if report_path is None:
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        out = REPORTS_DIR / "discovery_verdict.yaml"
        try:
            import yaml  # type: ignore[import]
            out.write_text(yaml.safe_dump({"discovery_verdict": verdict}, sort_keys=False,
                                          allow_unicode=True), encoding="utf-8")
        except ImportError:  # pragma: no cover - yaml ships with the pipeline venv
            out.write_text(json.dumps({"discovery_verdict": verdict}, indent=2) + "\n",
                           encoding="utf-8")

    if as_json:
        print(json.dumps(verdict, indent=2, ensure_ascii=False))
    else:
        label = {0: "OK", 1: "DEGRADED", 2: "BLOCKED"}[verdict["exit_code"]]
        print(f"DISCOVERY GATE: {label} — {verdict['reason']}", file=sys.stderr)
        if verdict.get("provenance_stamp"):
            print(f"  stamp every derived row with: {verdict['provenance_stamp']}",
                  file=sys.stderr)
        if out is not None:
            print(f"  verdict written to {out.relative_to(REPO_ROOT)}", file=sys.stderr)
        else:
            print(f"  inspection of {source.name} — live verdict left untouched",
                  file=sys.stderr)

    return verdict["exit_code"]


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
# Scan health (ST-058 failure contract)
# ---------------------------------------------------------------------------

def _scan_health(orgs: list[str], outcomes: list[dict], auth_mode: str) -> dict:
    """Summarise per-org outcomes into the report's scan_health block.

    status is "ok" (every org reached), "degraded" (some reached), or "failed"
    (none reached). Consumers — S-95 discovery-triage and the session-start
    advisory — key off this rather than assuming an empty finding list means
    "nothing to find".
    """
    failures = [o for o in outcomes if o["status"] != "ok"]
    ok_count = len(outcomes) - len(failures)
    if not outcomes or ok_count == 0:
        status = "failed"
    elif failures:
        status = "degraded"
    else:
        status = "ok"
    return {
        "status": status,
        "orgs_requested": len(orgs),
        "orgs_ok": ok_count,
        "orgs_failed": len(failures),
        "auth_mode": auth_mode,
        "failures": failures,
    }


def _failed_scan_report(
    orgs: list[str],
    now: str,
    auth_mode: str,
    error: str,
    inactive_days: int,
    apply: bool,
    *,
    outcomes: list[dict] | None = None,
) -> dict:
    """Build a total-failure report WITHOUT persisting it.

    Deliberately does not call _write_report/_archive_report: overwriting
    patrol_report.json on a total outage would destroy the last trustworthy
    result AND reset the 7-day staleness clock the session-start advisory uses,
    silencing the only monitor that would prompt a re-run (ST-058).
    """
    if outcomes is None:
        outcomes = [{"org": o, "status": "auth_denied", "repo_count": 0, "detail": error}
                    for o in orgs]
    print("  Last good patrol_report.json left untouched (fail-closed).", file=sys.stderr)
    return {
        "generated_at": now,
        "orgs_scanned": orgs,
        "total_repos": 0,
        "registry_applied": False,
        "inactive_days_threshold": inactive_days,
        "new_candidates": [],
        "status_changes": [],
        "unclassifiable": [],
        "skipped_count": 0,
        "excluded_count": 0,
        "report_written": False,
        "scan_health": _scan_health(orgs, outcomes, auth_mode),
        "summary": {
            "new_candidates": 0, "status_changes": 0, "unclassifiable": 0,
            "skipped": 0, "excluded": 0,
        },
    }


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
    auth_mode: str = "unknown",
    max_rate_wait: int = _DEFAULT_MAX_RATE_WAIT,
) -> dict:
    """Scan GitHub orgs and produce a patrol report.

    Returns the patrol report dict, which always carries a ``scan_health`` block.

    Failure contract (ST-058): when EVERY org fails, the scan is a total failure —
    no report is written and no registry entry is applied, so the previous
    (trustworthy) report is preserved and keeps ageing. A partial failure writes
    a report marked ``degraded`` listing exactly which orgs were missed.
    """
    from lib.org_scanner import scan_orgs, preflight, TokenRejected
    from commands.ops.update_product_registry import _classify_repo, _DEFAULT_ORGS

    if orgs is None:
        env_orgs = os.environ.get("ASPOSE_ORG", "")
        orgs = [o.strip() for o in env_orgs.split(",") if o.strip()] if env_orgs else list(_DEFAULT_ORGS)

    registry = _load_registry()
    registry_index = {_key(e): e for e in registry}
    exclusions = _load_exclusions()

    now = datetime.now(tz=timezone.utc).isoformat()

    print(f"Scanning {len(orgs)} GitHub orgs (auth: {auth_mode})...", file=sys.stderr)

    # Validate the credential against a single org first: a rejected token then
    # costs one request instead of one per org.
    if orgs:
        try:
            preflight(orgs[0], token=token)
        except TokenRejected as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return _failed_scan_report(orgs, now, auth_mode, str(exc), inactive_days, apply)

    all_repos, outcomes = scan_orgs(orgs, token=token, max_rate_wait=max_rate_wait)

    failures = [o for o in outcomes if o["status"] != "ok"]
    for f in failures:
        print(f"  {f['status'].upper()} {f['org']}: {f['detail'][:160]}", file=sys.stderr)

    # Branch on the computed health, not on the failure count directly, so the
    # "no org was even attempted" case (empty --orgs) is also treated as a total
    # failure rather than writing a report labelled "failed".
    if _scan_health(orgs, outcomes, auth_mode)["status"] == "failed":
        print(f"ERROR: no org was successfully scanned ({len(failures)}/{len(outcomes)} "
              f"failed); scan produced no usable data.", file=sys.stderr)
        return _failed_scan_report(orgs, now, auth_mode, "", inactive_days, apply,
                                   outcomes=outcomes)

    print(f"  Found {len(all_repos)} total repos "
          f"({len(outcomes) - len(failures)}/{len(outcomes)} orgs ok)", file=sys.stderr)

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
        "scan_health": _scan_health(orgs, outcomes, auth_mode),
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

    if report["scan_health"]["status"] == "degraded":
        print(f"  WARNING: scan DEGRADED — {len(failures)} of {len(outcomes)} orgs "
              f"unreachable; findings are incomplete.", file=sys.stderr)

    if apply:
        sorted_reg = sorted(registry, key=lambda e: (e["family"], e["platform"]))
        _save_registry(sorted_reg)
        print(f"  Registry updated: {len(new_candidates)} new entries added", file=sys.stderr)

    print(f"  Patrol report: {report['summary']}", file=sys.stderr)
    return report


# ---------------------------------------------------------------------------
# Sweep subcommand
# ---------------------------------------------------------------------------

def cmd_sweep(
    *,
    clone_exists_fn: "Callable[[str, str], bool] | None" = None,
    ensure_clone_fn: "Callable[[str, str], Path] | None" = None,
    update_clone_fn: "Callable[[str, str], str | None] | None" = None,
    clone_head_sha_fn: "Callable[[str, str], str | None] | None" = None,
) -> dict:
    """Batch SHA comparison across all active launched products.

    MT069-2026-09-16-GHA-MINUTES-REARCHITECTURE (2026-09-18): the pre-existing
    "no local clone exists" fetch_failure was misdiagnosed for months as a
    GitHub-token/PAT permission problem (issue #94, ST-058) -- upstream-
    monitor.yml's own comment claimed the ephemeral Actions token "403s
    against the aspose-*-foss orgs". Direct code read + a live repro
    (`clone_exists()` in a genuinely empty cache dir, matching a fresh CI
    checkout, returns False unconditionally -- confirmed live) shows this
    step never even reaches a network call: clone_exists() is a pure
    filesystem check against runs/.clone_cache/, which is gitignored and
    therefore never present on any fresh checkout, so every one of these 33
    products failed with "no local clone exists" before any git/API call was
    attempted, regardless of any token's validity. This now calls
    ensure_clone() first (already existed for exactly this purpose --
    auto-clones a PLAIN, UNAUTHENTICATED `git clone` from the public FOSS
    mirror URL in data/products.json, confirmed live that these are public
    repos, needing no token at all) so a cold/missing cache self-heals
    instead of failing outright. No behavior change when a clone already
    exists (ensure_clone() no-ops in that case) -- purely additive.

    The four `*_fn` parameters are DI seams (AGENTS.md 16 -- prefer explicit
    injection over monkeypatching core.clone_cache internals); each defaults
    to the real core.clone_cache function when not overridden by a caller.
    """
    from core.clone_cache import clone_exists, clone_head_sha, ensure_clone, update_clone

    clone_exists_fn = clone_exists_fn or clone_exists
    ensure_clone_fn = ensure_clone_fn or ensure_clone
    update_clone_fn = update_clone_fn or update_clone
    clone_head_sha_fn = clone_head_sha_fn or clone_head_sha

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

        if not clone_exists_fn(family, platform):
            try:
                ensure_clone_fn(family, platform)
            except RuntimeError as exc:
                fetch_failures.append({
                    "family": family,
                    "platform": platform,
                    "error": f"no local clone exists and auto-clone failed: {exc}",
                })
                continue

        stored_sha = _get_stored_sha(family, platform)

        new_sha = update_clone_fn(family, platform)
        if new_sha is None:
            new_sha = clone_head_sha_fn(family, platform)
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
    """Resolve the stored baseline SHA for a product.

    FRESH-001 (2026-08-14): delegates to freshness_guard.resolve_baseline() --
    behavior-preserving refactor of the resolution LOGIC (still tries the same
    sources, in an order that is now intentionally different, see below), not a
    new source of truth. Previously this function duplicated its own ad hoc
    2-source priority (data/upstream_baselines.json first, model.yaml scalar
    fallback -- the MT030-2026-08-13 fix for pdf/java's frozen-baseline
    incident). Now that merged/model.yaml is git-tracked (T0/T2), it is the
    canonical writer and is checked FIRST; upstream_baselines.json and
    knowledge_state.json are regenerated projections consulted as fallback (see
    freshness_guard.py's module docstring for the full collapsed-resolution
    rationale). This is an intentional priority flip, not a regression: the
    MT030 fix made upstream_baselines.json take priority specifically because
    model.yaml was NOT durable at the time; now that it is, the durability
    argument for preferring the projection over the source no longer applies.
    """
    sha, _source = _resolve_stored_sha_via_freshness_guard(family, platform)
    return sha


def _resolve_stored_sha_via_freshness_guard(family: str, platform: str) -> tuple[str | None, str]:
    try:
        from freshness_guard import resolve_baseline
        return resolve_baseline(family, platform)
    except ImportError:
        pass

    # Fallback if freshness_guard is unimportable for some reason (should not
    # happen in a correctly configured checkout) -- preserves old behavior
    # rather than returning None outright.
    try:
        baselines = json.loads(UPSTREAM_BASELINES_PATH.read_text(encoding="utf-8"))
        val = baselines.get(f"{family}/{platform}")
        if val:
            return val, "upstream_baselines.json"
    except (OSError, json.JSONDecodeError):
        pass
    model_path = KNOWLEDGE_ROOT / family / platform / "merged" / "model.yaml"
    if not model_path.is_file():
        return None, "none"
    try:
        text = model_path.read_text(encoding="utf-8")
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("repo_sha:"):
                val = stripped.split(":", 1)[1].strip().strip("'\"")
                return (val, "model.yaml") if val else (None, "none")
        return None, "none"
    except OSError:
        return None, "none"


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

        health = patrol.get("scan_health")
        if health:
            status = health.get("status", "unknown")
            marker = {"ok": "OK", "degraded": "**DEGRADED**", "failed": "**FAILED**"}.get(
                status, status)
            lines.append(
                f"- **Scan health**: {marker} — {health.get('orgs_ok', 0)}/"
                f"{health.get('orgs_requested', 0)} orgs reached "
                f"(auth: {health.get('auth_mode', 'unknown')})"
            )
            if status != "ok":
                lines.append("")
                lines.append("> Findings below are INCOMPLETE — orgs listed under "
                             "Scan Failures were never reached. Do not read an empty "
                             "candidate list as \"nothing new exists\".")
        else:
            lines.append("- **Scan health**: not recorded (report predates ST-058)")
        lines.append("")

        if health and health.get("failures"):
            lines.append("### Scan Failures")
            lines.append("")
            lines.append("| Org | Status | Detail |")
            lines.append("|-----|--------|--------|")
            for f in health["failures"]:
                detail = str(f.get("detail", "")).replace("|", "\\|")[:160]
                lines.append(f"| {f.get('org', '')} | {f.get('status', '')} | {detail} |")
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
                        help="GitHub token (falls back to GH_TOKEN, then GITHUB_TOKEN)")
    p_scan.add_argument("--no-auth", action="store_true",
                        help="Scan unauthenticated (public API, 60 req/hr). Explicit "
                             "degraded mode — never used as an automatic fallback.")
    p_scan.add_argument("--allow-degraded", action="store_true",
                        help="Exit 0 even when some orgs were unreachable (for scripted use)")
    p_scan.add_argument("--max-rate-wait", type=int, default=_DEFAULT_MAX_RATE_WAIT,
                        help=f"Cap in seconds on a single rate-limit backoff "
                             f"(default: {_DEFAULT_MAX_RATE_WAIT})")

    sub.add_parser("sweep", help="Batch SHA comparison across active launched products")

    sub.add_parser("report", help="Generate combined markdown report")

    p_gate = sub.add_parser(
        "gate",
        help="Deterministic health gate over the latest patrol report "
             "(exit 0 ok / 1 degraded / 2 blocked). Required before S-95 triage.")
    p_gate.add_argument("--json", action="store_true", dest="as_json",
                        help="Emit the verdict as JSON on stdout")
    p_gate.add_argument("--report", dest="report_path", default=None,
                        help="Evaluate an arbitrary report file (e.g. a history/ archive) "
                             "instead of the current patrol_report.json")

    args = parser.parse_args(argv)

    if args.command == "scan":
        from lib.org_scanner import resolve_token

        orgs = [o.strip() for o in args.orgs.split(",") if o.strip()] if args.orgs else None
        if args.no_auth:
            token, auth_mode = None, "unauthenticated"
        else:
            token, auth_mode = resolve_token(args.token)
            if token is None:
                print("ERROR: no GitHub credential found. Set GH_TOKEN (classic PAT), "
                      "pass --token, or use --no-auth for the 60 req/hr public API.",
                      file=sys.stderr)
                return _EXIT_FAILED
        report = cmd_scan(
            orgs=orgs,
            token=token,
            apply=args.apply,
            inactive_days=args.inactive_days,
            force=args.force,
            auth_mode=auth_mode,
            max_rate_wait=args.max_rate_wait,
        )
        status = report.get("scan_health", {}).get("status", "ok")
        if status == "failed":
            return _EXIT_FAILED
        if status == "degraded" and not args.allow_degraded:
            return _EXIT_DEGRADED
        return _EXIT_OK
    elif args.command == "sweep":
        cmd_sweep()
    elif args.command == "report":
        cmd_report()
    elif args.command == "gate":
        return cmd_gate(as_json=args.as_json, report_path=args.report_path)

    return _EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
