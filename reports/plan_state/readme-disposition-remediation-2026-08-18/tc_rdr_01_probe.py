"""TC-RDR-01: portfolio classification probe.

Scratch-only (not a pipeline module). Read-only: never writes to any candidate, disposition file,
or the clone cache. For every non-published DIRTY product in the TC-MICRO-02-01 baseline
(reports/_scratch/mt055_audit_portfolio_baseline_20260818.txt), computes:

  - live content-unit count vs existing content-disposition entry count (the growth signal)
  - remap_match_rate: what fraction of EXISTING disposition entries find a live excerpt match
    (the actual TRUE_DRIFT vs SUBSTANTIAL_GROWTH discriminator -- proven more reliable than raw
    count delta alone by the pilot: a real remap attempt, not just counting)
  - which of its baseline findings are in the disposition-coverage family (this mission's real
    scope) vs the self-citation/merge-verification family (RC-C-adjacent, a different fix) vs
    entirely out-of-family (not this mission's scope at all)

Classification per product:
  TRUE_DRIFT            -- disposition-family findings exist AND remap_match_rate > 0
  SUBSTANTIAL_GROWTH     -- disposition-family findings exist AND remap_match_rate == 0
  NO_DISPOSITION_FAMILY_FINDINGS -- product has no content_unit_disposition_coverage /
                             content_unit_excerpt_matches_extraction /
                             structural_unit_disposition_coverage /
                             code_example_disposition_coverage / badge_disposition_coverage
                             findings at all (its dirty findings are entirely
                             self-citation/merge-verify/out-of-family)
Separately recorded per product (not mutually exclusive with the above):
  self_citation_or_merge_verify_findings: content_unit_evidence_resolves /
                             content_unit_merged_into_target_section counts
  out_of_family_findings: every other check name and its count
"""
import ast
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "scripts" / "pipeline"))

from commands.foss import readme_refresh_run as rrr  # noqa: E402
from commands.foss import readme_refresh_checks as checks  # noqa: E402

BASELINE_PATH = REPO_ROOT / "reports" / "_scratch" / "mt055_audit_portfolio_baseline_20260818.txt"

DISPOSITION_FAMILY = {
    "content_unit_disposition_coverage",
    "content_unit_excerpt_matches_extraction",
    "structural_unit_disposition_coverage",
    "code_example_disposition_coverage",
    "badge_disposition_coverage",
}
SELF_CITATION_OR_MERGE_VERIFY = {
    "content_unit_evidence_resolves",
    "content_unit_merged_into_target_section",
}


def parse_baseline() -> dict:
    """Return {family/platform: {check: count}} for non-published DIRTY products only."""
    products = {}
    for line in BASELINE_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line.startswith("DIRTY "):
            continue
        if "[published]" in line:
            continue
        rest = line[len("DIRTY "):]
        fam_plat, _, findings_str = rest.partition(": ")
        fam_plat = fam_plat.strip()
        findings = ast.literal_eval(findings_str)
        products[fam_plat] = findings
    return products


def _match_rate(live_keyed: dict, disp_entries: list, disp_key: str) -> "tuple[int, int, float | None]":
    matched = 0
    for entry in disp_entries:
        norm = checks._normalize_for_drop_match(entry.get(disp_key) or "")
        if len(live_keyed.get(norm, [])) >= 1:
            matched += 1
    rate = round(matched / len(disp_entries), 3) if disp_entries else None
    return matched, len(disp_entries), rate


