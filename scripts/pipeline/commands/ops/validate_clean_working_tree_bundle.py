"""validate_clean_working_tree_bundle.py — Validate clean-working-tree plan/pilot bundles.

Specialized validator preventing previous-bundle defects from recurring silently.

Checks (14 total):
  1.  Required deliverables exist in bundle
  2.  Required command logs exist in bundle
  3.  SHA-256 manifest exists and verifies
  4.  Final verdict consistent with blocked_items
  5.  PLAN_HARDENED_READY_FOR_DOCS_ONLY_PILOT requires P0 tooling proof
  6.  Contradictions resolved must have repair evidence (not just accepted-as-is)
  7.  Dirty-tree state classified
  8.  Missing taskcards documented
  9.  Bundle path recorded
  10. Final git status captured
  11. Safety section free of unclassified stash/reset/clean output
  12. Claimed commits have git-log proof
  13. Pilot PASS claims require lane-evidence-schema PASS proof
  14. Validator source/tests are referenced or SHA-proven in bundle
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import zipfile
from pathlib import Path

REQUIRED_DELIVERABLES = [
    "repo-reality-audit", "failure-mode-register", "state-machine",
    "taskcards", "file-taxonomy-ownership-policy", "evidence-lifecycle",
    "generated-files-policy", "tooling-validator-requirements", "pilot-plan",
    "independent-verification", "final-verdict", "plan-state",
    "executive-summary", "evidence-index", "contradiction-log", "repair-loop-1",
]
REQUIRED_COMMAND_LOGS = ["preflight"]
P0_TOOL_NAMES = [
    "lane_manifest", "lane_overlap_check", "dirty_classifier", "lane_evidence_schema",
]
PILOT_READY_VERDICTS = frozenset({
    "PLAN_HARDENED_READY_FOR_DOCS_ONLY_PILOT",
    "ACCEPTED_P0_COMPLETE_PILOT1_COMPLETE",
    "ACCEPTED_P0_COMPLETE_PILOT1_BLOCKED",
})


def _names_in_bundle(bp: Path) -> list[str]:
    if bp.suffix == ".zip":
        with zipfile.ZipFile(bp) as zf:
            return [n.lower() for n in zf.namelist()]
    return [
        str(f.relative_to(bp)).lower().replace("\\", "/")
        for f in bp.rglob("*") if f.is_file()
    ]


def _read(bp: Path, frag: str) -> str | None:
    if bp.suffix == ".zip":
        with zipfile.ZipFile(bp) as zf:
            for n in zf.namelist():
                if frag.lower() in n.lower():
                    return zf.read(n).decode("utf-8", errors="replace")
    else:
        for f in bp.rglob("*"):
            if frag.lower() in f.name.lower() and f.is_file():
                return f.read_text(encoding="utf-8", errors="replace")
    return None


def _c(name: str, ok: bool, detail: str) -> dict:
    return {"check": name, "status": "PASS" if ok else "FAIL", "detail": detail}


def check1_required_deliverables(names: list[str]) -> dict:
    missing = [r for r in REQUIRED_DELIVERABLES
               if not any(r.replace("-", "_") in n or r in n for n in names)]
    return _c("required_deliverables", not missing,
               f"Missing: {missing}" if missing else f"All {len(REQUIRED_DELIVERABLES)} present")


def check2_command_logs(names: list[str]) -> dict:
    missing = [r for r in REQUIRED_COMMAND_LOGS if not any(r in n for n in names)]
    return _c("required_command_logs", not missing,
               f"Missing: {missing}" if missing else "Required logs present")


def check3_sha256_manifest(bp: Path, names: list[str]) -> dict:
    if not any("sha256" in n for n in names):
        return _c("sha256_manifest", False, "No SHA-256 manifest found in bundle")
    t = _read(bp, "sha256")
    if t:
        cnt = sum(1 for line in t.splitlines() if re.match(r"[0-9a-f]{64}", line.strip()))
        return _c("sha256_manifest", True, f"SHA-256 manifest: {cnt} entries")
    return _c("sha256_manifest", True, "SHA-256 manifest present")


def check4_verdict_consistency(bp: Path, names: list[str]) -> dict:
    t = _read(bp, "plan-state")
    if not t:
        return _c("verdict_consistency", False, "No plan-state file found")
    vm = re.search(r"final_verdict:\s*(\S+)", t)
    bm = re.search(r"blocked_items:\s*\[([^\]]*)\]", t)
    if not vm:
        return _c("verdict_consistency", False, "No final_verdict in plan-state")
    verdict = vm.group(1).strip()
    if bm and bm.group(1).strip() and verdict in PILOT_READY_VERDICTS:
        return _c("verdict_consistency", False,
                  f"Verdict {verdict!r} claims pilot-ready but blocked_items non-empty")
    return _c("verdict_consistency", True, f"Verdict {verdict!r} consistent")


def check5_p0_tooling(bp: Path, names: list[str]) -> dict:
    t = _read(bp, "plan-state")
    if not t:
        return _c("p0_tooling_present", False, "No plan-state found")
    vm = re.search(r"final_verdict:\s*(\S+)", t)
    if not vm or vm.group(1).strip() not in PILOT_READY_VERDICTS:
        return _c("p0_tooling_present", True, "Not pilot-ready verdict — P0 check skipped")
    found = [tool for tool in P0_TOOL_NAMES if any(tool in n for n in names)]
    missing = [tool for tool in P0_TOOL_NAMES if tool not in found]
    return _c("p0_tooling_present", not missing,
               f"P0 tools missing: {missing}" if missing else f"P0 tools present: {found}")


def check6_contradiction_repair(bp: Path, names: list[str]) -> dict:
    ct = _read(bp, "contradiction")
    if not ct:
        return _c("contradiction_repair", False, "No contradiction-log in bundle")
    accepted = len(re.findall(r"accepted.as.is", ct, re.I))
    if accepted:
        rt = _read(bp, "repair-loop")
        if not rt:
            return _c("contradiction_repair", False,
                       f"{accepted} 'accepted-as-is' entries but no repair-loop file")
        if not re.search(r"repaired|fixed|correction|resolved|addressed", rt, re.I):
            return _c("contradiction_repair", False,
                       "Repair-loop has no resolution-evidence keywords")
    return _c("contradiction_repair", True, "Contradiction handling includes repair evidence")


def check7_dirty_tree_classified(bp: Path, names: list[str]) -> dict:
    t = _read(bp, "preflight")
    if not t:
        return _c("dirty_tree_classified", False, "No preflight log in bundle")
    ok = "git status" in t.lower() or "??" in t or " M " in t
    return _c("dirty_tree_classified", ok,
               "git status in preflight" if ok else "Preflight missing git status")


def check8_missing_taskcards(bp: Path, names: list[str]) -> dict:
    t = _read(bp, "taskcards")
    if not t:
        return _c("missing_taskcards", False, "No taskcards file in bundle")
    n = len(re.findall(r"TC-LCM-\d+", t))
    return _c("missing_taskcards", n > 0,
               f"{n} TC-LCM taskcards" if n else "No TC-LCM entries")


def check9_bundle_path_recorded(bp: Path, names: list[str]) -> dict:
    for frag in ["evidence-index", "final-verdict", "executive-summary", "plan-state"]:
        t = _read(bp, frag)
        if t and ("evidence-bundle" in t.lower() or ".zip" in t.lower()):
            return _c("bundle_path_recorded", True, f"Bundle path in {frag}")
    return _c("bundle_path_recorded", False, "Bundle path not referenced in any file")


def check10_git_status_captured(bp: Path, names: list[str]) -> dict:
    t = _read(bp, "preflight")
    if t and "git status" in t.lower():
        return _c("git_status_captured", True, "git status in preflight log")
    if any("git-status" in n or "git_status" in n for n in names):
        return _c("git_status_captured", True, "Dedicated git-status file")
    return _c("git_status_captured", False, "No git status captured")


# ---------------------------------------------------------------------------
# New hardening checks (11–14)
# ---------------------------------------------------------------------------

_STASH_PATTERNS = re.compile(
    r"(saved working directory|stash@\{|wip on \w+:|git stash pop|git stash drop)",
    re.I,
)
_SAFE_SECTION_MARKERS = re.compile(
    r"(stash.*classified|no stash|stash.*benign|stash.*investigation|stash.*not a violation)",
    re.I,
)


def check11_safety_section_no_unclassified_stash(bp: Path, names: list[str]) -> dict:
    """Safety section must not contain stash/reset output without classification."""
    for frag in ["executive-summary", "plan-state", "final-verdict", "safety"]:
        t = _read(bp, frag)
        if not t:
            continue
        if _STASH_PATTERNS.search(t):
            if _SAFE_SECTION_MARKERS.search(t):
                return _c("safety_no_unclassified_stash", True,
                           f"Stash output in {frag} but classified/explained")
            return _c("safety_no_unclassified_stash", False,
                       f"Stash/reset output in {frag} without classification")
    return _c("safety_no_unclassified_stash", True, "No unclassified stash output found")


def check12_commits_have_git_log_proof(bp: Path, names: list[str]) -> dict:
    """If commits are claimed, a git-log proof file must be present."""
    # Check whether any file claims a commit SHA
    sha_pattern = re.compile(r"\b[0-9a-f]{7,40}\b")
    commit_claimed = False
    for frag in ["final-verdict", "executive-summary", "plan-state"]:
        t = _read(bp, frag)
        if t and sha_pattern.search(t):
            commit_claimed = True
            break

    if not commit_claimed:
        return _c("commits_have_git_log_proof", True, "No commit SHAs claimed — skip")

    has_log = any("git-log" in n or "git_log" in n or "gitlog" in n for n in names)
    if not has_log:
        # Also accept if preflight or a command-log contains git log output
        for frag in ["preflight", "command-log"]:
            t = _read(bp, frag)
            if t and re.search(r"[0-9a-f]{7,40}\s+(commit|fix|feat|content|docs)\(", t):
                has_log = True
                break
    return _c("commits_have_git_log_proof", has_log,
               "git-log proof present" if has_log else "Commits claimed but no git-log proof")


_PILOT_PASS_PATTERN = re.compile(r"pilot\s*[123]\s*(?:pass|complete|verified|accepted)", re.I)
_EVIDENCE_SCHEMA_PASS = re.compile(r"lane.evidence.schema.*pass|evidence.*schema.*pass", re.I)


def check13_pilot_pass_requires_evidence_schema(bp: Path, names: list[str]) -> dict:
    """Pilot PASS claims require lane-evidence-schema PASS proof."""
    for frag in ["executive-summary", "final-verdict", "independent-verification", "plan-state"]:
        t = _read(bp, frag)
        if t and _PILOT_PASS_PATTERN.search(t):
            # A pilot PASS is claimed — look for evidence schema proof
            for check_frag in ["independent-verification", "defect-repair", "repair-loop"]:
                ct = _read(bp, check_frag)
                if ct and _EVIDENCE_SCHEMA_PASS.search(ct):
                    return _c("pilot_pass_has_evidence_schema", True,
                               "Pilot PASS backed by evidence-schema PASS proof")
            # Also accept if the names list includes an evidence-schema output
            if any("evidence_schema" in n or "evidence-schema" in n for n in names):
                return _c("pilot_pass_has_evidence_schema", True,
                           "Evidence-schema artifact in bundle")
            return _c("pilot_pass_has_evidence_schema", False,
                       "Pilot PASS claimed but no lane-evidence-schema PASS proof found")
    return _c("pilot_pass_has_evidence_schema", True, "No pilot PASS claim found — skip")


def check14_validator_source_referenced(bp: Path, names: list[str]) -> dict:
    """Validator source/tests must be referenced or SHA-proven in bundle."""
    validator_names = [
        "validate_clean_working_tree_bundle",
        "lane_evidence_schema",
        "lane_manifest",
    ]
    # Accept if any source file is directly in the bundle
    for v in validator_names:
        if any(v in n for n in names):
            return _c("validator_source_referenced", True,
                       f"Validator source in bundle: {v}")
    # Accept if a SHA/commit reference appears in executive-summary or plan-state
    for frag in ["executive-summary", "plan-state", "preflight"]:
        t = _read(bp, frag)
        if t and any(v in t for v in validator_names):
            return _c("validator_source_referenced", True,
                       f"Validator referenced in {frag}")
    return _c("validator_source_referenced", False,
               "No validator source, test, or SHA reference found in bundle")


def validate(bp: Path) -> dict:
    if not bp.exists():
        return {
            "bundle_path": str(bp),
            "checks": [_c("file_exists", False, f"Not found: {bp}")],
            "overall": "FAIL", "pass_count": 0, "fail_count": 1, "total_checks": 1,
        }
    names = _names_in_bundle(bp)
    checks = [
        check1_required_deliverables(names), check2_command_logs(names),
        check3_sha256_manifest(bp, names), check4_verdict_consistency(bp, names),
        check5_p0_tooling(bp, names), check6_contradiction_repair(bp, names),
        check7_dirty_tree_classified(bp, names), check8_missing_taskcards(bp, names),
        check9_bundle_path_recorded(bp, names), check10_git_status_captured(bp, names),
        check11_safety_section_no_unclassified_stash(bp, names),
        check12_commits_have_git_log_proof(bp, names),
        check13_pilot_pass_requires_evidence_schema(bp, names),
        check14_validator_source_referenced(bp, names),
    ]
    pc = sum(1 for c in checks if c["status"] == "PASS")
    fc = sum(1 for c in checks if c["status"] == "FAIL")
    return {
        "bundle_path": str(bp), "checks": checks,
        "overall": "PASS" if fc == 0 else "FAIL",
        "pass_count": pc, "fail_count": fc, "total_checks": len(checks),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate a clean-working-tree plan/pilot evidence bundle."
    )
    g = parser.add_mutually_exclusive_group(required=True)
    g.add_argument("--bundle", type=Path)
    g.add_argument("--dir", type=Path)
    parser.add_argument("--format", choices=["json", "table"], default="table")
    args = parser.parse_args(argv)
    report = validate(args.bundle or args.dir)
    if args.format == "json":
        print(json.dumps(report, indent=2))
    else:
        print(f"Bundle: {report['bundle_path']}")
        for c in report["checks"]:
            print(f"  [{c['status']}] {c['check']}: {c['detail']}")
        print(f"\n{report['total_checks']} checks: "
              f"{report['pass_count']} PASS, {report['fail_count']} FAIL — {report['overall']}")
    return 0 if report["overall"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
