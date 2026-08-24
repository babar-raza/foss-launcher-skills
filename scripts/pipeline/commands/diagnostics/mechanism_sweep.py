#!/usr/bin/env python3
"""Mechanism sweep (S-117, Task 7, mission-plan-the-end-to-end-vast-hejlsberg.md
§9.4, closes G2): detect which already-launched products are stale because OUR
OWN pipeline code (extraction/enrichment/snippet/format detection) improved,
independent of any upstream FOSS repo change.

This is the deliberate sibling of change-sweep (repo_patrol.py's cmd_sweep):
change-sweep watches the *upstream FOSS repo* axis (did the source change?);
this script watches the *our own pipeline code* axis (did re-running the same,
unchanged source through corrected extraction/enrichment produce a different
result?). See skills/mechanism-sweep.md for the full skill contract this script
backs.

Precondition this script assumes, matching the skill's own precondition (its own
docstring: "the triggering fix has already landed"), extended one step further:
for each candidate, the FIXED extraction/enrichment/snippet/format step must
already have been re-run against that candidate's already-cloned source, so
knowledge/{family}/{platform}/scout/ already reflects its corrected output. This
script does not know, and cannot generically know, which specific script changed
for an arbitrary future fix -- that re-run is the agent's own responsibility
(mirroring the skill's own step 2 instruction), same as it always has been.
What this script automates is everything after that point: the compute-only
promote() diff (never promote_atomic()'s atomic swap -- the real merged/ is
never touched), page-impact classification (NONE/METADATA_ONLY/CONTENT_AFFECTING),
the upstream-drift separation check (step 4), and the sweep report (step 6).
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

_PIPELINE_DIR = Path(__file__).resolve().parents[2]  # commands/diagnostics/ -> commands/ -> pipeline/
if str(_PIPELINE_DIR) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_DIR))
_LIB_DIR = str(_PIPELINE_DIR / "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)

import yaml  # noqa: E402

from commands.knowledge.promote import promote as _real_promote  # noqa: E402
from commands.ops import page_impact_assess  # noqa: E402
from core.clone_cache import (  # noqa: E402
    clone_exists as _real_clone_exists,
    clone_head_sha as _real_clone_head_sha,
)

_REPO_ROOT = Path(__file__).resolve().parents[4]
_REGISTRY_PATH = _REPO_ROOT / "data" / "products.json"
_PHASE_STATE_PATH = _REPO_ROOT / "reports" / "phase_state.json"
_REPORT_ROOT = _REPO_ROOT / "reports" / "mechanism_sweep"

_LAUNCHED_PHASE_KEYS = ("docs_done", "kb_done", "reference_done", "products_done")

# configure()-seam pattern (matches refresh_run.py's own command_runner/
# source_sha_resolver seams): monkeypatch-lint's T2 rule bans direct
# monkeypatch.setattr on a module's real collaborators, so tests override
# these through configure() instead of patching promote/clone_exists/
# clone_head_sha in place.
_promote_fn = _real_promote
_clone_exists_fn = _real_clone_exists
_clone_head_sha_fn = _real_clone_head_sha


def configure(
    *,
    promote_fn=None,
    clone_exists_fn=None,
    clone_head_sha_fn=None,
) -> None:
    """Override this module's collaborators for tests; call with no arguments to reset."""
    global _promote_fn, _clone_exists_fn, _clone_head_sha_fn
    _promote_fn = promote_fn or _real_promote
    _clone_exists_fn = clone_exists_fn or _real_clone_exists
    _clone_head_sha_fn = clone_head_sha_fn or _real_clone_head_sha


def _load_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def enumerate_candidates(
    language: str,
    *,
    exclude: set[tuple[str, str]] | None = None,
    registry_path: Path = _REGISTRY_PATH,
    phase_state_path: Path = _PHASE_STATE_PATH,
) -> list[dict]:
    """Enumerate already-launched products matching `language`, per skill step 1.

    "language" maps 1:1 to this repo's own `platform` field (this codebase has
    no separate language field in data/products.json -- confirmed by direct
    read; platform values like "java"/"go"/"rust"/"cpp" already ARE the
    language/ecosystem identifier everywhere else in this pipeline).
    "Already-launched" is judged from reports/phase_state.json: a product with
    no phase-state entry at all was never scored and is excluded, even if
    `active: true` in products.json (onboarding-in-progress, not yet launched).
    """
    exclude = exclude or set()
    registry = _load_json(registry_path, [])
    phase_state = _load_json(phase_state_path, {})

    candidates = []
    for entry in registry:
        family = entry.get("family")
        platform = entry.get("platform")
        if not family or not platform:
            continue
        if platform.lower() != language.lower():
            continue
        if not entry.get("active"):
            continue
        if (family, platform) in exclude:
            continue
        phase = phase_state.get(f"{family}/{platform}")
        if not phase:
            continue
        values = phase.get("values", {})
        if not all(values.get(key) for key in _LAUNCHED_PHASE_KEYS):
            continue
        candidates.append({"family": family, "platform": platform})
    return candidates


