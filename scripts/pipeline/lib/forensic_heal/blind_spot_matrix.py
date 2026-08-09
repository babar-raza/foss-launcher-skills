"""CONTRACT: manual-vs-system blind-spot comparison matrix for S-122 (blind-spot-audit),
Wave 3 of MISSION MT025-2026-08-08-FORENSIC-BLIND-SPOT-HEAL-SKILLS.

Purpose: join the unaided-review findings (FND-*, produced during S-122's INSIDE window)
against the system-tooling findings (SFND-*, produced during the POST window after seal())
on a shared identity key, classify each joined row, and compute a system_recall metric.
This is the core deliverable that makes "where is our tooling blind" a measured number
instead of an impression.

Identity key: (family, platform, page, issue_type). `page` is a free-text location
descriptor (a single page path, or an aggregate like "134 reference pages" / "h01+h02
H-gates") -- it does not need to resolve to a real file, only to be used CONSISTENTLY by
both the unaided and system passes for the same underlying issue. `issue_type` MUST come
from a bounded vocabulary (ISSUE_TYPE_VOCABULARY below) or the finding is routed to
`unclassified_issue_types` and excluded from the rate calculations, rather than silently
degrading the join -- see build_comparison_matrix()'s docstring.

Classification (per plan typed-snuggling-peach.md):
    BOTH          -- same key present in both unaided and system findings, same polarity
    UNAIDED_ONLY  -- key found only by the unaided pass (a real blind spot -- the system
                     missed something a careful reader caught)
    SYSTEM_ONLY   -- key found only by system tooling (either a genuine system catch the
                     unaided pass missed, or a system false positive -- root-cause analysis,
                     Wave 3's next module, decides which)
    CONTRADICTORY -- same key, opposite polarity (system says PASS, unaided says FAIL, or
                     vice versa) -- the highest-severity class, since it means the two
                     passes actively disagree about the same unit rather than one simply
                     not having looked

Seeded from the real 2026-06-17 hand-run's observed issue_type vocabulary
(.local/evidences/foss-manual-system-heal-v2-20260617/06-comparison/
manual-vs-system-comparison-matrix.csv) -- see test_blind_spot_matrix.py for the golden-
fixture replay proving this module reproduces that run's own per-row classifications.
"""
from __future__ import annotations

from typing import Any

# Seeded from the real v2 run's 06-comparison/manual-vs-system-comparison-matrix.csv, plus
# a few evident categories from other phase docs. An issue_type outside this set does not
# silently fall out of the matrix -- see build_comparison_matrix()'s unclassified_issue_types.
ISSUE_TYPE_VOCABULARY: "frozenset[str]" = frozenset({
    "private_import_notice", "wrong_import_path", "empty_description_cells",
    "property_access_wrong", "unknown_class_stdlib", "broken_internal_link",
    "clean_regen", "stale_evidence", "hgate_conditional", "hgate_format_mismatch",
})

_VALID_VERDICTS = ("FAIL", "PASS")


def _key(finding: dict) -> tuple:
    return (finding["family"], finding["platform"], finding["page"], finding["issue_type"])


def _validate_finding(finding: dict, *, side: str) -> "list[str]":
    errors = []
    for field in ("finding_id", "family", "platform", "page", "issue_type"):
        if not finding.get(field):
            errors.append(f"{side} finding missing required field '{field}': {finding!r}")
    verdict = finding.get("verdict", "FAIL")
    if verdict not in _VALID_VERDICTS:
        errors.append(f"{side} finding {finding.get('finding_id')!r} has invalid verdict {verdict!r}")
    return errors


def build_comparison_matrix(unaided_findings: "list[dict]", system_findings: "list[dict]") -> dict:
    """Join unaided vs system findings on (family, platform, page, issue_type).

    Each input finding dict requires: finding_id, family, platform, page, issue_type, and
    an optional verdict ("FAIL", the default -- a finding IS a reported problem -- or
    "PASS", for a system tool explicitly confirming a unit is clean, which is what makes
    CONTRADICTORY detectable).

    Returns:
        {
          "rows": [{"key": {...}, "classification": "BOTH"|"UNAIDED_ONLY"|"SYSTEM_ONLY"|
                    "CONTRADICTORY", "unaided_finding_ids": [...], "system_finding_ids": [...]}],
          "unclassified_issue_types": [...],   # findings outside ISSUE_TYPE_VOCABULARY,
                                                 # excluded from rows/rates, reported not dropped
          "orphan_finding_ids": [...],          # completeness assertion -- always [] by
                                                 # construction; a non-empty list is a bug
          "counts": {"BOTH": n, "UNAIDED_ONLY": n, "SYSTEM_ONLY": n, "CONTRADICTORY": n},
          "system_recall": float,   # BOTH / (BOTH + UNAIDED_ONLY), None if that denominator is 0
        }

    Raises ValueError (not a silent drop) if any finding is missing a required field or
    has an invalid verdict -- a malformed input finding is a bug in the phase that produced
    it, not something this joiner should paper over.
    """
    errors: "list[str]" = []
    for f in unaided_findings:
        errors.extend(_validate_finding(f, side="unaided"))
    for f in system_findings:
        errors.extend(_validate_finding(f, side="system"))
    if errors:
        raise ValueError(f"{len(errors)} invalid finding(s): {errors[:5]}")

    unclassified: "list[dict]" = []
    grouped: "dict[tuple, dict[str, list[dict]]]" = {}
    accounted_ids: "set[str]" = set()

    for side_name, findings in (("unaided", unaided_findings), ("system", system_findings)):
        for f in findings:
            if f["issue_type"] not in ISSUE_TYPE_VOCABULARY:
                unclassified.append(f)
                continue
            key = _key(f)
            bucket = grouped.setdefault(key, {"unaided": [], "system": []})
            bucket[side_name].append(f)

    rows: "list[dict]" = []
    counts = {"BOTH": 0, "UNAIDED_ONLY": 0, "SYSTEM_ONLY": 0, "CONTRADICTORY": 0}

    for key, bucket in grouped.items():
        unaided_side = bucket["unaided"]
        system_side = bucket["system"]
        for f in unaided_side + system_side:
            accounted_ids.add(f["finding_id"])

        if unaided_side and system_side:
            unaided_verdicts = {f.get("verdict", "FAIL") for f in unaided_side}
            system_verdicts = {f.get("verdict", "FAIL") for f in system_side}
            if unaided_verdicts != system_verdicts:
                classification = "CONTRADICTORY"
            else:
                classification = "BOTH"
        elif unaided_side:
            classification = "UNAIDED_ONLY"
        else:
            classification = "SYSTEM_ONLY"

        counts[classification] += 1
        rows.append({
            "key": {"family": key[0], "platform": key[1], "page": key[2], "issue_type": key[3]},
            "classification": classification,
            "unaided_finding_ids": [f["finding_id"] for f in unaided_side],
            "system_finding_ids": [f["finding_id"] for f in system_side],
        })

    all_input_ids = {f["finding_id"] for f in unaided_findings} | {f["finding_id"] for f in system_findings}
    unclassified_ids = {f["finding_id"] for f in unclassified}
    orphan_ids = sorted(all_input_ids - accounted_ids - unclassified_ids)

    denom = counts["BOTH"] + counts["UNAIDED_ONLY"]
    system_recall = (counts["BOTH"] / denom) if denom else None

    return {
        "rows": rows,
        "unclassified_issue_types": unclassified,
        "orphan_finding_ids": orphan_ids,
        "counts": counts,
        "system_recall": system_recall,
    }