def probe_one(family: str, platform: str) -> dict:
    clone_cache = rrr._product_clone_cache(family, platform)
    old_readme = clone_cache / "README.md"
    result = {"family": family, "platform": platform}
    if not old_readme.is_file():
        result["error"] = f"old README not found at {old_readme}"
        return result

    old_text = old_readme.read_text(encoding="utf-8")

    # Content units (identity: excerpt text)
    content_live = checks.extract_old_readme_content_units(old_text)
    content_live_by_norm = {}
    for u in content_live:
        norm = checks._normalize_for_drop_match(u.get("excerpt") or "")
        content_live_by_norm.setdefault(norm, []).append(u["unit_id"])
    content_disp_path = rrr._content_dispositions_path(family, platform)
    content_disp = json.loads(content_disp_path.read_text(encoding="utf-8")) if content_disp_path.is_file() else []
    c_matched, c_total, c_rate = _match_rate(content_live_by_norm, content_disp, "excerpt")

    # Structural units (identity: heading text, not excerpt)
    struct_live = checks.extract_old_readme_structural_units(old_text)
    struct_live_by_norm = {}
    for u in struct_live:
        norm = checks._normalize_for_drop_match(u.get("heading") or "")
        struct_live_by_norm.setdefault(norm, []).append(u["unit_id"])
    struct_disp_path = rrr._structure_dispositions_path(family, platform)
    struct_disp = json.loads(struct_disp_path.read_text(encoding="utf-8")) if struct_disp_path.is_file() else []
    s_matched, s_total, s_rate = _match_rate(struct_live_by_norm, struct_disp, "heading")

    # Code-example units: no separate excerpt field on the disposition side confirmed here --
    # use simple count comparison (live count vs disposition count) as the coverage signal;
    # a product whose code-example-dispositions.json is entirely missing/empty is unambiguous.
    code_live = checks.extract_old_readme_code_units(old_text)
    code_disp_path = rrr._code_example_dispositions_path(family, platform)
    code_disp = json.loads(code_disp_path.read_text(encoding="utf-8")) if code_disp_path.is_file() else []

    result.update({
        "content_live_count": len(content_live), "content_disp_count": c_total,
        "content_matched": c_matched, "content_match_rate": c_rate,
        "structural_live_count": len(struct_live), "structural_disp_count": s_total,
        "structural_matched": s_matched, "structural_match_rate": s_rate,
        "code_live_count": len(code_live), "code_disp_count": len(code_disp),
    })
    return result


TRUE_DRIFT_THRESHOLD = 0.5  # below this, one coincidental match is noise, not "mostly intact drift"


def _family_status(findings: dict, check_name: str, live_count: int, disp_count: int,
                    match_rate) -> str:
    if check_name not in findings:
        return "NOT_APPLICABLE"
    if disp_count == 0 and live_count > 0:
        return "NEVER_AUTHORED"
    if match_rate is not None and match_rate >= TRUE_DRIFT_THRESHOLD:
        return "TRUE_DRIFT"
    return "SUBSTANTIAL_GROWTH_OR_STALE"


def main() -> int:
    baseline = parse_baseline()
    out = {}
    for fam_plat, findings in sorted(baseline.items()):
        family, platform = fam_plat.split("/")
        disp_family_findings = {k: v for k, v in findings.items() if k in DISPOSITION_FAMILY}
        scm_findings = {k: v for k, v in findings.items() if k in SELF_CITATION_OR_MERGE_VERIFY}
        out_of_family_findings = {
            k: v for k, v in findings.items()
            if k not in DISPOSITION_FAMILY and k not in SELF_CITATION_OR_MERGE_VERIFY
        }

        probe = probe_one(family, platform)

        content_engaged = (
            "content_unit_excerpt_matches_extraction" in findings
            or "content_unit_disposition_coverage" in findings
        )
        content_status = _family_status(
            {"content": 1} if content_engaged else {}, "content",
            probe.get("content_live_count", 0), probe.get("content_disp_count", 0),
            probe.get("content_match_rate"),
        )
        structural_status = _family_status(
            findings, "structural_unit_disposition_coverage",
            probe.get("structural_live_count", 0), probe.get("structural_disp_count", 0),
            probe.get("structural_match_rate"),
        )
        if "code_example_disposition_coverage" not in findings:
            code_status = "NOT_APPLICABLE"
        elif probe.get("code_disp_count", 0) == 0 and probe.get("code_live_count", 0) > 0:
            code_status = "NEVER_AUTHORED"
        else:
            code_status = "SUBSTANTIAL_GROWTH_OR_STALE (count-based heuristic only, not "
            code_status += "content-matched)"
        badge_status = "NEVER_AUTHORED_OR_STALE" if "badge_disposition_coverage" in findings else "NOT_APPLICABLE"

        family_statuses = {
            "content": content_status, "structural": structural_status,
            "code_example": code_status, "badge": badge_status,
        }
        engaged = {k: v for k, v in family_statuses.items() if v != "NOT_APPLICABLE"}
        if not disp_family_findings:
            overall = "NO_DISPOSITION_FAMILY_FINDINGS"
        elif all(v == "TRUE_DRIFT" for v in engaged.values()):
            overall = "TRUE_DRIFT"
        elif any(v == "TRUE_DRIFT" for v in engaged.values()):
            overall = "MIXED"
        else:
            overall = "COMPOSE_REQUIRED"

        out[fam_plat] = {
            "overall": overall,
            "family_statuses": family_statuses,
            "disposition_family_findings": disp_family_findings,
            "self_citation_or_merge_verify_findings": scm_findings,
            "out_of_family_findings": out_of_family_findings,
            "probe": probe,
        }
        print(f"{fam_plat}: {overall}  families={family_statuses}")

    out_path = Path(__file__).resolve().parent / "tc_rdr_01_classification.json"
    out_path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"\nWritten: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