def _model_repo_sha(family: str, platform: str, knowledge_root: Path) -> str | None:
    model_path = knowledge_root / family / platform / "merged" / "model.yaml"
    if not model_path.is_file():
        return None
    try:
        model = yaml.safe_load(model_path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError:
        return None
    return model.get("repo_sha") or None


def check_upstream_drift(family: str, platform: str, *, knowledge_root: Path = _REPO_ROOT / "knowledge") -> dict | None:
    """Per skill step 4: if the candidate's clone-cache HEAD already differs from
    the knowledge model's last-scouted repo_sha, any diff this sweep would find
    is contaminated by genuine upstream drift, not attributable to the pipeline-
    code fix alone. Never calls update_clone() -- this sweep must never pull
    upstream (that is change-sweep's axis, not this one's), only read the clone
    cache's current, already-fetched HEAD.

    Returns a dict describing the drift if detected (candidate should be routed
    to the separated_upstream_drift bucket, not classified NONE/METADATA_ONLY/
    CONTENT_AFFECTING), or None if the source is confirmed unchanged since the
    last scout (safe to proceed with a pure mechanism-only diff).
    """
    if not _clone_exists_fn(family, platform):
        return {"reason": "no local clone exists"}
    stored_sha = _model_repo_sha(family, platform, knowledge_root)
    if stored_sha is None:
        return {"reason": "no model.yaml / repo_sha on record"}
    current_sha = _clone_head_sha_fn(family, platform)
    if current_sha is None:
        return {"reason": "could not resolve clone HEAD"}
    if current_sha != stored_sha:
        return {
            "reason": "clone HEAD differs from last-scouted repo_sha -- diff would mix upstream drift with the mechanism fix",
            "stored_sha": stored_sha,
            "current_sha": current_sha,
        }
    return None


def _by_claim_id(claims: list) -> dict:
    return {c["claim_id"]: c for c in claims if isinstance(c, dict) and "claim_id" in c}


def _by_api_name(apis: list) -> dict:
    return {e["name"]: e for e in apis if isinstance(e, dict) and "name" in e}


def compute_delta(old_claims: list, new_claims: list, old_apis: list, new_apis: list) -> dict:
    """Pure diff, same field shape refresh_knowledge.py's _write_knowledge_delta
    already produces (new_claims/removed_claims/modified_claims/new_apis/
    removed_apis/modified_apis) -- reused as a shape, not as a direct function
    call: _write_knowledge_delta is keyed to a real SHA transition and always
    writes a knowledge_delta.json side effect, neither of which applies here
    (a mechanism-sweep diff is same-source, no SHA moved, and must never write
    into any real knowledge/ tree). This mirrors its comparison algorithm
    exactly (claims by claim_id, apis by name, modified = method/property
    name-set changes) for a same-source, before/after-pipeline-fix comparison.
    """
    old_by_id = _by_claim_id(old_claims)
    new_by_id = _by_claim_id(new_claims)
    new_claim_ids = [cid for cid in new_by_id if cid not in old_by_id]
    removed_claim_ids = [cid for cid in old_by_id if cid not in new_by_id]
    modified_claim_ids = [
        cid for cid in new_by_id
        if cid in old_by_id and (
            new_by_id[cid].get("text") != old_by_id[cid].get("text")
            or new_by_id[cid].get("confidence") != old_by_id[cid].get("confidence")
        )
    ]

    old_api_by_name = _by_api_name(old_apis)
    new_api_by_name = _by_api_name(new_apis)
    old_names = set(old_api_by_name)
    new_names = set(new_api_by_name)
    new_api_names = sorted(new_names - old_names)
    removed_api_names = sorted(old_names - new_names)
    modified_api_names = sorted(
        name for name in new_names & old_names
        if (
            {m.get("name") for m in new_api_by_name[name].get("methods", [])}
            != {m.get("name") for m in old_api_by_name[name].get("methods", [])}
        ) or (
            {p.get("name") for p in new_api_by_name[name].get("properties", [])}
            != {p.get("name") for p in old_api_by_name[name].get("properties", [])}
        )
    )

    return {
        "new_claims": new_claim_ids,
        "removed_claims": removed_claim_ids,
        "modified_claims": modified_claim_ids,
        "new_apis": new_api_names,
        "removed_apis": removed_api_names,
        "modified_apis": modified_api_names,
    }


def _delta_is_empty(delta: dict) -> bool:
    return not any(delta[key] for key in (
        "new_claims", "removed_claims", "modified_claims",
        "new_apis", "removed_apis", "modified_apis",
    ))


def diff_only_rerun(family: str, platform: str, *, knowledge_root: Path = _REPO_ROOT / "knowledge") -> dict:
    """Compute-only diff: re-run promote() into an isolated staging directory
    (never promote_atomic()'s atomic swap into the real merged/), then diff
    against the CURRENT real merged/ state. The real merged/ is read but never
    written -- mirrors promote_atomic()'s own staging setup (line ~1848-1860 of
    promote.py: a sibling `merged.staging.{uuid}` dir, seeded with a copy of the
    current merged/ so promote()'s own "read prior state" logic still works),
    just without ever calling _atomic_swap().

    Requires knowledge/{family}/{platform}/scout/claims.json to already reflect
    the fixed step's re-run output (see this module's own docstring) -- promote()
    itself raises/returns False otherwise, surfaced here as a RuntimeError.
    """
    base = knowledge_root / family / platform
    real_merged = base / "merged"
    old_claims = _load_json(real_merged / "claims.json", [])
    old_apis = _load_json(real_merged / "api_surface.json", [])

    staging_dir = base / f"merged.sweep-staging.{uuid.uuid4()}"
    if real_merged.is_dir():
        shutil.copytree(real_merged, staging_dir)
    else:
        staging_dir.mkdir(parents=True, exist_ok=True)
    try:
        success = _promote_fn(family, platform, knowledge_root, merged_dir_override=staging_dir)
        if not success:
            raise RuntimeError(
                f"promote() returned False for {family}/{platform} -- "
                f"is scout/claims.json present and current-step output re-run?"
            )
        new_claims = _load_json(staging_dir / "claims.json", [])
        new_apis = _load_json(staging_dir / "api_surface.json", [])
        return compute_delta(old_claims, new_claims, old_apis, new_apis)
    finally:
        shutil.rmtree(staging_dir, ignore_errors=True)


def classify_candidate(
    family: str,
    platform: str,
    delta: dict,
    *,
    content_root: Path = _REPO_ROOT / "content",
) -> tuple[str, dict]:
    """Per skill step 3: NONE / METADATA_ONLY / CONTENT_AFFECTING.

    Feeds the hypothetical delta into page_impact_assess.assess_product's own
    scoring, exactly as it scores a real knowledge_delta.json, by writing it to
    an isolated scratch knowledge_root's merged/knowledge_delta.json (never the
    real knowledge/ tree) and pointing content_root at the REAL content (read-
    only -- assess_product never writes to content). Returns (classification,
    pia_summary_dict).
    """
    if _delta_is_empty(delta):
        return "NONE", {"HIGH_IMPACT": 0, "MEDIUM_IMPACT": 0, "LOW_IMPACT": 0, "NOT_AFFECTED": 0, "total": 0}

    with tempfile.TemporaryDirectory(prefix="mechanism-sweep-pia-") as scratch:
        scratch_root = Path(scratch)
        delta_path = scratch_root / family / platform / "merged" / "knowledge_delta.json"
        delta_path.parent.mkdir(parents=True, exist_ok=True)
        delta_path.write_text(json.dumps(delta, indent=2, ensure_ascii=False), encoding="utf-8")

        result = page_impact_assess.assess_product(
            family, platform, content_root=content_root, knowledge_root=scratch_root,
        )
        summary = result["summary"]
        if summary.get("HIGH_IMPACT", 0) or summary.get("MEDIUM_IMPACT", 0):
            return "CONTENT_AFFECTING", summary
        return "METADATA_ONLY", summary


def run_sweep(
    since_commit: str,
    language: str,
    *,
    exclude: set[tuple[str, str]] | None = None,
    registry_path: Path = _REGISTRY_PATH,
    phase_state_path: Path = _PHASE_STATE_PATH,
    knowledge_root: Path = _REPO_ROOT / "knowledge",
    content_root: Path = _REPO_ROOT / "content",
) -> dict:
    """Run the full mechanism sweep and return the report dict (does not write
    any file -- see write_sweep_report / main() for that, matching cmd_sweep's
    own split between computing and persisting the report)."""
    candidates = enumerate_candidates(
        language, exclude=exclude, registry_path=registry_path, phase_state_path=phase_state_path,
    )

    none_list: list[dict] = []
    metadata_only: list[dict] = []
    content_affecting: list[dict] = []
    separated_upstream_drift: list[dict] = []
    errors: list[dict] = []

    for candidate in candidates:
        family, platform = candidate["family"], candidate["platform"]
        drift = check_upstream_drift(family, platform, knowledge_root=knowledge_root)
        if drift is not None:
            separated_upstream_drift.append({"family": family, "platform": platform, **drift})
            continue
        try:
            delta = diff_only_rerun(family, platform, knowledge_root=knowledge_root)
            classification, pia_summary = classify_candidate(
                family, platform, delta, content_root=content_root,
            )
        except Exception as exc:  # noqa: BLE001 -- one candidate's failure must not abort the sweep
            errors.append({"family": family, "platform": platform, "error": str(exc)})
            continue

        row = {
            "family": family, "platform": platform,
            "delta": delta, "pia_summary": pia_summary,
        }
        if classification == "NONE":
            none_list.append(row)
        elif classification == "METADATA_ONLY":
            metadata_only.append(row)
        else:
            content_affecting.append(row)

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "since_commit": since_commit,
        "language": language,
        "excluded": sorted(f"{f}/{p}" for f, p in (exclude or set())),
        "candidates_checked": len(candidates),
        "none": none_list,
        "metadata_only": metadata_only,
        "content_affecting": content_affecting,
        "separated_upstream_drift": separated_upstream_drift,
        "errors": errors,
        "summary": {
            "none": len(none_list),
            "metadata_only": len(metadata_only),
            "content_affecting": len(content_affecting),
            "separated_upstream_drift": len(separated_upstream_drift),
            "errors": len(errors),
        },
    }


