#!/usr/bin/env python3
"""Stage 8 — Readiness Scorecard for launch-product orchestration.

Collects per-subdomain translation coverage and content grades,
then prints a READY TO SHIP / NOT READY verdict.

Translation coverage is reported informationally but does not block the verdict.

Usage:
    python scripts/pipeline/commands/launch/readiness_scorecard.py --family slides --platform python
    python scripts/pipeline/commands/launch/readiness_scorecard.py --family slides --platform python --set-checkpoint
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

_DEFAULT_ROOT = Path(__file__).resolve().parents[4]
_ROOT = _DEFAULT_ROOT
_CONTENT = _ROOT / "content"
_PHASE_STATE = _ROOT / "reports" / "phase_state.json"


def configure(*, repo_root: "Path | str | None" = None) -> None:
    """Override module-level path constants for testing."""
    global _ROOT, _CONTENT, _PHASE_STATE
    _ROOT = Path(repo_root) if repo_root is not None else _DEFAULT_ROOT
    _CONTENT = _ROOT / "content"
    _PHASE_STATE = _ROOT / "reports" / "phase_state.json"

_SUBDOMAINS = ["products.aspose.org", "docs.aspose.org", "kb.aspose.org",
               "reference.aspose.org", "blog.aspose.org"]

_HGATES = ["h01", "h02", "h03", "h04", "h05"]
_HGATE_NAMES = {
    "h01": "Human prose review",
    "h02": "Reference accuracy",
    "h03": "Format table spot-check",
    "h04": "Link validation",
    "h05": "License accuracy",
}

_LOCALES = [
    "ar", "bg", "ca", "cs", "da", "de", "el", "es", "fa", "fi",
    "fr", "he", "hi", "hr", "hu", "id", "it", "ja", "ko", "lt",
    "lv", "ms", "nl", "no", "pl", "pt", "ro", "ru", "sk", "sr",
    "sv", "th", "tr", "uk", "vi", "zh",
]



def _count_locale_coverage(site: str, family: str, platform: str) -> dict:
    """Count how many of the 36 locales have at least one translated file."""
    site_root = _CONTENT / site
    locales_present = set()
    total_files = 0

    if site == "blog.aspose.org":
        # Blog: content/blog.aspose.org/{family}/{platform}/{post}/index.{locale}.md
        blog_root = site_root / family / platform
        if blog_root.is_dir():
            for md in blog_root.rglob("index.*.md"):
                # Extract locale from index.{locale}.md
                m = re.match(r"index\.([a-z]{2})\.md$", md.name)
                if m and m.group(1) in _LOCALES:
                    locales_present.add(m.group(1))
                    total_files += 1
    else:
        # Standard: content/{site}/{locale}/{family}/{platform}/
        for locale in _LOCALES:
            locale_dir = site_root / locale / family / platform
            if locale_dir.is_dir():
                files = list(locale_dir.rglob("*.md"))
                if files:
                    locales_present.add(locale)
                    total_files += len(files)

    return {
        "locales_present": len(locales_present),
        "total_locales": len(_LOCALES),
        "coverage": len(locales_present) / len(_LOCALES) if _LOCALES else 0,
        "total_files": total_files,
    }


def _compute_parity(family: str, platform: str) -> dict[str, dict]:
    """Compare page counts vs other launched products of the same platform (SH-04).

    Returns per-subdomain dict with keys: target_count, peer_median, gap_pct, peers.
    """
    import statistics

    results = {}
    for site in _SUBDOMAINS:
        target_count = _count_en_pages(site, family, platform)
        # Find all other families that have this platform on this subdomain
        site_root = _CONTENT / site
        peer_counts = []
        if site == "blog.aspose.org":
            search_root = site_root
        else:
            search_root = site_root / "en"
        if search_root.is_dir():
            for fam_dir in sorted(search_root.iterdir()):
                if not fam_dir.is_dir() or fam_dir.name.startswith("."):
                    continue
                if fam_dir.name == family:
                    continue
                # Check if this family has the target platform
                if site == "blog.aspose.org":
                    plat_dir = fam_dir / platform
                else:
                    plat_dir = fam_dir / platform
                if plat_dir.is_dir():
                    count = _count_en_pages(site, fam_dir.name, platform)
                    if count > 0:
                        peer_counts.append(count)
        peer_median = statistics.median(peer_counts) if peer_counts else 0
        gap_pct = ((target_count - peer_median) / peer_median * 100) if peer_median > 0 else 0
        results[site] = {
            "target_count": target_count,
            "peer_median": peer_median,
            "gap_pct": gap_pct,
            "peer_count": len(peer_counts),
        }
    return results


def _count_en_pages(site: str, family: str, platform: str) -> int:
    """Count English source pages for a subdomain."""
    site_root = _CONTENT / site
    if site == "blog.aspose.org":
        blog_root = site_root / family / platform
        if not blog_root.is_dir():
            return 0
        return len(list(blog_root.rglob("index.md")))
    else:
        en_root = site_root / "en" / family / platform
        if not en_root.is_dir():
            # products has family directly under en (no platform for some)
            en_root = site_root / "en" / family
            if not en_root.is_dir():
                return 0
        return len(list(en_root.rglob("*.md")))


def _collect_grades(family: str, platform: str) -> dict:
    """Collect content grades from frontmatter across all EN pages."""
    grades = {"A": 0, "B": 0, "C": 0, "D": 0, "F": 0, "ungraded": 0}
    grade_re = re.compile(r"^grade:\s*([A-F])\s*$", re.MULTILINE)

    for site in _SUBDOMAINS:
        site_root = _CONTENT / site
        if site == "blog.aspose.org":
            search_root = site_root / family / platform
        else:
            search_root = site_root / "en" / family / platform
            if not search_root.is_dir():
                search_root = site_root / "en" / family

        if not search_root.is_dir():
            continue

        for md in search_root.rglob("*.md"):
            if md.name.startswith("index.") and md.name != "index.md":
                continue  # skip locale files in blog
            try:
                text = md.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            # Search the actual frontmatter block, not an arbitrary byte
            # count. Found 2026-07-23: text[:2000] silently misclassified 75
            # genuinely-graded words/net pages as "ungraded" because their
            # evidence:/content: frontmatter blocks (many claims/apis cited,
            # or plugin-layout pages with substantial overview/content/single
            # blocks) push the `grade:` line past 2000 chars -- e.g.
            # bibliography.md (grade at byte 207 of an 11880-byte file, but
            # still beyond 2000 once the preceding evidence block is counted)
            # and the products.aspose.org plugin page (grade at byte 132 of
            # an 8880-byte file). Frontmatter is delimited by a leading `---`
            # and the next `---` on its own line -- search only that span.
            frontmatter_end = text.find("\n---", 3)
            frontmatter = text[: frontmatter_end + 4] if text.startswith("---") and frontmatter_end != -1 else text[:2000]
            m = grade_re.search(frontmatter)
            if m:
                grades[m.group(1)] += 1
            else:
                grades["ungraded"] += 1

    return grades


def _import_acceptance_bindings():
    """Lazy sys.path-qualified import of lib/acceptance_bindings.py, matching
    this file's own existing lazy-import convention (see
    _verify_checkpoint_integrity's commands.ops.project_phase_store import
    above).

    Propagates THIS module's own (possibly test-configured) _ROOT into the
    imported module every call -- acceptance_bindings.py has its own
    independent configure() seam/global, so without this a test that calls
    readiness_scorecard.configure(repo_root=tmp_path) would silently read
    bindings from the REAL repo's knowledge/ instead of the fixture (found
    live while writing this card's own tests).
    """
    lib_dir = str(_ROOT / "scripts" / "pipeline" / "lib")
    if lib_dir not in sys.path:
        sys.path.insert(0, lib_dir)
    import acceptance_bindings
    acceptance_bindings.configure(repo_root=_ROOT)
    return acceptance_bindings


def _read_hgate_signoffs(family: str, platform: str) -> dict[str, str]:
    """Read human review gate sign-off results.

    Returns dict mapping gate id (h01..h05) to result
    (PASS/FAIL/CONDITIONAL/STALE/""). Empty string means no sign-off file
    found or sign-off not completed.

    R-1 (MT040-2026-08-28-PDF-TYPESCRIPT-LAUNCH TC-MT040-49): a PASS result
    is downgraded to "STALE" when the sample file carries a ``bindings:``
    block (see lib/acceptance_bindings.py) that no longer matches the
    product's CURRENT knowledge/evaluator state -- e.g. a reviewer signed
    off H-01 against one model_sha, and the knowledge model was re-promoted
    since, without a fresh review. A sample file with no bindings block at
    all (every file generated before this card existed) is "unverifiable"
    and its bare PASS/FAIL/CONDITIONAL is returned unchanged -- this is an
    additive check, not a retroactive one; it never invents staleness for an
    artifact that predates this signal.
    """
    review_dir = _ROOT / "reports" / "human-review"
    results: dict[str, str] = {}
    bindings_mod = None
    current_bindings = None
    for gate in _HGATES:
        sample_file = review_dir / f"{family}-{platform}-{gate}-sample.md"
        if not sample_file.is_file():
            results[gate] = ""
            continue
        try:
            text = sample_file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            results[gate] = ""
            continue
        # Normalize CRLF → LF and strip inline comments before parsing
        text = text.replace("\r\n", "\n")
        text = re.sub(r"#[^\n]*$", "", text, flags=re.MULTILINE)
        # Parse the YAML sign-off block (case-insensitive)
        m = re.search(
            r'^result:\s*"?(PASS|FAIL|CONDITIONAL)"?\s*$',
            text,
            re.MULTILINE | re.IGNORECASE,
        )
        result = m.group(1).upper() if m else ""
        if result == "PASS":
            try:
                if bindings_mod is None:
                    bindings_mod = _import_acceptance_bindings()
                    current_bindings = bindings_mod.compute_bindings(family, platform)
                stored = bindings_mod.parse_bindings_yaml(text)
                if bindings_mod.bindings_status(stored, current_bindings) == "stale":
                    result = "STALE"
            except Exception:  # noqa: BLE001 -- staleness check is additive, never fatal
                pass
        results[gate] = result
    return results


def _read_checkpoints(family: str, platform: str) -> dict:
    """Read checkpoint state for this product."""
    if not _PHASE_STATE.is_file():
        return {}
    with open(_PHASE_STATE, encoding="utf-8") as f:
        data = json.load(f)
    key = f"{family}/{platform}"
    entry = data.get(key, {})
    return entry.get("values", {})


def _verify_checkpoint_integrity(family: str, platform: str, checkpoints: dict) -> list[str]:
    """HARDEN-A5: re-verify artifact fingerprints behind every fingerprinted
    checkpoint. A checkpoint whose certified artifact was corrupted/reverted
    since it was set is a REAL blocker; legacy bool-only checkpoints are
    unverifiable (warn-only, never block — no flag day)."""
    problems: list[str] = []
    pipeline_root = str(_ROOT / "scripts" / "pipeline")
    if pipeline_root not in sys.path:
        sys.path.insert(0, pipeline_root)
    try:
        from commands.ops.project_phase_store import load_state, verify_checkpoint
    except ImportError as exc:
        print(f"WARN: checkpoint integrity verification unavailable: {exc}", file=sys.stderr)
        return problems
    state, _backup = load_state(_PHASE_STATE)
    for key in sorted(checkpoints):
        if key.endswith("__fingerprint"):
            continue
        if f"{key}__fingerprint" not in checkpoints:
            continue  # legacy bool-only — unverifiable, not blocking
        ok, notes = verify_checkpoint(state, family, platform, key)
        if not ok:
            for note in notes:
                problems.append(f"checkpoint {key}: {note}")
    return problems


def _verify_forbidden_claims_receipts(family: str, platform: str) -> list[str]:
    """HARDEN-A7/finding-1: consult the SAME on-disk receipt scan
    launch_gate.py's L-03 gate uses, so readiness_scorecard's own verdict
    can't diverge from L-03 on what counts as an unverified forbidden-claims
    scan (the two were previously separate re-implementations — a scan
    failure could read READY here while L-03 correctly failed it there)."""
    pipeline_root = str(_ROOT / "scripts" / "pipeline")
    if pipeline_root not in sys.path:
        sys.path.insert(0, pipeline_root)
    try:
        from commands.content.body_refresh import find_unverified_forbidden_claims_receipts
    except ImportError as exc:
        print(f"WARN: forbidden-claims receipt verification unavailable: {exc}", file=sys.stderr)
        return []
    try:
        return find_unverified_forbidden_claims_receipts(family, platform, repo_root=_ROOT)
    except Exception as exc:  # noqa: BLE001 — unreadable receipts are unverifiable, not clean
        return [f"(scan error: {exc})"]


def _set_checkpoint(family: str, platform: str, key: str, value: str):
    """Set a checkpoint via project_phase_store CLI.

    (A5 fix: the previous path pointed at the pre-migration root-level
    scripts/pipeline/project_phase_store.py, which no longer exists — the
    --set-checkpoint flag crashed on every invocation.)
    """
    import subprocess
    cmd = [sys.executable,
           str(_ROOT / "scripts" / "pipeline" / "commands" / "ops" / "project_phase_store.py"),
           "set", family, platform, key, value]
    subprocess.run(cmd, check=True, capture_output=True)


def compute_verdict(
    grades: dict[str, int],
    coverage: dict[str, dict],
    checkpoints: dict,
    hgate_results: dict[str, str],
    *,
    skip_human_review: bool = False,
    checkpoint_integrity: list[str] | None = None,
    unverified_forbidden_claims: list[str] | None = None,
) -> tuple[bool, list[str]]:
    """Compute launch readiness verdict. Pure function — no I/O, no sys.exit.

    Args:
        grades: grade-letter → count, e.g. {"A": 5, "B": 3, "D": 1, "F": 0, ...}
        coverage: subdomain → {"locales_present": n, "total_locales": 36, "coverage": 0.5}
        checkpoints: pipeline checkpoint dict (keys like "truth_audit_done")
        hgate_results: gate_id → "PASS" | "FAIL" | "CONDITIONAL" | ""
        skip_human_review: if True, skip H-gate criterion
        checkpoint_integrity: HARDEN-A5 fingerprint-verification failures from
            _verify_checkpoint_integrity() — each is a real blocker (an artifact
            a checkpoint certified has changed/vanished since certification)
        unverified_forbidden_claims: HARDEN-A7/finding-1 — receipt names from
            _verify_forbidden_claims_receipts() whose forbidden-claims scan
            did not verifiably complete. Each is a real blocker: this gate
            must not report READY for a page whose scan crashed or never ran,
            even though launch_gate.py's separate L-03 gate already catches
            the same condition — the two gates must not be allowed to disagree.

    Returns:
        (ready: bool, blockers: list[str])
    """
    blockers: list[str] = []

    # Criterion 0: phase_state entry must exist
    if not checkpoints:
        blockers.append("No phase_state entry — product not registered in launch tracking")

    # Criterion 0.5 (HARDEN-A5): fingerprinted checkpoints must still match disk
    for problem in (checkpoint_integrity or []):
        blockers.append(f"checkpoint integrity: {problem}")

    # Criterion 0.6 (HARDEN-A7/finding-1): every forbidden-claims scan must be verified
    for receipt_name in (unverified_forbidden_claims or []):
        blockers.append(f"unverified forbidden-claims scan: {receipt_name}")

    # Criterion 1: 0 D/F pages
    df_count = grades.get("D", 0) + grades.get("F", 0)
    if df_count > 0:
        blockers.append(f"{df_count} page(s) graded D or F")

    # Criterion 2: key checkpoints
    if not checkpoints.get("truth_audit_done"):
        blockers.append("truth_audit_done checkpoint not set")

    # Criterion 3: human review gates (H-01 through H-05)
    if not skip_human_review:
        for gate in _HGATES:
            result = hgate_results.get(gate, "")
            if result == "PASS":
                continue
            elif result == "FAIL":
                blockers.append(f"{_HGATE_NAMES[gate]} ({gate.upper()}): FAIL")
            elif result == "CONDITIONAL":
                blockers.append(f"{_HGATE_NAMES[gate]} ({gate.upper()}): CONDITIONAL — requires follow-up")
            elif result == "STALE":
                # R-1 (TC-MT040-49): this gate WAS signed off PASS, but the
                # sign-off's own bindings block no longer matches current
                # knowledge/evaluator state — treat it the same as an
                # unreviewed gate (never silently accept a stale PASS), with
                # a message that tells the operator WHY, not just that it's
                # missing.
                blockers.append(
                    f"{_HGATE_NAMES[gate]} ({gate.upper()}): STALE — signed off PASS against "
                    f"older knowledge/evaluator state; re-review required"
                )
            else:
                blockers.append(
                    f"{_HGATE_NAMES[gate]} ({gate.upper()}): not reviewed."
                )

    ready = len(blockers) == 0
    return ready, blockers


def main():
    parser = argparse.ArgumentParser(description="Stage 8 — Launch Readiness Scorecard")
    parser.add_argument("--family", required=True)
    parser.add_argument("--platform", required=True)
    parser.add_argument("--set-checkpoint", action="store_true",
                        help="Set readiness_done=true if READY TO SHIP")
    parser.add_argument("--json", action="store_true",
                        help="Output JSON instead of human-readable text")
    parser.add_argument("--skip-human-review", action="store_true",
                        help="Skip H-gate checks (development use only)")
    args = parser.parse_args()

    family = args.family
    platform = args.platform

    # Prerequisite check
    try:
        from core.prereqs import require_all
        require_all(family, platform)
    except SystemExit:
        raise
    except Exception:
        pass  # prereqs is best-effort

    # Collect data
    checkpoints = _read_checkpoints(family, platform)
    grades = _collect_grades(family, platform)
    coverage = {}
    for site in _SUBDOMAINS:
        coverage[site] = _count_locale_coverage(site, family, platform)

    # Evaluate readiness criteria
    hgate_results = _read_hgate_signoffs(family, platform)
    if args.skip_human_review:
        print(f"  AUDIT: --skip-human-review used for {family}/{platform}", file=sys.stderr)
    checkpoint_integrity = _verify_checkpoint_integrity(family, platform, checkpoints)
    unverified_forbidden_claims = _verify_forbidden_claims_receipts(family, platform)
    ready, blockers = compute_verdict(
        grades, coverage, checkpoints, hgate_results,
        skip_human_review=args.skip_human_review,
        checkpoint_integrity=checkpoint_integrity,
        unverified_forbidden_claims=unverified_forbidden_claims,
    )
    verdict = "READY TO SHIP" if ready else "NOT READY"

    if args.json:
        result = {
            "family": family,
            "platform": platform,
            "verdict": verdict,
            "ready": ready,
            "grades": grades,
            "coverage": coverage,
            "checkpoints": {k: v for k, v in checkpoints.items()
                           if k.endswith("_done")},
            "blockers": blockers,
            "human_review": hgate_results,
            "skip_human_review": args.skip_human_review,
        }
        print(json.dumps(result, indent=2))
    else:
        print(f"=== LAUNCH READINESS: {family}/{platform} ===\n")

        # Grades
        total_graded = sum(v for k, v in grades.items() if k != "ungraded")
        print("Content grades:")
        for g in ["A", "B", "C", "D", "F"]:
            print(f"  {g}: {grades[g]}")
        if grades["ungraded"]:
            print(f"  Ungraded: {grades['ungraded']}")
        print()

        # Translation coverage
        print("Translation coverage (informational — not a launch blocker):")
        for site in _SUBDOMAINS:
            cov = coverage[site]
            en_pages = _count_en_pages(site, family, platform)
            print(f"  {site:25s} {cov['locales_present']:2d}/{cov['total_locales']} locales "
                  f"({cov['coverage']:5.1%})  {cov['total_files']:4d} files  "
                  f"[{en_pages} EN pages]")
        print()

        # Content parity (SH-04 — informational, not a launch blocker)
        parity = _compute_parity(family, platform)
        has_parity_warning = False
        print("Content volume parity (informational — not a launch blocker):")
        for site in _SUBDOMAINS:
            p = parity[site]
            if p["peer_count"] == 0:
                print(f"  {site:25s} {p['target_count']:3d} pages  (no peers for comparison)")
                continue
            marker = ""
            if p["gap_pct"] < -40:
                marker = "  [!] WARNING: >40% below peer median"
                has_parity_warning = True
            print(f"  {site:25s} {p['target_count']:3d} pages  "
                  f"(peer median: {p['peer_median']:.0f}, gap: {p['gap_pct']:+.0f}%){marker}")
        if not has_parity_warning:
            print("  All subdomains within parity range.")
        print()

        # Human review gates
        print("Human review gates:")
        if args.skip_human_review:
            print("  (skipped via --skip-human-review)")
        else:
            for gate in _HGATES:
                result = hgate_results.get(gate, "")
                status = result if result else "NOT REVIEWED"
                mark = "+" if result == "PASS" else "-"
                print(f"  [{mark}] {gate.upper()} {_HGATE_NAMES[gate]}: {status}")
        print()

        # Checkpoints
        print("Checkpoints:")
        for ck in ["knowledge_ready", "truth_audit_done",
                    "quality_done", "readiness_done"]:
            val = checkpoints.get(ck, False)
            mark = "+" if val else "-"
            print(f"  [{mark}] {ck}")
        print()

        # Verdict
        print(f">>> {verdict} <<<")
        if blockers:
            print("\nBlockers:")
            for b in blockers:
                print(f"  - {b}")

    # Write report file
    report_dir = _ROOT / "reports" / family / platform
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / "readiness.md"
    # R-1 (TC-MT040-49): this run just recomputed every grade/checkpoint/
    # hgate signal fresh, so the bindings this readiness.md is written
    # against are, by construction, the CURRENT ones — a later reader
    # (product_state.py, or a human) compares this block's own values
    # against a fresh compute_bindings() call to tell whether THIS file has
    # since gone stale.
    try:
        bindings_mod = _import_acceptance_bindings()
        current_bindings = bindings_mod.compute_bindings(family, platform)
        bindings_yaml = bindings_mod.format_bindings_yaml(current_bindings)
    except Exception as exc:  # noqa: BLE001 -- bindings are additive, never block the report
        current_bindings = None
        bindings_yaml = f"bindings: null  # unavailable: {exc}"

    with open(report_path, "w", encoding="utf-8") as f:
        f.write(f"# Readiness Scorecard: {family}/{platform}\n\n")
        f.write(f"**Verdict**: {verdict}\n\n")
        f.write("```yaml\n")
        f.write(bindings_yaml + "\n")
        f.write("```\n\n")
        f.write("## Translation Coverage (informational — not a launch blocker)\n\n")
        f.write("| Subdomain | Locales | Coverage | Files |\n")
        f.write("|-----------|---------|----------|-------|\n")
        for site in _SUBDOMAINS:
            cov = coverage[site]
            f.write(f"| {site} | {cov['locales_present']}/{cov['total_locales']} | "
                    f"{cov['coverage']:.0%} | {cov['total_files']} |\n")
        f.write(f"\n## Grades\n\n")
        for g in ["A", "B", "C", "D", "F"]:
            f.write(f"- {g}: {grades[g]}\n")
        f.write(f"\n## Human Review Gates\n\n")
        f.write("| Gate | Name | Result |\n")
        f.write("|------|------|--------|\n")
        for gate in _HGATES:
            result = hgate_results.get(gate, "")
            f.write(f"| {gate.upper()} | {_HGATE_NAMES[gate]} | {result or 'NOT REVIEWED'} |\n")

        if blockers:
            f.write(f"\n## Blockers\n\n")
            for b in blockers:
                f.write(f"- {b}\n")

    print(f"\nReport written to: {report_path}")

    # Set checkpoint if requested and ready
    if args.set_checkpoint and ready:
        _set_checkpoint(family, platform, "readiness_done", "true")
        print(f"Checkpoint readiness_done=true set for {family}/{platform}")

    sys.exit(0 if ready else 1)


if __name__ == "__main__":
    main()
