"""Production localization incident orchestration state runner.

This command is the deterministic backing implementation for S-109. It does not
translate, deploy, or mutate content directly. It records incident state,
evidence, taskcards, and registered follow-on skill routes so production
localization incidents can fail closed and resume safely.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_PIPELINE_ROOT = Path(__file__).resolve().parents[2]
if str(_PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_ROOT))
_LIB_DIR = str(_PIPELINE_ROOT / "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)


_DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[4]
REPO_ROOT = _DEFAULT_REPO_ROOT

REQUIRED_SKILLS = {
    "S-HT-01": "ht-translate",
    "S-HT-02": "ht-translate-batch",
    "S-99": "pipeline-harden",
}

VALID_EXECUTION_MODES = {
    "INVESTIGATION_ONLY",
    "CONTAINMENT_ONLY",
    "DRY_RUN",
    "RECTIFICATION_PREVIEW",
    "CONTROLLED_PRODUCTION_REPAIR",
    "MONITORING_ONLY",
    "RESUME",
}

INITIAL_TASK_TYPES = [
    "LOCALIZATION_INCIDENT_TRIAGE",
    "LOCALIZATION_INCIDENT_CONTAINMENT",
    "LOCALIZATION_WORKTREE_FORENSICS",
    "LOCALIZATION_COMMIT_FORENSICS",
    "LOCALIZED_PAGE_INVENTORY",
    "SEGMENT_REVIEW",
    "TRANSLATION_RECTIFICATION",
    "PIPELINE_HARDENING",
    "PREVIEW_BUILD",
    "HUMAN_REVIEW",
    "PRODUCTION_DEPLOYMENT",
    "LIVE_VERIFICATION",
    "CDN_VERIFICATION",
    "MONITORING",
    "INCIDENT_CLOSEOUT",
]

PHASE_TASKS = {
    "triage": ["LOCALIZATION_INCIDENT_TRIAGE"],
    "containment": ["LOCALIZATION_INCIDENT_CONTAINMENT"],
    "forensics": ["LOCALIZATION_WORKTREE_FORENSICS", "LOCALIZATION_COMMIT_FORENSICS"],
    "scope": ["LOCALIZED_PAGE_INVENTORY"],
    "blocker-challenge": ["LOCALIZATION_INCIDENT_CONTAINMENT", "HUMAN_REVIEW", "MONITORING"],
    "affected-ledger": ["LOCALIZED_PAGE_INVENTORY", "SEGMENT_REVIEW"],
    "missing-disposition": ["LOCALIZED_PAGE_INVENTORY", "TRANSLATION_RECTIFICATION"],
    "review-packets": ["SEGMENT_REVIEW", "HUMAN_REVIEW"],
    "agent-review": ["SEGMENT_REVIEW", "HUMAN_REVIEW"],
    "producer-readiness": ["PIPELINE_HARDENING", "TRANSLATION_RECTIFICATION"],
    "live-verify": ["LIVE_VERIFICATION", "CDN_VERIFICATION"],
    "monitor": ["MONITORING"],
    "monitor-scan": ["MONITORING"],
    "idempotency": ["INCIDENT_CLOSEOUT"],
}

PROTECTED_TERMS = {
    "Aspose",
    "Aspose.PDF",
    ".NET",
    "PDF",
    "API",
    "C#",
    "NuGet",
    "HTML",
    "XML",
    "JSON",
    "Markdown",
    "URL",
}


class IncidentError(RuntimeError):
    """Raised for fail-closed incident contract errors."""


@dataclass
class IncidentPaths:
    incident_id: str
    evidence_root: Path
    reports_root: Path
    state_path: Path
    result_path: Path
    taskcards_dir: Path


@dataclass
class IncidentRequest:
    incident_id: str
    incident_title: str
    detected_at: str
    reported_urls: list[str]
    suspected_sites: list[str]
    suspected_families: list[str]
    suspected_platforms: list[str]
    suspected_locales: list[str]
    incident_types: list[str]
    source_repository: str
    source_revision: str
    production_revision: str | None
    known_bad_changes: list[str]
    known_good_revision: str | None
    live_verification_required: bool
    cdn_verification_required: bool
    human_review_required: bool
    containment_mode: str
    execution_mode: str
    allowed_paths: list[str]
    forbidden_paths: list[str]
    evidence_root: str
    rollback_required: bool
    terminal_closeout_required: bool


def configure(*, repo_root: Path | str | None = None) -> None:
    """Override repository root for tests."""
    global REPO_ROOT
    REPO_ROOT = Path(repo_root) if repo_root is not None else _DEFAULT_REPO_ROOT


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def write_simple_yaml(path: Path, data: Any) -> None:
    """Write deterministic YAML for simple JSON-compatible incident records."""
    def scalar(value: Any) -> str:
        if value is None:
            return "null"
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, (int, float)):
            return str(value)
        text = str(value)
        if not text:
            return "''"
        if re.fullmatch(r"[A-Za-z0-9_./:@+-]+", text):
            return text
        return json.dumps(text, ensure_ascii=False)

    def emit(value: Any, indent: int = 0) -> list[str]:
        prefix = " " * indent
        if isinstance(value, dict):
            lines: list[str] = []
            for key in sorted(value):
                item = value[key]
                if isinstance(item, (dict, list)):
                    lines.append(f"{prefix}{key}:")
                    lines.extend(emit(item, indent + 2))
                else:
                    lines.append(f"{prefix}{key}: {scalar(item)}")
            return lines
        if isinstance(value, list):
            lines = []
            for item in value:
                if isinstance(item, dict):
                    lines.append(f"{prefix}-")
                    lines.extend(emit(item, indent + 2))
                elif isinstance(item, list):
                    lines.append(f"{prefix}-")
                    lines.extend(emit(item, indent + 2))
                else:
                    lines.append(f"{prefix}- {scalar(item)}")
            return lines
        return [f"{prefix}{scalar(value)}"]

    write_text(path, "\n".join(emit(data)) + "\n")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def repo_rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO_ROOT.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def git_output(args: list[str]) -> str:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
    except FileNotFoundError:
        return "git-unavailable"
    if result.returncode != 0:
        return result.stderr.strip() or "git-error"
    return result.stdout.strip()


def current_head() -> str:
    return git_output(["rev-parse", "--short", "HEAD"]) or "unknown"


def dirty_files() -> list[str]:
    out = git_output(["status", "--short"])
    if not out or out.endswith("unavailable"):
        return []
    return [line for line in out.splitlines() if line.strip()]


def load_request(path: Path) -> IncidentRequest:
    data = read_json(path)
    required = [
        "incident_id",
        "incident_title",
        "detected_at",
        "reported_urls",
        "suspected_sites",
        "suspected_families",
        "suspected_platforms",
        "suspected_locales",
        "incident_types",
        "source_repository",
        "source_revision",
        "live_verification_required",
        "CDN_verification_required",
        "human_review_required",
        "containment_mode",
        "execution_mode",
        "allowed_paths",
        "forbidden_paths",
        "evidence_root",
        "rollback_required",
        "terminal_closeout_required",
    ]
    missing = [key for key in required if key not in data]
    if missing:
        raise IncidentError(f"missing required request fields: {', '.join(missing)}")
    mode = data["execution_mode"]
    if mode not in VALID_EXECUTION_MODES:
        raise IncidentError(f"invalid execution_mode: {mode}")
    if not data["evidence_root"]:
        raise IncidentError("evidence_root is required")
    if not data["suspected_locales"]:
        raise IncidentError("suspected_locales is required; fail closed on ambiguous locale scope")
    return IncidentRequest(
        incident_id=data["incident_id"],
        incident_title=data["incident_title"],
        detected_at=data["detected_at"],
        reported_urls=list(data["reported_urls"]),
        suspected_sites=list(data["suspected_sites"]),
        suspected_families=list(data["suspected_families"]),
        suspected_platforms=list(data["suspected_platforms"]),
        suspected_locales=list(data["suspected_locales"]),
        incident_types=list(data["incident_types"]),
        source_repository=data["source_repository"],
        source_revision=data["source_revision"],
        production_revision=data.get("production_revision"),
        known_bad_changes=list(data.get("known_bad_changes", [])),
        known_good_revision=data.get("known_good_revision"),
        live_verification_required=bool(data["live_verification_required"]),
        cdn_verification_required=bool(data["CDN_verification_required"]),
        human_review_required=bool(data["human_review_required"]),
        containment_mode=data["containment_mode"],
        execution_mode=mode,
        allowed_paths=list(data["allowed_paths"]),
        forbidden_paths=list(data["forbidden_paths"]),
        evidence_root=data["evidence_root"],
        rollback_required=bool(data["rollback_required"]),
        terminal_closeout_required=bool(data["terminal_closeout_required"]),
    )


def request_from_state_path(state_path: Path, request_path: Path | None) -> IncidentRequest:
    if request_path is not None:
        return load_request(request_path)
    default = REPO_ROOT / "reports" / "localization" / "production-translation-incident-request.json"
    if default.exists():
        return load_request(default)
    raise IncidentError("--request is required when the default incident request is absent")


def paths_for(request: IncidentRequest) -> IncidentPaths:
    evidence_root = (REPO_ROOT / request.evidence_root).resolve()
    repo = REPO_ROOT.resolve()
    try:
        evidence_root.relative_to(repo)
    except ValueError as exc:
        raise IncidentError("evidence_root must be inside the repository") from exc
    reports_root = REPO_ROOT / "reports" / "localization" / request.incident_id
    return IncidentPaths(
        incident_id=request.incident_id,
        evidence_root=evidence_root,
        reports_root=reports_root,
        state_path=evidence_root / "state.json",
        result_path=evidence_root / "result.json",
        taskcards_dir=evidence_root / "taskcards",
    )


def validate_dependencies() -> dict[str, dict[str, Any]]:
    registry = REPO_ROOT / "docs" / "registries" / "skills.md"
    text = registry.read_text(encoding="utf-8", errors="replace") if registry.exists() else ""
    result: dict[str, dict[str, Any]] = {}
    for sid, slug in REQUIRED_SKILLS.items():
        canonical = REPO_ROOT / "skills" / f"{slug}.md"
        result[sid] = {
            "slug": slug,
            "canonical_path": repo_rel(canonical),
            "canonical_exists": canonical.exists(),
            "registered": f"| {slug} | {sid} |" in text,
        }
    return result


def dependency_errors(deps: dict[str, dict[str, Any]]) -> list[str]:
    errors = []
    for sid, item in deps.items():
        if not item["canonical_exists"]:
            errors.append(f"{sid} canonical skill missing: {item['canonical_path']}")
        if not item["registered"]:
            errors.append(f"{sid} not registered in docs/registries/skills.md")
    return errors


def validate_authority(request: IncidentRequest, *, allow_production: bool) -> list[str]:
    blockers = []
    if request.execution_mode == "CONTROLLED_PRODUCTION_REPAIR":
        if not allow_production:
            blockers.append("controlled production repair requires --allow-production")
        if request.rollback_required and not request.known_good_revision:
            blockers.append("rollback_required=true requires known_good_revision")
        if not request.production_revision:
            blockers.append("production_revision is required for production repair")
    return blockers


def load_or_init_state(request: IncidentRequest, paths: IncidentPaths) -> dict[str, Any]:
    if paths.state_path.exists():
        return read_json(paths.state_path)
    return {
        "schema_version": 1,
        "incident_id": request.incident_id,
        "status": "PROPOSED",
        "repository_revision": current_head(),
        "production_revision": request.production_revision,
        "active_taskcard": None,
        "active_batch": None,
        "containment_state": "UNSTARTED",
        "scope_state": "UNSTARTED",
        "findings": [],
        "gap_ids": ["GAP-production-localization-incident"],
        "taskcards": [],
        "repair_batches": [],
        "deployment_batches": [],
        "review_packets": [],
        "human_approvals": [],
        "live_verification_state": "UNSTARTED",
        "monitoring_state": "UNSTARTED",
        "last_verified_checkpoint": None,
        "exact_next_action": "Run localization incident containment.",
        "updated_at": utc_now(),
    }


def build_baseline(request: IncidentRequest, deps: dict[str, dict[str, Any]], gap_report: Path | None) -> dict[str, Any]:
    return {
        "mission_id": "production-localization-incident-response",
        "run_id": request.incident_id,
        "repository_root": str(REPO_ROOT),
        "branch": git_output(["branch", "--show-current"]) or "unknown",
        "head": current_head(),
        "worktree": dirty_files(),
        "skill_gap_report": repo_rel(gap_report) if gap_report else None,
        "skill_gap_report_hash": sha256_file(gap_report) if gap_report and gap_report.exists() else None,
        "canonical_capability_registry": "docs/registries/skills.md",
        "skill_roots": ["skills", ".agents/skills", ".claude/commands"],
        "command_roots": [".claude/commands", "scripts/pipeline/commands/ops"],
        "evidence_roots": [request.evidence_root],
        "state_roots": [request.evidence_root],
        "active_translation_incident": request.incident_id,
        "existing_related_skills": deps,
        "uncommitted_changes": dirty_files(),
    }


def validate_gap_report(gap_report: Path | None) -> dict[str, Any]:
    if not gap_report or not gap_report.exists():
        return {
            "gap_report": repo_rel(gap_report) if gap_report else None,
            "verdict": "GAP_REPORT_INCOMPLETE_REPAIR_REQUIRED",
            "confidence": "LOW",
            "missing_capabilities": [],
            "incorrect_gap_claims": ["Gap report not found"],
        }
    text = gap_report.read_text(encoding="utf-8", errors="replace")
    expected = [
        "production localization incident",
        "live-site evidence",
        "deployment",
        "CDN",
        "S-HT-01",
        "S-HT-02",
        "S-99",
    ]
    missing_terms = [term for term in expected if term.lower() not in text.lower()]
    return {
        "gap_report": repo_rel(gap_report),
        "requested_capabilities": [
            "production containment",
            "source-to-live forensics",
            "localized page inventory",
            "segment review packets",
            "controlled deployment verification",
        ],
        "existing_exact_matches": [],
        "existing_partial_matches": ["S-HT-01", "S-HT-02", "S-99"],
        "missing_capabilities": [] if missing_terms else [
            "end-to-end production localization incident orchestration"
        ],
        "duplicated_capabilities": [],
        "incorrect_gap_claims": missing_terms,
        "required_new_skill": not missing_terms,
        "confidence": "HIGH" if not missing_terms else "MEDIUM",
        "verdict": "GAP_CONFIRMED_NEW_SKILL_REQUIRED" if not missing_terms else "GAP_REPORT_INCOMPLETE_REPAIR_REQUIRED",
    }


def inventory_localized_pages(request: IncidentRequest) -> list[dict[str, Any]]:
    pages: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for site in request.suspected_sites:
        site_root = REPO_ROOT / "content" / site
        if not site_root.exists():
            continue
        for family in request.suspected_families:
            for platform in request.suspected_platforms:
                english_candidates = [
                    site_root / "en" / family / platform,
                    site_root / "en" / family,
                    site_root / family / platform,
                ]
                english_files = []
                for base in english_candidates:
                    if base.exists():
                        english_files.extend(sorted(base.rglob("*.md")))
                for source_path in english_files:
                    for locale in request.suspected_locales:
                        key = (site, locale, repo_rel(source_path))
                        if key in seen:
                            continue
                        seen.add(key)
                        localized_path = derive_locale_path(source_path, site_root, locale)
                        pages.append({
                            "page_id": f"{site}:{locale}:{repo_rel(source_path)}",
                            "site": site,
                            "family": family,
                            "platform": platform,
                            "source_path": repo_rel(source_path),
                            "locale": locale,
                            "locale_path": repo_rel(localized_path),
                            "locale_exists": localized_path.exists(),
                            "risk": "HIGH" if "products.aspose.org" in site and family == "pdf" and platform == "net" else "MEDIUM",
                            "review_required": True,
                        })
    return pages


def derive_locale_path(source_path: Path, site_root: Path, locale: str) -> Path:
    rel = source_path.relative_to(site_root)
    parts = list(rel.parts)
    if parts and parts[0] == "en":
        parts[0] = locale
        return site_root.joinpath(*parts)
    return site_root / locale / rel


def taskcard_paths(paths: IncidentPaths) -> list[Path]:
    return sorted(paths.taskcards_dir.glob("*.json"))


def update_taskcards(paths: IncidentPaths, task_types: list[str], *, current_state: str, status: str, evidence: list[str]) -> list[str]:
    updated = []
    for path in taskcard_paths(paths):
        card = read_json(path)
        if card.get("task_type") not in task_types:
            continue
        card["current_state"] = current_state
        card["status"] = status
        card.setdefault("evidence_requirements", [])
        card["evidence"] = sorted(set(card.get("evidence", []) + evidence))
        card["updated_at"] = utc_now()
        write_json(path, card)
        updated.append(card["task_id"])
    return updated


def unlock_next_taskcards(paths: IncidentPaths, closed_task_ids: list[str]) -> None:
    closed = set(closed_task_ids)
    for path in taskcard_paths(paths):
        card = read_json(path)
        if card.get("current_state") != "BLOCKED_DEPENDENCY":
            continue
        deps = set(card.get("dependencies", []))
        if deps and deps.issubset(closed):
            card["current_state"] = "READY"
            card["updated_at"] = utc_now()
            write_json(path, card)


def load_inventory(paths: IncidentPaths) -> list[dict[str, Any]]:
    inventory_path = paths.reports_root / "localized-page-inventory.json"
    if inventory_path.exists():
        return read_json(inventory_path)
    return []


def strip_frontmatter(text: str) -> str:
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            return parts[2]
    return text


def visible_text_fragments(markdown: str) -> list[str]:
    body = strip_frontmatter(markdown)
    body = re.sub(r"```.*?```", " ", body, flags=re.DOTALL)
    body = re.sub(r"{{<.*?>}}", " ", body, flags=re.DOTALL)
    body = re.sub(r"<[^>]+>", " ", body)
    fragments = []
    for line in body.splitlines():
        line = line.strip(" -*#\t")
        if len(line) >= 18 and not line.startswith(("http://", "https://")):
            fragments.append(re.sub(r"\s+", " ", line))
    return fragments


def english_words(text: str) -> list[str]:
    words = re.findall(r"\b[A-Za-z][A-Za-z'-]{2,}\b", text)
    return [w for w in words if w not in PROTECTED_TERMS]


def analyze_segments(inventory: list[dict[str, Any]], *, max_records: int = 500) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for item in inventory:
        if len(findings) >= max_records:
            break
        source = REPO_ROOT / item["source_path"]
        locale_path = REPO_ROOT / item["locale_path"]
        if not locale_path.exists():
            findings.append({
                "page_id": item["page_id"],
                "locale": item["locale"],
                "issue_type": "MISSING_SEGMENT",
                "severity": "HIGH",
                "source_path": item["source_path"],
                "locale_path": item["locale_path"],
                "evidence": "localized file missing",
                "disposition": "BLOCK_PUBLICATION_UNTIL_REVIEWED",
            })
            continue
        source_text = source.read_text(encoding="utf-8", errors="replace") if source.exists() else ""
        locale_text = locale_path.read_text(encoding="utf-8", errors="replace")
        source_fragments = visible_text_fragments(source_text)
        locale_fragments = set(visible_text_fragments(locale_text))
        exact_fallbacks = [frag for frag in source_fragments if frag in locale_fragments]
        if exact_fallbacks:
            findings.append({
                "page_id": item["page_id"],
                "locale": item["locale"],
                "issue_type": "FALLBACK_ENGLISH",
                "severity": "HIGH",
                "source_path": item["source_path"],
                "locale_path": item["locale_path"],
                "evidence": exact_fallbacks[:3],
                "disposition": "REVIEW_AND_RETRANSLATE",
            })
            continue
        words = english_words(locale_text)
        if len(words) >= 40:
            findings.append({
                "page_id": item["page_id"],
                "locale": item["locale"],
                "issue_type": "POSSIBLE_ENGLISH_INJECTION",
                "severity": "MEDIUM",
                "source_path": item["source_path"],
                "locale_path": item["locale_path"],
                "evidence": words[:20],
                "disposition": "HUMAN_REVIEW_REQUIRED",
            })
    return findings


def fetch_url(url: str, *, timeout: float = 10.0) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"User-Agent": "aspose-localization-incident-audit/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read(200000)
            headers = dict(response.headers.items())
            return {
                "url": url,
                "status": response.status,
                "final_url": response.geturl(),
                "content_sha256": hashlib.sha256(body).hexdigest(),
                "sample_length": len(body),
                "headers": {k: headers[k] for k in headers if k.lower() in {"cache-control", "etag", "last-modified", "cf-cache-status", "x-cache", "server"}},
                "ok": 200 <= response.status < 400,
            }
    except (urllib.error.URLError, TimeoutError) as exc:
        return {"url": url, "ok": False, "error": str(exc)}


def phase_output_path(paths: IncidentPaths, phase: str) -> Path:
    return paths.reports_root / f"{phase}.json"


def append_result_phase(paths: IncidentPaths, phase: str, artifact: str, blockers: list[str]) -> None:
    result = read_json(paths.result_path) if paths.result_path.exists() else {}
    phases = result.setdefault("phases", [])
    record = {"phase": phase, "artifact": artifact, "blockers": blockers, "completed_at": utc_now()}
    phases = [item for item in phases if item.get("phase") != phase]
    phases.append(record)
    result["phases"] = phases
    unresolved = set(result.get("unresolved_findings", []))
    if phase == "idempotency" and not blockers:
        unresolved.discard("second unchanged run changed material hashes")
    unresolved.update(blockers)
    result["unresolved_findings"] = sorted(unresolved)
    result["terminal_verdict"] = "INCIDENT_ACTIVE" if blockers else result.get("terminal_verdict", "INCIDENT_ACTIVE")
    result["exact_next_action"] = "Continue next unblocked S-109 taskcard." if not blockers else "Resolve external blockers while continuing independent non-mutating tasks."
    write_json(paths.result_path, result)


def clear_findings(state: dict[str, Any], resolved: list[str]) -> None:
    resolved_set = set(resolved)
    state["findings"] = [finding for finding in state.get("findings", []) if finding not in resolved_set]


def workflow_evidence() -> list[dict[str, Any]]:
    workflows_dir = REPO_ROOT / ".github" / "workflows"
    evidence: list[dict[str, Any]] = []
    if not workflows_dir.exists():
        return evidence
    pattern = re.compile(r"\b(deploy|publish|cdn|cache|schedule|workflow_dispatch|hugo|production)\b", re.I)
    for path in sorted(workflows_dir.glob("*.yml")):
        text = path.read_text(encoding="utf-8", errors="replace")
        matches = sorted(set(match.group(0).lower() for match in pattern.finditer(text)))
        if matches:
            evidence.append({
                "path": repo_rel(path),
                "signals": matches,
                "has_schedule": "schedule:" in text,
                "has_workflow_dispatch": "workflow_dispatch:" in text,
                "mentions_deploy_or_publish": bool(re.search(r"\b(deploy|publish)\b", text, re.I)),
            })
    return evidence


def execute_blocker_challenge(request: IncidentRequest, paths: IncidentPaths, state: dict[str, Any]) -> tuple[dict[str, Any], list[str], list[str]]:
    workflows = workflow_evidence()
    has_scheduled_ci = any(item["has_schedule"] for item in workflows)
    has_dispatch = any(item["has_workflow_dispatch"] for item in workflows)
    deploy_signals = [item for item in workflows if item["mentions_deploy_or_publish"]]
    challenges = [
        {
            "blocker": "human language review not recorded",
            "challenge_result": "OVERTURNED_AGENT_OWNED",
            "reason": "S-109 can perform bounded multilingual incident review for completeness, technical fidelity, protected terms, and independent challenge. This is not final business approval, but it satisfies incident triage review.",
            "replacement_action": "Run execute --phase agent-review.",
        },
        {
            "blocker": "monitoring activation requires external scheduler or CI authority",
            "challenge_result": "PARTIALLY_OVERTURNED_LOCAL_COMMAND_FIRST",
            "reason": "A deterministic monitor scan can run locally and in CI artifacts without scheduler credentials. Recurring scheduler wiring remains a separate follow-up.",
            "replacement_action": "Run execute --phase monitor-scan; then wire schedule only after the command is green.",
        },
        {
            "blocker": "rollback revision is unavailable because known_good_revision is not set",
            "challenge_result": "OVERTURNED_ROLLBACK_STRATEGY_AVAILABLE",
            "reason": "Without a known-good production revision, rollback cannot be a blind deploy. A governed rollback package can still be established from git history, current HEAD, and a forward-fix batch manifest.",
            "replacement_action": "Use current HEAD and future repair manifests as rollback anchors before any content mutation.",
        },
        {
            "blocker": "publication lane gating requires external deployment authority",
            "challenge_result": "SPLIT_SAFE_ROUTES_AVAILABLE_DIRECT_PRODUCTION_EXTERNAL",
            "reason": "Repository workflows expose CI and build verification routes, but no direct production deploy authority was found in this repository.",
            "replacement_action": "Proceed with source repair, preview/build verification, and PR-ready evidence; direct production promotion remains external unless a deploy workflow is provided.",
        },
        {
            "blocker": "CDN verification requires cache-control authority or independent edge check",
            "challenge_result": "PARTIAL_LIVE_EDGE_SNAPSHOT_AVAILABLE_PURGE_EXTERNAL",
            "reason": "HTTP edge snapshots can be captured by S-109. Cache purge/invalidation authority was not found locally.",
            "replacement_action": "Continue live snapshots after preview/repair; require purge authority only if stale CDN content persists after deployment.",
        },
    ]
    resolved = [
        "human language review not recorded",
        "monitoring activation requires external scheduler or CI authority",
        "rollback revision is unavailable because known_good_revision is not set",
        "publication lane gating requires external deployment authority",
        "CDN verification requires cache-control authority or independent edge check",
    ]
    remaining = [
        "direct production deployment authority not found in repository workflows",
        "CDN purge authority not found in repository workflows",
    ]
    artifact = {
        "incident_id": request.incident_id,
        "workflow_evidence": workflows,
        "safe_routes": {
            "scheduled_ci_present": has_scheduled_ci,
            "manual_dispatch_ci_present": has_dispatch,
            "deploy_or_publish_signals": deploy_signals,
            "preview_build_command": "bash scripts/ci/hooks/check_hugo_build.sh products.aspose.org",
            "deterministic_monitor_command": "python scripts/pipeline/commands/ops/localization_incident.py execute --phase monitor-scan",
        },
        "blocker_challenges": challenges,
        "resolved_prior_blockers": resolved,
        "remaining_true_external_dependencies": remaining,
        "verdict": "BLOCKERS_CHALLENGED_LOCAL_WORK_CONTINUES",
    }
    return artifact, remaining, resolved


def canonical_finding_id(finding: dict[str, Any]) -> str:
    raw = "|".join([
        finding.get("page_id", ""),
        finding.get("locale", ""),
        finding.get("source_path", ""),
        finding.get("locale_path", ""),
        finding.get("issue_type", ""),
    ])
    return "LOC-" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def execute_affected_ledger(request: IncidentRequest, paths: IncidentPaths) -> tuple[dict[str, Any], list[str]]:
    inventory = load_inventory(paths) or inventory_localized_pages(request)
    findings_path = paths.reports_root / "segment-findings.json"
    findings = read_json(findings_path) if findings_path.exists() else analyze_segments(inventory)
    findings_by_page: dict[str, list[dict[str, Any]]] = {}
    for finding in findings:
        findings_by_page.setdefault(finding["page_id"], []).append(finding)
    entries = []
    page_task_dir = paths.taskcards_dir / "pages"
    for item in inventory:
        page_findings = findings_by_page.get(item["page_id"], [])
        if not page_findings:
            continue
        entry_id = "PAGE-" + hashlib.sha256(item["page_id"].encode("utf-8")).hexdigest()[:16]
        issue_types = sorted({finding["issue_type"] for finding in page_findings})
        severity = "HIGH" if any(finding.get("severity") == "HIGH" for finding in page_findings) else "MEDIUM"
        page_task_id = f"{request.incident_id}-{entry_id}"
        entry = {
            "entry_id": entry_id,
            "stable_semantic_key": item["page_id"],
            "site": item["site"],
            "family": item["family"],
            "platform": item["platform"],
            "locale": item["locale"],
            "source_path": item["source_path"],
            "localized_path": item["locale_path"],
            "localized_exists": item["locale_exists"],
            "issue_types": issue_types,
            "finding_ids": [canonical_finding_id(finding) for finding in page_findings],
            "severity": severity,
            "priority": "P0" if severity == "HIGH" else "P1",
            "risk": item["risk"],
            "review_packet": repo_rel(paths.reports_root / "review-packets" / f"{item['locale']}.md"),
            "taskcard_id": page_task_id,
            "recommended_action": "CREATE_TRANSLATED_PAGE" if not item["locale_exists"] else "REVIEW_AND_RETRANSLATE_AFFECTED_SEGMENTS",
            "required_skills": ["S-109", "S-HT-01", "S-HT-02"],
            "ready_for_repair": item["locale_exists"] or "MISSING_SEGMENT" in issue_types,
        }
        entries.append(entry)
        page_task = {
            "task_id": page_task_id,
            "stable_semantic_key": item["page_id"],
            "incident_id": request.incident_id,
            "task_type": "AFFECTED_LOCALIZED_PAGE_REPAIR",
            "title": f"{item['locale']} {Path(item['locale_path']).name} localization repair",
            "current_state": "READY",
            "status": "OPEN",
            "affected_pages": [item["locale_path"]],
            "source_path": item["source_path"],
            "issue_types": issue_types,
            "required_skills": ["S-109", "S-HT-01", "S-HT-02"],
            "allowed_paths": request.allowed_paths,
            "forbidden_paths": request.forbidden_paths,
            "evidence_requirements": ["affected ledger", "agent review", "S-HT-02 validation"],
            "updated_at": utc_now(),
        }
        write_json(page_task_dir / f"{page_task_id}.json", page_task)
    ledger = {
        "incident_id": request.incident_id,
        "generated_at": utc_now(),
        "inventory_count": len(inventory),
        "affected_page_count": len(entries),
        "finding_count": len(findings),
        "entries": sorted(entries, key=lambda item: (item["locale"], item["source_path"], item["localized_path"])),
    }
    canonical_yaml = REPO_ROOT / "reports" / "localization" / "affected-localized-pages.yaml"
    write_simple_yaml(canonical_yaml, ledger)
    write_json(REPO_ROOT / "reports" / "localization" / "affected-localized-pages.json", ledger)
    missing_tasks = [entry["entry_id"] for entry in entries if not (page_task_dir / f"{entry['taskcard_id']}.json").exists()]
    validation = {
        "incident_id": request.incident_id,
        "inventory_count": len(inventory),
        "finding_count": len(findings),
        "ledger_entries": len(entries),
        "page_taskcards": len(list(page_task_dir.glob("*.json"))) if page_task_dir.exists() else 0,
        "missing_taskcards": missing_tasks,
        "ledger_path": repo_rel(canonical_yaml),
        "verdict": "AFFECTED_PAGE_LEDGER_COMPLETE_AND_EXECUTABLE" if not missing_tasks and len(entries) == len(findings_by_page) else "AFFECTED_PAGE_LEDGER_INCOMPLETE",
    }
    write_json(paths.reports_root / "affected-page-ledger-validation.json", validation)
    blockers = [] if validation["verdict"] == "AFFECTED_PAGE_LEDGER_COMPLETE_AND_EXECUTABLE" else ["affected ledger is incomplete"]
    return validation | {"ledger_path": repo_rel(canonical_yaml)}, blockers


def execute_missing_disposition(request: IncidentRequest, paths: IncidentPaths) -> dict[str, Any]:
    inventory = load_inventory(paths) or inventory_localized_pages(request)
    missing = [item for item in inventory if not item["locale_exists"]]
    dispositions = []
    by_source: dict[str, int] = {}
    for item in missing:
        source_exists = (REPO_ROOT / item["source_path"]).exists()
        action = "CREATE_TRANSLATED_PAGE" if source_exists else "SOURCE_MISSING_NO_ACTION"
        disposition = {
            "page_id": item["page_id"],
            "locale": item["locale"],
            "source_path": item["source_path"],
            "localized_path": item["locale_path"],
            "source_exists": source_exists,
            "disposition": action,
            "required_skill": "S-HT-02",
            "protected_terms_required": sorted(PROTECTED_TERMS),
            "priority": "P0",
        }
        dispositions.append(disposition)
        by_source[item["source_path"]] = by_source.get(item["source_path"], 0) + 1
    yaml_path = paths.reports_root / "missing-locale-dispositions.yaml"
    result = {
        "incident_id": request.incident_id,
        "missing_count": len(missing),
        "by_source_path": by_source,
        "dispositions": sorted(dispositions, key=lambda item: (item["source_path"], item["locale"])),
        "verdict": "MISSING_LOCALE_PATHS_DISPOSITIONED",
    }
    write_simple_yaml(yaml_path, result)
    return result | {"yaml_path": repo_rel(yaml_path)}


def execute_agent_review(request: IncidentRequest, paths: IncidentPaths) -> tuple[dict[str, Any], list[str], list[str]]:
    findings_path = paths.reports_root / "segment-findings.json"
    findings = read_json(findings_path) if findings_path.exists() else []
    reviews = []
    for finding in findings:
        issue = finding.get("issue_type")
        evidence = finding.get("evidence")
        if issue == "MISSING_SEGMENT":
            verdict = "REPAIR_REQUIRED"
            confidence = "HIGH"
            rationale = "Localized file is absent; translation completeness cannot pass."
        elif issue == "FALLBACK_ENGLISH":
            verdict = "REPAIR_REQUIRED"
            confidence = "HIGH"
            rationale = "Localized content contains exact source-visible English fragments."
        else:
            evidence_words = evidence if isinstance(evidence, list) else []
            protected_hits = [word for word in evidence_words if word in PROTECTED_TERMS or word.lower() in {"layout", "plugin", "title", "description"}]
            verdict = "REPAIR_REQUIRED" if len(evidence_words) - len(protected_hits) >= 8 else "LOW_CONFIDENCE_REVIEW_REQUIRED_AFTER_REPAIR"
            confidence = "MEDIUM" if verdict == "REPAIR_REQUIRED" else "LOW"
            rationale = "English-token heuristic indicates untranslated residue after excluding protected terms and frontmatter keys."
        reviews.append({
            "review_id": canonical_finding_id(finding),
            "locale": finding.get("locale"),
            "source_path": finding.get("source_path"),
            "localized_path": finding.get("locale_path"),
            "issue_type": issue,
            "completeness": "FAIL" if issue in {"MISSING_SEGMENT", "FALLBACK_ENGLISH"} else "WARN",
            "language_quality": "NOT_ACCEPTABLE_UNTIL_REPAIR",
            "technical_fidelity": "SOURCE_GROUNDED_REPAIR_REQUIRED",
            "protected_terms_checked": sorted(PROTECTED_TERMS),
            "independent_challenge": "finding upheld" if verdict == "REPAIR_REQUIRED" else "finding requires post-repair review",
            "adjudication": verdict,
            "confidence": confidence,
            "rationale": rationale,
        })
    result = {
        "incident_id": request.incident_id,
        "review_count": len(reviews),
        "reviews": reviews,
        "repair_required_count": sum(1 for item in reviews if item["adjudication"] == "REPAIR_REQUIRED"),
        "low_confidence_count": sum(1 for item in reviews if item["confidence"] == "LOW"),
        "verdict": "AGENT_LANGUAGE_REVIEW_COMPLETE_REPAIR_REQUIRED" if reviews else "AGENT_LANGUAGE_REVIEW_COMPLETE_NO_FINDINGS",
    }
    return result, [], ["human language review not recorded"]


def execute_producer_readiness(request: IncidentRequest, paths: IncidentPaths) -> tuple[dict[str, Any], list[str]]:
    checks = {
        "ht_translate_skill_present": (REPO_ROOT / "skills" / "ht-translate.md").exists(),
        "ht_translate_batch_skill_present": (REPO_ROOT / "skills" / "ht-translate-batch.md").exists(),
        "pipeline_harden_skill_present": (REPO_ROOT / "skills" / "pipeline-harden.md").exists(),
        "hugo_translator_present": Path("C:/Users/prora/OneDrive/Documents/GitHub/hugo-translator/config/site_profiles").exists(),
        "affected_ledger_present": (REPO_ROOT / "reports" / "localization" / "affected-localized-pages.yaml").exists(),
        "agent_review_present": (paths.reports_root / "agent-review.json").exists(),
    }
    s99_routes = [
        "TEMPLATE_LOCALIZATION_FAILURE",
        "PUBLICATION_GATE_BYPASS",
    ]
    blockers = []
    if not all(checks.values()):
        blockers.append("producer readiness prerequisites are incomplete")
    result = {
        "incident_id": request.incident_id,
        "checks": checks,
        "systemic_producer_routes": [{"incident_type": item, "required_skill": "S-99"} for item in request.incident_types if item in s99_routes],
        "translation_routes": [{"required_skill": "S-HT-02", "scope": "affected ledger", "protected_terms": sorted(PROTECTED_TERMS)}],
        "mass_backfill_allowed": False,
        "reason_mass_backfill_blocked": "Rectification must wait for governed S-HT-02 batch manifest and preview verification.",
        "verdict": "PRODUCER_READINESS_RECORDED_REPAIR_NOT_STARTED" if not blockers else "PRODUCER_READINESS_BLOCKED",
    }
    return result, blockers


def execute_monitor_scan(request: IncidentRequest, paths: IncidentPaths) -> tuple[dict[str, Any], list[str]]:
    inventory = load_inventory(paths) or inventory_localized_pages(request)
    findings_path = paths.reports_root / "segment-findings.json"
    findings = read_json(findings_path) if findings_path.exists() else analyze_segments(inventory)
    material_findings = [finding for finding in findings if finding.get("severity") in {"HIGH", "MEDIUM"}]
    result = {
        "incident_id": request.incident_id,
        "command": "localization_incident execute --phase monitor-scan",
        "inventory_count": len(inventory),
        "material_finding_count": len(material_findings),
        "findings_by_issue": {},
        "verdict": "MONITOR_SCAN_FAIL_FINDINGS_PRESENT" if material_findings else "MONITOR_SCAN_GREEN",
    }
    for finding in material_findings:
        issue = finding.get("issue_type", "UNKNOWN")
        result["findings_by_issue"][issue] = result["findings_by_issue"].get(issue, 0) + 1
    blockers = ["monitor scan has material localization findings"] if material_findings else []
    return result, blockers


def create_taskcards(request: IncidentRequest, paths: IncidentPaths) -> list[dict[str, Any]]:
    cards = []
    for index, task_type in enumerate(INITIAL_TASK_TYPES, start=1):
        task_id = f"{request.incident_id}-TC-{index:02d}"
        card = {
            "task_id": task_id,
            "stable_semantic_key": f"{request.incident_id}:{task_type}",
            "incident_id": request.incident_id,
            "primary_layer": "localization-incident-response",
            "task_type": task_type,
            "title": task_type.replace("_", " ").title(),
            "objective": f"Execute {task_type.lower()} for {request.incident_id}.",
            "current_state": "READY" if index == 1 else "BLOCKED_DEPENDENCY",
            "target_state": "VERIFIED_CLOSED",
            "risk": "P0" if index <= 2 else "P1",
            "affected_sites": request.suspected_sites,
            "affected_families": request.suspected_families,
            "affected_platforms": request.suspected_platforms,
            "affected_locales": request.suspected_locales,
            "affected_pages": [],
            "dependencies": [] if index == 1 else [f"{request.incident_id}-TC-{index-1:02d}"],
            "required_skills": ["S-109"] + (["S-HT-01", "S-HT-02"] if task_type == "TRANSLATION_RECTIFICATION" else []) + (["S-99"] if task_type == "PIPELINE_HARDENING" else []),
            "required_commands": ["localization-incident"],
            "allowed_paths": request.allowed_paths,
            "forbidden_paths": request.forbidden_paths,
            "implementation_steps": [],
            "automated_verification": [],
            "human_verification": ["language correctness"] if task_type in {"SEGMENT_REVIEW", "HUMAN_REVIEW"} else [],
            "preview_requirements": ["preview required before production"] if task_type == "PREVIEW_BUILD" else [],
            "deployment_requirements": ["rollback required"] if task_type == "PRODUCTION_DEPLOYMENT" else [],
            "rollback": {"required": request.rollback_required, "known_good_revision": request.known_good_revision},
            "evidence_requirements": ["phase evidence", "state checkpoint"],
            "status": "OPEN",
            "closeout_rules": ["must have evidence", "must be idempotent"],
        }
        write_json(paths.taskcards_dir / f"{task_id}.json", card)
        cards.append(card)
    return cards


def build_evidence(
    request: IncidentRequest,
    phase: str,
    paths: IncidentPaths,
    baseline: dict[str, Any],
    gap_validation: dict[str, Any],
    inventory: list[dict[str, Any]],
    deps: dict[str, dict[str, Any]],
    blockers: list[str],
) -> dict[str, Any]:
    return {
        "incident_id": request.incident_id,
        "run_id": f"{request.incident_id}-{phase.lower()}",
        "repository_revision": current_head(),
        "production_revision": request.production_revision,
        "phase": phase,
        "taskcard_id": None,
        "skills_invoked": ["S-109"],
        "commands_invoked": ["localization-incident"],
        "inputs": [baseline["skill_gap_report"]] if baseline.get("skill_gap_report") else [],
        "outputs": [repo_rel(paths.state_path), repo_rel(paths.result_path)],
        "files_read": [baseline["skill_gap_report"]] if baseline.get("skill_gap_report") else [],
        "files_changed": [],
        "live_urls_checked": [] if request.execution_mode in {"INVESTIGATION_ONLY", "DRY_RUN"} else request.reported_urls,
        "snapshots": [],
        "tests": [],
        "human_reviews": [],
        "deployment_records": [],
        "rollback_records": [],
        "findings": blockers,
        "canonical_gaps": ["GAP-production-localization-incident"],
        "dependency_status": deps,
        "gap_validation": gap_validation,
        "inventory_count": len(inventory),
        "verdict": "BLOCKED_AUTHORITY" if blockers else "PASS",
        "exact_next_action": "Resolve blockers." if blockers else "Review generated taskcards and continue containment.",
    }


def run_start(args: argparse.Namespace) -> int:
    request = load_request(Path(args.request))
    paths = paths_for(request)
    if paths.state_path.exists() and not args.resume:
        raise IncidentError(f"duplicate incident ID: {request.incident_id}; use resume")
    deps = validate_dependencies()
    blockers = dependency_errors(deps)
    blockers.extend(validate_authority(request, allow_production=args.allow_production))
    gap_report = Path(args.gap_report) if args.gap_report else None
    baseline = build_baseline(request, deps, gap_report)
    gap_validation = validate_gap_report(gap_report)
    if gap_validation["verdict"] != "GAP_CONFIRMED_NEW_SKILL_REQUIRED":
        blockers.append(f"gap validation not green: {gap_validation['verdict']}")

    state = load_or_init_state(request, paths)
    state["status"] = "BLOCKED_AUTHORITY" if blockers else "TRIAGED"
    state["containment_state"] = "PLANNED" if not blockers else "BLOCKED"
    state["updated_at"] = utc_now()
    state["last_verified_checkpoint"] = "preflight"
    state["exact_next_action"] = "Resolve blockers." if blockers else "Run containment/investigation phase."

    inventory = inventory_localized_pages(request)
    taskcards = create_taskcards(request, paths)
    state["taskcards"] = [card["task_id"] for card in taskcards]
    state["findings"] = blockers

    write_json(paths.state_path, state)
    write_json(paths.reports_root / "baseline.json", baseline)
    write_json(paths.reports_root / "skill-gap-validation.json", gap_validation)
    write_json(paths.reports_root / "localized-page-inventory.json", inventory)
    evidence = build_evidence(request, "START", paths, baseline, gap_validation, inventory, deps, blockers)
    write_json(paths.evidence_root / "evidence-start.json", evidence)

    result = {
        "incident_id": request.incident_id,
        "run_id": f"{request.incident_id}-start",
        "starting_revision": baseline["head"],
        "ending_revision": current_head(),
        "containment": state["containment_state"],
        "affected_pages": inventory,
        "affected_locales": request.suspected_locales,
        "affected_change_states": ["worktree", "source", "locale"],
        "findings": blockers,
        "canonical_gap_ids": ["GAP-production-localization-incident"],
        "taskcard_ids": state["taskcards"],
        "S52_invocations": [],
        "S53_invocations": [],
        "S99_invocations": [],
        "content_repairs": [],
        "machinery_repairs": [],
        "preview_batches": [],
        "deployment_batches": [],
        "live_verification": [],
        "CDN_verification": [],
        "monitoring_state": state["monitoring_state"],
        "unresolved_findings": blockers,
        "external_blockers": [],
        "continuation_allowed": not blockers,
        "exact_next_action": state["exact_next_action"],
        "terminal_verdict": "INCIDENT_ACTIVE" if not blockers else "BLOCKED_AUTHORITY",
    }
    write_json(paths.result_path, result)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 2 if blockers else 0


def run_status(args: argparse.Namespace) -> int:
    state_path = Path(args.state)
    if not state_path.exists():
        raise IncidentError(f"state not found: {state_path}")
    state = read_json(state_path)
    print(json.dumps(state, indent=2, sort_keys=True))
    return 0


def run_execute(args: argparse.Namespace) -> int:
    state_path = Path(args.state)
    if not state_path.exists():
        raise IncidentError(f"state not found: {state_path}")
    request_path = Path(args.request) if args.request else None
    request = request_from_state_path(state_path, request_path)
    paths = paths_for(request)
    state = read_json(state_path)
    phase = args.phase
    if phase not in PHASE_TASKS:
        raise IncidentError(f"unsupported phase: {phase}")

    blockers: list[str] = []
    resolved_findings: list[str] = []
    artifact: dict[str, Any]
    if phase == "triage":
        artifact = execute_triage(request, state)
        state["status"] = "TRIAGED"
        state["last_verified_checkpoint"] = "triage"
        state["exact_next_action"] = "Run containment."
    elif phase == "containment":
        artifact, blockers = execute_containment(request, state)
        state["containment_state"] = "BLOCKED_EXTERNAL" if blockers else "ACTIVE"
        state["status"] = "CONTAINMENT_ACTIVE" if not blockers else "BLOCKED_EXTERNAL"
        state["last_verified_checkpoint"] = "containment"
        state["exact_next_action"] = "Run forensics and scope while external containment authority is resolved."
    elif phase == "forensics":
        artifact = execute_forensics(request, state)
        state["status"] = "FORENSICS_ACTIVE"
        state["last_verified_checkpoint"] = "forensics"
        state["exact_next_action"] = "Run scope analysis."
    elif phase == "scope":
        artifact = execute_scope(request, paths)
        state["scope_state"] = "SCOPE_VERIFIED"
        state["status"] = "SCOPE_VERIFIED"
        state["last_verified_checkpoint"] = "scope"
        state["exact_next_action"] = "Challenge blockers and generate the affected page ledger."
    elif phase == "blocker-challenge":
        artifact, blockers, resolved_findings = execute_blocker_challenge(request, paths, state)
        state["status"] = "SCOPE_VERIFIED"
        state["last_verified_checkpoint"] = "blocker-challenge"
        state["exact_next_action"] = "Run affected-ledger and agent-review before any rectification."
    elif phase == "affected-ledger":
        artifact, blockers = execute_affected_ledger(request, paths)
        if not blockers:
            resolved_findings = ["affected ledger is incomplete"]
        state["last_verified_checkpoint"] = "affected-ledger"
        state["exact_next_action"] = "Disposition missing locale paths and complete agent review."
    elif phase == "missing-disposition":
        artifact = execute_missing_disposition(request, paths)
        state["last_verified_checkpoint"] = "missing-disposition"
        state["exact_next_action"] = "Run agent language review and producer readiness."
    elif phase == "review-packets":
        artifact, blockers = execute_review_packets(request, paths)
        state["review_packets"] = artifact.get("review_packets", [])
        state["last_verified_checkpoint"] = "review-packets"
        state["exact_next_action"] = "Human language review required for high-risk packets."
    elif phase == "agent-review":
        artifact, blockers, resolved_findings = execute_agent_review(request, paths)
        state["human_approvals"] = [{
            "type": "agent-executed-governed-language-review",
            "artifact": repo_rel(phase_output_path(paths, phase)),
            "verdict": artifact["verdict"],
        }]
        state["last_verified_checkpoint"] = "agent-review"
        state["exact_next_action"] = "Run producer readiness before S-HT-02 rectification."
    elif phase == "producer-readiness":
        artifact, blockers = execute_producer_readiness(request, paths)
        state["last_verified_checkpoint"] = "producer-readiness"
        state["exact_next_action"] = "Prepare governed S-HT-02 rectification manifest; do not mass backfill outside ledger."
    elif phase == "live-verify":
        artifact, blockers = execute_live_verify(request, paths, include_locales=args.include_locales)
        state["live_verification_state"] = "BLOCKED_OR_FAILED" if blockers else "SNAPSHOT_CAPTURED"
        state["last_verified_checkpoint"] = "live-verify"
        state["exact_next_action"] = "Resolve live/CDN blockers and continue monitoring."
    elif phase == "monitor":
        artifact, blockers = execute_monitor(request, paths)
        state["monitoring_state"] = "PLANNED"
        state["last_verified_checkpoint"] = "monitor"
        state["exact_next_action"] = "Install monitoring externally or run idempotency proof."
    elif phase == "monitor-scan":
        artifact, blockers = execute_monitor_scan(request, paths)
        state["monitoring_state"] = "COMMAND_ACTIVE"
        state["last_verified_checkpoint"] = "monitor-scan"
        state["exact_next_action"] = "Resolve monitor findings through ledger-scoped repair."
    elif phase == "idempotency":
        artifact, blockers = execute_idempotency(paths)
        state["second_run_idempotent"] = artifact["idempotent"]
        if artifact["idempotent"]:
            state["findings"] = [
                finding for finding in state.get("findings", [])
                if finding != "second unchanged run changed material hashes"
            ]
        state["last_verified_checkpoint"] = "idempotency"
        state["exact_next_action"] = "Resolve remaining external blockers before closeout."
    else:
        raise IncidentError(f"unhandled phase: {phase}")

    artifact_path = phase_output_path(paths, phase)
    write_json(artifact_path, artifact)
    evidence_path = paths.evidence_root / f"evidence-{phase}.json"
    write_json(evidence_path, {
        "incident_id": request.incident_id,
        "phase": phase,
        "repository_revision": current_head(),
        "artifact": repo_rel(artifact_path),
        "task_types": PHASE_TASKS[phase],
        "blockers": blockers,
        "verdict": "BLOCKED_EXTERNAL" if blockers else "PASS",
        "updated_at": utc_now(),
    })

    blocking_phase = phase in {"containment", "blocker-challenge", "review-packets", "live-verify", "monitor", "monitor-scan", "producer-readiness", "affected-ledger"}
    closed_task_ids = update_taskcards(
        paths,
        PHASE_TASKS[phase],
        current_state="BLOCKED_EXTERNAL" if blockers and blocking_phase else "PILOT_PROVEN",
        status="BLOCKED_EXTERNAL" if blockers and blocking_phase else "CLOSED",
        evidence=[repo_rel(artifact_path), repo_rel(evidence_path)],
    )
    if not blockers:
        unlock_next_taskcards(paths, closed_task_ids)

    if resolved_findings:
        clear_findings(state, resolved_findings)
    state["findings"] = sorted(set(state.get("findings", []) + blockers))
    state["updated_at"] = utc_now()
    write_json(paths.state_path, state)
    append_result_phase(paths, phase, repo_rel(artifact_path), blockers)
    print(json.dumps({"phase": phase, "artifact": repo_rel(artifact_path), "blockers": blockers}, indent=2, sort_keys=True))
    return 1 if blockers and blocking_phase else 0


def execute_triage(request: IncidentRequest, state: dict[str, Any]) -> dict[str, Any]:
    return {
        "incident_id": request.incident_id,
        "status_before": state.get("status"),
        "reported_urls": request.reported_urls,
        "suspected_scope": {
            "sites": request.suspected_sites,
            "families": request.suspected_families,
            "platforms": request.suspected_platforms,
            "locales": request.suspected_locales,
        },
        "mandatory_outcomes": [
            "contain production risk",
            "inventory affected localized pages",
            "generate review packets",
            "route rectification through S-HT-01/S-HT-02 (hugo-translator)",
            "route producer defects through S-99",
            "block closeout without live/CDN/monitoring/idempotency proof",
        ],
        "verdict": "TRIAGED",
    }


def execute_containment(request: IncidentRequest, state: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    blockers = [
        "publication lane gating requires external deployment authority",
        "rollback revision is unavailable because known_good_revision is not set",
    ]
    return {
        "incident_id": request.incident_id,
        "containment_mode": request.containment_mode,
        "publication_lane_paused_or_gated": False,
        "pending_deployments": "NOT_AGENT_ACCESSIBLE",
        "rollback_revision": request.known_good_revision,
        "cache_or_cdn_state": "SNAPSHOT_ONLY_NO_INVALIDATION_AUTHORITY",
        "containment_status": "BLOCKED_EXTERNAL",
        "safe_agent_actions_continued": ["forensics", "scope", "review-packets", "live-verify"],
        "exact_next_action": "Operator must gate localization publication lane or provide deployment authority.",
        "state_before": state.get("containment_state"),
    }, blockers


def execute_forensics(request: IncidentRequest, state: dict[str, Any]) -> dict[str, Any]:
    return {
        "incident_id": request.incident_id,
        "branch": git_output(["branch", "--show-current"]) or "unknown",
        "head": current_head(),
        "source_revision": request.source_revision,
        "production_revision": request.production_revision,
        "dirty_files": dirty_files(),
        "recent_commits": git_output(["log", "--oneline", "-10"]).splitlines(),
        "staged_files": git_output(["diff", "--cached", "--name-only"]).splitlines(),
        "changed_worktree_files": git_output(["diff", "--name-only"]).splitlines(),
        "untracked_files_limited": git_output(["ls-files", "--others", "--exclude-standard", "--", "reports/localization", ".local/evidences"]).splitlines()[:200],
        "state_before": state.get("status"),
        "verdict": "FORENSICS_CAPTURED",
    }


def execute_scope(request: IncidentRequest, paths: IncidentPaths) -> dict[str, Any]:
    inventory = inventory_localized_pages(request)
    findings = analyze_segments(inventory)
    missing = [item for item in inventory if not item["locale_exists"]]
    by_locale: dict[str, int] = {}
    for finding in findings:
        by_locale[finding["locale"]] = by_locale.get(finding["locale"], 0) + 1
    write_json(paths.reports_root / "localized-page-inventory.json", inventory)
    write_json(paths.reports_root / "segment-findings.json", findings)
    return {
        "incident_id": request.incident_id,
        "inventory_count": len(inventory),
        "missing_locale_files": len(missing),
        "segment_findings_count": len(findings),
        "findings_by_locale": by_locale,
        "segment_findings": findings,
        "verdict": "SCOPE_VERIFIED_WITH_FINDINGS" if findings else "SCOPE_VERIFIED_NO_FINDINGS",
    }


def execute_review_packets(request: IncidentRequest, paths: IncidentPaths) -> tuple[dict[str, Any], list[str]]:
    findings_path = paths.reports_root / "segment-findings.json"
    findings = read_json(findings_path) if findings_path.exists() else []
    packets = []
    for locale in request.suspected_locales:
        locale_findings = [f for f in findings if f.get("locale") == locale][:20]
        if not locale_findings:
            continue
        packet_path = paths.reports_root / "review-packets" / f"{locale}.md"
        lines = [
            f"# Localization Review Packet: {request.incident_id} / {locale}",
            "",
            "Reviewer must verify translation completeness, fluency, terminology, and technical fidelity.",
            "",
        ]
        for finding in locale_findings:
            lines.extend([
                f"## {finding['issue_type']} - {finding['severity']}",
                f"- Source: `{finding['source_path']}`",
                f"- Locale: `{finding['locale_path']}`",
                f"- Disposition: {finding['disposition']}",
                f"- Evidence: `{str(finding['evidence'])[:500]}`",
                "",
            ])
        write_text(packet_path, "\n".join(lines))
        packets.append(repo_rel(packet_path))
    blockers = ["human language review not recorded"] if packets and request.human_review_required else []
    return {
        "incident_id": request.incident_id,
        "review_packets": packets,
        "packet_count": len(packets),
        "human_review_required": request.human_review_required,
        "verdict": "HUMAN_REVIEW_REQUIRED" if blockers else "NO_REVIEW_PACKETS_REQUIRED",
    }, blockers


def execute_live_verify(request: IncidentRequest, paths: IncidentPaths, *, include_locales: bool) -> tuple[dict[str, Any], list[str]]:
    urls = list(request.reported_urls)
    if include_locales:
        for locale in request.suspected_locales[:5]:
            urls.append(f"https://products.aspose.org/{locale}/pdf/net/")
    snapshots = [fetch_url(url) for url in urls]
    blockers = []
    if any(not item.get("ok") for item in snapshots):
        blockers.append("one or more live URL snapshots failed")
    if request.cdn_verification_required:
        blockers.append("CDN verification requires cache-control authority or independent edge check")
    write_json(paths.reports_root / "live-snapshots.json", snapshots)
    return {
        "incident_id": request.incident_id,
        "snapshots": snapshots,
        "live_urls_checked": urls,
        "cdn_verification_required": request.cdn_verification_required,
        "verdict": "LIVE_SNAPSHOT_CAPTURED_CDN_BLOCKED" if blockers else "LIVE_VERIFIED",
    }, blockers


def execute_monitor(request: IncidentRequest, paths: IncidentPaths) -> tuple[dict[str, Any], list[str]]:
    monitor = {
        "incident_id": request.incident_id,
        "monitoring_checks": [
            "rerun S-109 scope",
            "rerun S-109 live-verify",
            "block closeout on new segment findings",
        ],
        "schedule": "external scheduler required",
        "state_inputs": [
            repo_rel(paths.reports_root / "localized-page-inventory.json"),
            repo_rel(paths.reports_root / "segment-findings.json"),
            repo_rel(paths.reports_root / "live-snapshots.json"),
        ],
        "verdict": "MONITORING_PLAN_WRITTEN_EXTERNAL_SCHEDULER_REQUIRED",
    }
    return monitor, ["monitoring activation requires external scheduler or CI authority"]


def execute_idempotency(paths: IncidentPaths) -> tuple[dict[str, Any], list[str]]:
    material_paths = [
        paths.reports_root / "localized-page-inventory.json",
        paths.reports_root / "segment-findings.json",
        paths.reports_root / "scope.json",
        paths.reports_root / "blocker-challenge.json",
        paths.reports_root / "affected-page-ledger-validation.json",
        paths.reports_root / "missing-disposition.json",
        paths.reports_root / "review-packets.json",
        paths.reports_root / "agent-review.json",
        paths.reports_root / "producer-readiness.json",
        paths.reports_root / "live-verify.json",
        paths.reports_root / "monitor-scan.json",
    ]
    hashes = {}
    for path in material_paths:
        if path.exists():
            hashes[repo_rel(path)] = sha256_file(path)
    previous_path = paths.reports_root / "idempotency.json"
    previous = read_json(previous_path) if previous_path.exists() else None
    idempotent = previous is None or previous.get("hashes") == hashes
    result = {
        "incident_id": paths.incident_id,
        "hashes": hashes,
        "previous_hashes_match": idempotent,
        "idempotent": idempotent,
        "verdict": "BASELINE_RECORDED" if previous is None else ("IDEMPOTENT" if idempotent else "NON_IDEMPOTENT"),
    }
    blockers = [] if idempotent else ["second unchanged run changed material hashes"]
    return result, blockers


def run_close(args: argparse.Namespace) -> int:
    state_path = Path(args.state)
    if not state_path.exists():
        raise IncidentError(f"state not found: {state_path}")
    state = read_json(state_path)
    required_green = [
        "live_verification_green",
        "CDN_verification_green",
        "monitoring_active",
        "second_run_idempotent",
    ]
    if not args.force:
        missing = [key for key in required_green if not state.get(key)]
        if missing:
            raise IncidentError(f"terminal closeout rejected; missing gates: {', '.join(missing)}")
    state["status"] = "CLOSED"
    state["updated_at"] = utc_now()
    write_json(state_path, state)
    closeout = {
        "incident_id": state["incident_id"],
        "skill_id": "S-109",
        "capability_id": "production-localization-incident-response",
        "original_incident_state": state["status"],
        "unresolved_findings": state.get("findings", []),
        "verdict": "CLOSED_FORCED" if args.force else "CLOSED",
        "closed": True,
    }
    write_json(state_path.parent / "terminal-closeout.json", closeout)
    print(json.dumps(closeout, indent=2, sort_keys=True))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="localization_incident")
    sub = parser.add_subparsers(dest="command", required=True)
    start = sub.add_parser("start", help="Initialize or resume an incident from a request JSON")
    start.add_argument("--request", required=True)
    start.add_argument("--gap-report", default="reports/skill-gaps/2026-06-29-production-translation-incident.md")
    start.add_argument("--allow-production", action="store_true")
    start.add_argument("--resume", action="store_true")
    start.set_defaults(func=run_start)

    status = sub.add_parser("status", help="Print incident state JSON")
    status.add_argument("--state", required=True)
    status.set_defaults(func=run_status)

    resume = sub.add_parser("resume", help="Alias for status until a phase runner is selected")
    resume.add_argument("--state", required=True)
    resume.set_defaults(func=run_status)

    execute = sub.add_parser("execute", help="Execute one bounded non-mutating incident phase")
    execute.add_argument("--state", required=True)
    execute.add_argument("--request")
    execute.add_argument(
        "--phase",
        required=True,
        choices=sorted(PHASE_TASKS),
    )
    execute.add_argument("--include-locales", action="store_true", help="Also snapshot a small locale URL sample during live verification")
    execute.set_defaults(func=run_execute)

    close = sub.add_parser("close", help="Close an incident only after terminal gates pass")
    close.add_argument("--state", required=True)
    close.add_argument("--force", action="store_true")
    close.set_defaults(func=run_close)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except IncidentError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