def _mechanism_id(since_commit: str, language: str) -> str:
    return f"{language}-{since_commit[:8]}"


def render_markdown(report: dict, mechanism_id: str) -> str:
    lines = [
        f"# Mechanism Sweep: {mechanism_id} ({report['generated_at'][:10]})",
        f"Trigger: {report['since_commit']} — {report['language']}",
        f"Candidates checked: {report['candidates_checked']} (excluding {', '.join(report['excluded']) or 'none'})",
        "",
        "## CONTENT_AFFECTING",
    ]
    if report["content_affecting"]:
        for row in report["content_affecting"]:
            n_apis = len(row["delta"]["modified_apis"]) + len(row["delta"]["new_apis"])
            lines.append(f"- {row['family']}/{row['platform']} — {n_apis} class(es) affected")
    else:
        lines.append("- (none)")
    lines.append("")
    lines.append("## METADATA_ONLY")
    if report["metadata_only"]:
        for row in report["metadata_only"]:
            lines.append(f"- {row['family']}/{row['platform']} — metadata-only diff, no published page affected")
    else:
        lines.append("- (none)")
    lines.append("")
    lines.append("## NONE")
    if report["none"]:
        for row in report["none"]:
            lines.append(f"- {row['family']}/{row['platform']} — confirmed no drift")
    else:
        lines.append("- (none)")
    lines.append("")
    lines.append("## Separated upstream-drift findings (routed to change-sweep/backlog, not this sweep)")
    if report["separated_upstream_drift"]:
        for row in report["separated_upstream_drift"]:
            lines.append(f"- {row['family']}/{row['platform']} — {row['reason']}")
    else:
        lines.append("- (none)")
    if report["errors"]:
        lines.append("")
        lines.append("## Errors")
        for row in report["errors"]:
            lines.append(f"- {row['family']}/{row['platform']} — {row['error']}")
    return "\n".join(lines) + "\n"


