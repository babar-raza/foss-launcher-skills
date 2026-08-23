"""page_impact_matrix.py -- composed, read-only cross-surface impact report
for one refresh run.

Mission plan: mission-plan-the-end-to-end-vast-hejlsberg.md, Task 2 (S9.1,
closes G7). Joins eight already-existing artifacts into one per-run report
at ``reports/refresh_review/{family}/{platform}/page_impact_matrix.json``
(+ a rendered ``.md``) -- this is deliberately a COMPOSED VIEW, not a new
source of truth: the mission's own F1 finding (a hand-typed products-page
sentence drifted independently of the working shortcode system) is the
reason a second place claiming to hold truth is exactly the failure mode to
avoid here. Every field below is read from an artifact some other script
already owns and writes; this module never originates data, only joins it.

Ground-truth schemas for all eight inputs were confirmed by direct code read
(not docstring/assumption) before this module was written -- see this
mission's own plan file, Task 2's implementation note, for the full survey
and the five real divergences it caught (site_plan.yaml lives under
reports/plans/, not reports/refresh_review/; two differently-named
"page decisions" files exist and only the run-scoped .jsonl one is correct
here; scripts/pipeline/lib/triage_confirm.py is the real script, not the
commands/ops/ path a stale doc once implied; manifest.json has no
"bound_commit" field, the real name is base_commit_sha; knowledge_delta.json's
list fields are plain strings, not objects).

Inputs (per {family}/{platform}, or per {family}/{platform}/{run_id} where noted):
  1. knowledge/{family}/{platform}/merged/knowledge_delta.json
  2. reports/refresh_review/{family}/{platform}/semantic_changes.json
  3. reports/refresh_review/{family}/{platform}/page_impact.json
  4. reports/plans/{family}/{platform}/site_plan.yaml               (read, not required)
  5. reports/refresh_runs/{family}/{platform}/{run_id}/page_decisions.jsonl
  6. reports/refresh_review/{family}/{platform}/triage_verdict.yaml
  7. data/package_registry.json  (data[family][platform].verification.published)
  8. reports/refresh_runs/{family}/{platform}/{run_id}/manifest.json
     + reports/refresh_review/{family}/{platform}/oracle_verdicts/*.yaml

Output columns (exact, per the mission plan's SS12): release_delta_item,
evidence_source, change_classification, affected_surface, affected_repo_page,
required_action, reason_for_no_change, validator_test, publication_dependency,
final_evidence, plus prose_updated/code_updated (SS9.6b).

Honest, stated limitation on prose_updated/code_updated (SS9.6b): no artifact
in this pipeline persists a code-fence-specific before/after diff -- receipts
carry content hashes, not content itself, and body_refresh.py's own execution
never stores the actual old/new bodies past the run. prose_updated is a real,
grounded signal (disposition + body_hash_before != body_hash_after).
code_updated is best-effort: "true" only when the page's own receipt
strategy_used implies a full regeneration (REFERENCE_REGENERATION always
rewrites code examples); otherwise "unknown", never a guessed False -- an
honest "not determined" is preferable to a silently wrong boolean, matching
this mission's own no-overclaiming standard. Closing this gap for real is
Task 21's territory (body_refresh.py code-block re-pull audit), not this
module's.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

_PIPELINE_ROOT = Path(__file__).resolve().parents[2]
if str(_PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_ROOT))

from core.fs import atomic_write  # noqa: E402

try:
    import yaml
except ImportError:  # pragma: no cover -- PyYAML is a real repo dependency
    yaml = None  # type: ignore[assignment]

_DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[4]
_repo_root = _DEFAULT_REPO_ROOT


def configure(*, repo_root: "Path | str | None" = None) -> None:
    """Override the repo-root seam for tests; call with no arguments to reset."""
    global _repo_root
    _repo_root = Path(repo_root) if repo_root is not None else _DEFAULT_REPO_ROOT


# ---------------------------------------------------------------------------
# Widened required_action vocabulary (SS9.7, corrected -- "redirect" dropped,
# it has no producing mechanism anywhere in this plan; SS9.5 is retire+unlink
# only). "deprecate" has no real producer yet either (Task 15/G9 -- extraction
# never carries a deprecated signal today) but the value is reserved here so
# nothing downstream needs to change shape once Task 15 lands one.
# ---------------------------------------------------------------------------
_DISPOSITION_TO_ACTION: dict[str, str] = {
    "GENERATED": "add",
    "BODY_UPDATED": "update",
    "EVIDENCE_ONLY": "update",
    "RETIRED": "remove",
    "NOT_AFFECTED": "no_change",
    "SKIPPED": "preserve",
    "ADDED": "add",
    "BLOCKED": "no_change",  # surfaced via reason_for_no_change, not silently dropped
}

_DELTA_LIST_FIELDS = (
    "new_claims", "removed_claims", "modified_claims",
    "new_apis", "removed_apis", "modified_apis", "resurrected_apis",
)


def _load_json(path: Path) -> "dict | list | None":
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _load_yaml(path: Path) -> "dict | None":
    if not path.is_file() or yaml is None:
        return None
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except (yaml.YAMLError, OSError):  # type: ignore[union-attr]
        return None


def _load_jsonl(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


# ---------------------------------------------------------------------------
# Per-artifact loaders (artifact numbers match this module's own docstring)
# ---------------------------------------------------------------------------

def load_knowledge_delta(family: str, platform: str) -> "dict | None":
    """Artifact 1."""
    return _load_json(
        _repo_root / "knowledge" / family / platform / "merged" / "knowledge_delta.json"
    )


def load_semantic_changes(family: str, platform: str) -> list[dict]:
    """Artifact 2."""
    data = _load_json(
        _repo_root / "reports" / "refresh_review" / family / platform / "semantic_changes.json"
    )
    return data if isinstance(data, list) else []


def load_page_impact(family: str, platform: str) -> "dict | None":
    """Artifact 3."""
    return _load_json(
        _repo_root / "reports" / "refresh_review" / family / platform / "page_impact.json"
    )


def load_site_plan(family: str, platform: str) -> "dict | None":
    """Artifact 4 -- reports/plans/, NOT reports/refresh_review/ (confirmed
    divergence from a naive path guess -- see module docstring)."""
    return _load_yaml(
        _repo_root / "reports" / "plans" / family / platform / "site_plan.yaml"
    )


def load_page_decisions(run_root: Path) -> list[dict]:
    """Artifact 5 -- the RUN-SCOPED page_decisions.jsonl under the run's own
    directory, NOT reports/refresh_review/{family}/{platform}/page_decisions.json
    (no "l") which is a completely different, product-level aggregate file
    owned by refresh_review.py. Confirmed distinct by direct code read."""
    return _load_jsonl(run_root / "page_decisions.jsonl")


def load_triage_verdict(family: str, platform: str) -> "dict | None":
    """Artifact 6."""
    return _load_yaml(
        _repo_root / "reports" / "refresh_review" / family / platform / "triage_verdict.yaml"
    )


def load_publication_status(family: str, platform: str) -> "bool | None":
    """Artifact 7 -- data[family][platform].verification.published. Returns
    None (not False) when the registry has no entry for this product at all,
    so callers can distinguish "confirmed unpublished" from "no data"."""
    data = _load_json(_repo_root / "data" / "package_registry.json")
    if not isinstance(data, dict):
        return None
    entry = data.get(family, {}).get(platform) if isinstance(data.get(family), dict) else None
    if not isinstance(entry, dict):
        return None
    verification = entry.get("verification")
    if not isinstance(verification, dict):
        return None
    return verification.get("published")


def load_manifest(run_root: Path) -> "dict | None":
    """Artifact 8a."""
    return _load_json(run_root / "manifest.json")


def load_oracle_verdicts(family: str, platform: str) -> dict[str, dict]:
    """Artifact 8b -- one file per page under oracle_verdicts/*.yaml, keyed by
    the page_path field INSIDE each file (not by re-deriving the writer's own
    slug+hash filename scheme, which is fragile to depend on from outside).
    Returns {page_path: verdict_dict}."""
    verdicts_dir = _repo_root / "reports" / "refresh_review" / family / platform / "oracle_verdicts"
    result: dict[str, dict] = {}
    if not verdicts_dir.is_dir():
        return result
    for path in sorted(verdicts_dir.glob("*.yaml")):
        doc = _load_yaml(path)
        if not isinstance(doc, dict):
            continue
        verdict = doc.get("refresh_oracle_verdict")
        if isinstance(verdict, dict) and verdict.get("page_path"):
            result[verdict["page_path"]] = verdict
    return result


def load_receipt(run_root: Path, receipt_ref: "str | None") -> "dict | None":
    """receipt_ref is relative to run_root, not repo-root (confirmed)."""
    if not receipt_ref:
        return None
    doc = _load_yaml(run_root / receipt_ref)
    if not isinstance(doc, dict):
        return None
    receipt = doc.get("content_refresh_receipt")
    return receipt if isinstance(receipt, dict) else None


# ---------------------------------------------------------------------------
# Cross-referencing: which release-delta item(s) does a page's cited evidence
# actually correspond to?
# ---------------------------------------------------------------------------

def _match_delta_items(
    evidence_claims: list[str],
    evidence_apis: list[str],
    knowledge_delta: "dict | None",
    semantic_changes: list[dict],
) -> list[dict]:
    """Return the subset of knowledge_delta.json's changed IDs (claims + APIs)
    that this page actually cites, each enriched with semantic_changes.json's
    richer classification when a matching symbol entry exists there too.

    knowledge_delta.json's own lists are plain ID strings (confirmed -- see
    module docstring); semantic_changes.json's `symbol` field is the same
    class-name/claim-id string, so a direct string match joins the two
    without needing a shared key to be invented.
    """
    cited = set(evidence_claims) | set(evidence_apis)
    if not cited:
        return []

    changed_ids: set[str] = set()
    delta_field_by_id: dict[str, str] = {}
    if isinstance(knowledge_delta, dict):
        for field in _DELTA_LIST_FIELDS:
            for item_id in knowledge_delta.get(field, []) or []:
                if isinstance(item_id, str):
                    changed_ids.add(item_id)
                    delta_field_by_id.setdefault(item_id, field)

    matched_ids = cited & changed_ids
    if not matched_ids:
        return []

    semantic_by_symbol: dict[str, dict] = {
        c["symbol"]: c for c in semantic_changes if isinstance(c, dict) and c.get("symbol")
    }

    matches = []
    for item_id in sorted(matched_ids):
        sc = semantic_by_symbol.get(item_id)
        matches.append({
            "id": item_id,
            "delta_field": delta_field_by_id.get(item_id),
            "change_type": sc.get("change_type") if sc else None,
            "confidence": sc.get("confidence") if sc else None,
        })
    return matches


def _prose_and_code_flags(decision_row: dict, receipt: "dict | None") -> tuple[bool, str]:
    """See module docstring's "Honest, stated limitation" section."""
    hash_changed = (
        decision_row.get("body_hash_before") != decision_row.get("body_hash_after")
    )
    disposition = decision_row.get("disposition")
    prose_updated = hash_changed and disposition in {"BODY_UPDATED", "GENERATED", "EVIDENCE_ONLY"}

    if not prose_updated:
        code_updated = "false"
    elif receipt and receipt.get("strategy_used") == "REFERENCE_REGENERATION":
        code_updated = "true"
    else:
        code_updated = "unknown"
    return prose_updated, code_updated


def _publication_dependency(surface: str, published: "bool | None") -> "str | None":
    """Only docs/products pages render a live install command from
    package_registry.json via the maven-coord/maven-gav shortcodes (confirmed
    working mechanism, F1/F9) -- other surfaces have no such dependency."""
    if surface not in {"docs", "products"}:
        return None
    if published is None:
        return "unknown (no package_registry.json entry for this product)"
    return "published" if published else "unpublished"


def _reason_for_no_change(page_path: str, triage_verdict: "dict | None", matched: list[dict]) -> "str | None":
    if matched:
        return None
    for result in (triage_verdict or {}).get("results", []) if triage_verdict else []:
        if result.get("page_path") == page_path:
            reasons = result.get("reasons")
            if reasons:
                return "; ".join(str(r) for r in reasons)
            return f"triage verdict: {result.get('verdict', 'unknown')}"
    return "no cited claim/API in this page's evidence matches a changed item in this run's delta"


def _final_evidence(manifest: "dict | None", page_path: str, oracle_verdicts: dict[str, dict]) -> str:
    oracle = oracle_verdicts.get(page_path)
    oracle_part = f"oracle={oracle['verdict']}" if oracle else "oracle=not_run"
    if not manifest:
        return f"PENDING (no manifest); {oracle_part}"
    state = manifest.get("state")
    commit_sha = manifest.get("commit_sha")
    if state == "COMMITTED" and commit_sha:
        return f"COMMITTED at {commit_sha}; {oracle_part}"
    return f"PENDING (run state={state}); {oracle_part}"


# ---------------------------------------------------------------------------
# Composition
# ---------------------------------------------------------------------------

def build_matrix(family: str, platform: str, run_id: str) -> dict[str, Any]:
    """Build the full matrix dict for one run. Read-only: never writes to any
    of the eight source artifacts, only reads them."""
    run_root = _repo_root / "reports" / "refresh_runs" / family / platform / run_id

    knowledge_delta = load_knowledge_delta(family, platform)
    semantic_changes = load_semantic_changes(family, platform)
    page_impact = load_page_impact(family, platform)
    triage_verdict = load_triage_verdict(family, platform)
    published = load_publication_status(family, platform)
    manifest = load_manifest(run_root)
    oracle_verdicts = load_oracle_verdicts(family, platform)
    decisions = load_page_decisions(run_root)

    pia_by_path = {
        p["path"]: p for p in (page_impact or {}).get("pages", []) if isinstance(p, dict)
    }

    rows = []
    for row in decisions:
        page_path = row.get("page_path")
        surface = row.get("surface")
        disposition = row.get("disposition")
        evidence_claims = row.get("evidence_claims_checked") or []
        evidence_apis = row.get("evidence_apis_checked") or []

        matched = _match_delta_items(evidence_claims, evidence_apis, knowledge_delta, semantic_changes)
        receipt = load_receipt(run_root, row.get("receipt_ref"))
        prose_updated, code_updated = _prose_and_code_flags(row, receipt)
        required_action = _DISPOSITION_TO_ACTION.get(disposition, "no_change")

        pia_entry = pia_by_path.get(page_path)

        validator_results = row.get("validator_results") or {}
        oracle = oracle_verdicts.get(page_path)
        validator_test_parts = [f"{k}={v}" for k, v in validator_results.items()]
        if oracle:
            validator_test_parts.append(f"oracle={oracle.get('verdict')}")
        if disposition == "BLOCKED":
            validator_test_parts.append("run_gate=BLOCKED")

        rows.append({
            "release_delta_item": [m["id"] for m in matched] or None,
            "evidence_source": (evidence_claims + evidence_apis) or None,
            "change_classification": [m["change_type"] for m in matched if m["change_type"]] or None,
            "affected_surface": surface,
            "affected_repo_page": page_path,
            "required_action": required_action,
            "reason_for_no_change": (
                _reason_for_no_change(page_path, triage_verdict, matched)
                if required_action in {"no_change", "preserve"} else None
            ),
            "validator_test": "; ".join(validator_test_parts) or None,
            "publication_dependency": _publication_dependency(surface, published),
            "final_evidence": _final_evidence(manifest, page_path, oracle_verdicts),
            "prose_updated": prose_updated,
            "code_updated": code_updated,
            "pia_score": pia_entry.get("pia_score") if pia_entry else None,
        })

    incomplete_rows = [
        r["affected_repo_page"] for r in rows
        if r["required_action"] not in {"add", "update", "remove"} and not r["reason_for_no_change"]
    ]

    return {
        "schema_version": 1,
        "family": family,
        "platform": platform,
        "run_id": run_id,
        "generated_at": manifest.get("updated_at") if manifest else None,
        "run_state": manifest.get("state") if manifest else None,
        "knowledge_current_sha": (knowledge_delta or {}).get("current_sha"),
        "row_count": len(rows),
        "incomplete_row_count": len(incomplete_rows),
        "incomplete_rows": incomplete_rows,
        "rows": rows,
    }


def render_markdown(matrix: dict[str, Any]) -> str:
    lines = [
        f"# Page-Impact Matrix -- {matrix['family']}/{matrix['platform']} ({matrix['run_id']})",
        "",
        f"Run state: {matrix.get('run_state')}  |  Knowledge SHA: {matrix.get('knowledge_current_sha')}",
        f"Rows: {matrix['row_count']}  |  Incomplete (no action, no reason): {matrix['incomplete_row_count']}",
        "",
        "| Page | Surface | Action | Delta item(s) | Classification | Prose | Code | Validators | Final evidence |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for r in matrix["rows"]:
        delta_items = ", ".join(r["release_delta_item"]) if r["release_delta_item"] else "-"
        classification = ", ".join(r["change_classification"]) if r["change_classification"] else "-"
        action = r["required_action"]
        if r["reason_for_no_change"]:
            action = f"{action} ({r['reason_for_no_change']})"
        lines.append(
            f"| {r['affected_repo_page']} | {r['affected_surface']} | {action} | "
            f"{delta_items} | {classification} | {r['prose_updated']} | {r['code_updated']} | "
            f"{r['validator_test'] or '-'} | {r['final_evidence']} |"
        )
    if matrix["incomplete_rows"]:
        lines += ["", "## Incomplete rows (no required_action justification)", ""]
        lines += [f"- {p}" for p in matrix["incomplete_rows"]]
    return "\n".join(lines) + "\n"


def write_matrix_report(family: str, platform: str, run_id: str) -> tuple[Path, Path]:
    """Build the matrix and write both the .json and rendered .md. Returns
    (json_path, md_path)."""
    matrix = build_matrix(family, platform, run_id)
    out_dir = _repo_root / "reports" / "refresh_review" / family / platform
    json_path = out_dir / "page_impact_matrix.json"
    md_path = out_dir / "page_impact_matrix.md"
    atomic_write(json_path, json.dumps(matrix, indent=2, ensure_ascii=False) + "\n")
    atomic_write(md_path, render_markdown(matrix))
    return json_path, md_path


def matrix_digest(json_path: Path) -> "str | None":
    if not json_path.is_file():
        return None
    return "sha256:" + hashlib.sha256(json_path.read_bytes()).hexdigest()


def main(argv: "list[str] | None" = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--family", required=True)
    parser.add_argument("--platform", required=True)
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args(argv)

    json_path, md_path = write_matrix_report(args.family, args.platform, args.run_id)
    print(f"json={json_path}")
    print(f"md={md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