def write_sweep_report(report: dict, *, report_root: Path = _REPORT_ROOT) -> tuple[Path, Path]:
    mechanism_id = _mechanism_id(report["since_commit"], report["language"])
    date = report["generated_at"][:10]
    report_root.mkdir(parents=True, exist_ok=True)
    json_path = report_root / f"{mechanism_id}-{date}.json"
    md_path = report_root / f"{mechanism_id}-{date}.md"
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    md_path.write_text(render_markdown(report, mechanism_id), encoding="utf-8")
    return json_path, md_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="mechanism_sweep",
        description="Detect already-launched products stale from our own pipeline-code improvements",
    )
    parser.add_argument("--since-commit", required=True, help="Commit SHA that landed the pipeline fix")
    parser.add_argument("--language", required=True, help="Platform/language the fix applies to (e.g. go, rust, cpp)")
    parser.add_argument(
        "--exclude", default="",
        help="Comma-separated family/platform pairs to skip (the product already being worked on)",
    )
    args = parser.parse_args(argv)

    exclude: set[tuple[str, str]] = set()
    for pair in args.exclude.split(","):
        pair = pair.strip()
        if not pair:
            continue
        family, _, platform = pair.partition("/")
        if family and platform:
            exclude.add((family, platform))

    report = run_sweep(args.since_commit, args.language, exclude=exclude)
    json_path, md_path = write_sweep_report(report)
    sys.stderr.write(f"Mechanism sweep report written to {json_path} and {md_path}\n")
    sys.stderr.write(f"Summary: {report['summary']}\n")
    return 1 if report["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
