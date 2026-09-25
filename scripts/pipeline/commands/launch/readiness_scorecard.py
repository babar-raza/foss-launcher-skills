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


def _check_blog_post_exists(family: str, platform: str) -> str | None:
    """H-4 (MT074): every launch must ship at least one real blog post
    (the mandatory blog_role: announcement post).

    Before this fix, nothing in this script checked blog-post existence at
    all -- a product whose site_planner.py::plan_blog() call returned zero
    pages (all-or-nothing on total_claims>=200 and snippet_count>=5, INV-021)
    would report a clean READY TO SHIP despite `launch-product.md`'s own
    prose claiming "first blog post at B+" as a readiness criterion. Real
    precedent: imaging/net (68 claims) launched with zero blog posts and
    needed a human to notice the resulting 404 and patch it in separately.

    Checks for at least one real post directory (contains index.md, the
    canonical English source) under content/blog.aspose.org/{family}/
    {platform}/ -- a bare index.<locale>.md with no English index.md doesn't
    count, matching how _collect_grades() and _count_en_pages() already treat
    "index.md" as the one canonical file per post in this same module.

    Returns None if at least one real post exists, else a blocker message.
    """
    blog_root = _CONTENT / "blog.aspose.org" / family / platform
    if not blog_root.is_dir():
        return (
            f"no blog posts exist for {family}/{platform} "
            f"(content/blog.aspose.org/{family}/{platform}/ does not exist) — "
            f"every launch must ship at least one announcement post"
        )
    if not any(blog_root.glob("*/index.md")):
        return (
            f"no blog posts exist for {family}/{platform} "
            f"(content/blog.aspose.org/{family}/{platform}/ has no post directory "
            f"with an index.md) — every launch must ship at least one announcement post"
        )
    return None


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


def _find_final_verdict_recommendation(family: str, platform: str) -> "str | None":
    """H-2 (MT074): locate S-90's real, agent-authored
    reports/publish-review/{family}-{platform}-{YYYYMMDD}/final-verdict.md
    and parse its "## Final Recommendation" section for PUBLISH / CONDITIONAL
    / BLOCKED (per the template at .claude/commands/publish-readiness-review.md).

    S-90's Steps 7+ (including final-verdict.md authoring) have no backing
    script -- the skill's own docstring says so explicitly -- so there is no
    write-time hook to intercept. This is deliberately a read-side fix
    instead: readiness_scorecard.py reads the real artifact directly rather
    than trusting a hand-typed sign-off file with no link back to it.

    Returns the most recent recommendation found (by directory date suffix,
    lexicographically sortable), or None if no final-verdict.md exists or it
    could not be parsed.
    """
    review_root = _ROOT / "reports" / "publish-review"
    if not review_root.is_dir():
        return None
    candidates = sorted(review_root.glob(f"{family}-{platform}-*/final-verdict.md"))
    if not candidates:
        return None
    verdict_file = candidates[-1]  # YYYYMMDD suffix sorts newest-last
    try:
        text = verdict_file.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    section_match = re.search(
        r"##\s*Final Recommendation\s*\n(.*?)(?:\n##|\Z)", text, re.DOTALL | re.IGNORECASE
    )
    section = section_match.group(1) if section_match else text
    m = re.search(r"\b(PUBLISH|CONDITIONAL|BLOCKED)\b", section, re.IGNORECASE)
    return m.group(1).upper() if m else None


def _read_hgate_signoffs(family: str, platform: str) -> dict[str, str]:
    """Read human review gate sign-off results.

    Returns dict mapping gate id (h01..h05) to result
    (PASS/FAIL/CONDITIONAL/STALE/UNLINKED/CONTRADICTED/""). Empty string
    means no sign-off file found or sign-off not completed.

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

    H-2 (MT074): a PASS/CONDITIONAL result is further checked against S-90's
    real reports/publish-review/.../final-verdict.md. Before this fix, this
    reader trusted a `reports/human-review/*-sample.md` file whose own
    generator (human_review_sampler.py) writes it with a literal empty
    `result: ""` and the instruction "fill in after review" -- nothing
    checked that a real S-90 review had actually produced that result, or
    that it agreed with S-90's own output. This had already diverged in
    production once (cells/typescript's readiness.md and its real
    final-verdict.md directly contradicted each other with no mechanical
    check). Two new downgrades close this:
      - "UNLINKED": the sample says PASS/CONDITIONAL but no final-verdict.md
        exists for this family/platform at all -- an unreviewed
        self-attestation with nothing behind it.
      - "CONTRADICTED": a final-verdict.md exists, but its own Final
        Recommendation is BLOCKED while the sample claims PASS -- a real,
        detected divergence between the two verdict paths, the exact shape
        of the cells/typescript incident.
    """
    review_dir = _ROOT / "reports" / "human-review"
    results: dict[str, str] = {}
    bindings_mod = None
    current_bindings = None
    final_verdict_recommendation = "_unchecked"  # sentinel: lazily computed once, cached
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
        if result in ("PASS", "CONDITIONAL"):
            if final_verdict_recommendation == "_unchecked":
                try:
                    final_verdict_recommendation = _find_final_verdict_recommendation(family, platform)
                except Exception:  # noqa: BLE001 -- additive check, never fatal
                    final_verdict_recommendation = None
            if final_verdict_recommendation is None:
                result = "UNLINKED"
            elif final_verdict_recommendation == "BLOCKED":
                result = "CONTRADICTED"
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


# H-1 (MT074-2026-09-25-GIS-NET-LAUNCH-AND-READINESS-GATE-HARDENING): the two
# launch_gate.py gates that are structurally incapable of ever meaningfully
# blocking a launch. L-06 can only ever return FAIL or SKIP by design (its own
# module docstring: a placeholder pending a `promote.py --dry-run` mode that
# doesn't exist yet) -- wiring it in as a blocker would make every launch
# permanently unshippable. L-14's grade-regression comparison is unimplemented
# (its own inline comment: "For now, just report stats") and can only return
# PASS or SKIP -- wiring it in as a blocker would be a no-op. Both are still
# run and their results recorded for visibility; neither is silently hidden.
_LAUNCH_GATE_INFORMATIONAL_ONLY = frozenset({"L-06", "L-14"})


def _run_launch_gates(family: str, platform: str) -> tuple[list[str], list[dict]]:
    """H-1: genuinely invoke launch_gate.py's gates as part of the real Stage-8
    verdict.

    Before this fix, `.claude/commands/launch-product.md`'s Stage 8.5 claimed
    "the prior stage's launch_gate.py runs 16 automated gates" -- but
    readiness_scorecard.py (the script Stage 8 actually runs) never imported
    or subprocessed launch_gate.py at all. This was proven, not inferred,
    against a real incident: imaging/net's on-disk `reports/imaging/net/
    readiness.md`, produced by a real Stage-8 run before its Day-2 family-page
    fix, reported a clean "NOT READY (H-gates only)" verdict with zero mention
    of the stale "coming soon" placeholder L-10 exists to catch. A second,
    orphaned script (`readiness_gate.py`) did call launch_gate.py, but was
    never wired into `/launch-product` -- only into unrelated subsystems.

    L-07 (the full `pytest scripts/pipeline/tests/` suite) is skipped by
    default here, matching the existing precedent already set by
    `readiness_gate.py`'s own G-06 gate (`launch_gate.py {family} {platform}
    --skip-tests`) -- a full-suite run on every readiness check is
    prohibitively slow for routine, possibly-repeated use; run it separately
    (`launch_gate.py {family} {platform}` without `--skip-tests`) when a full
    pipeline-test pass is actually wanted.

    Returns:
        (blockers, gate_results) -- blockers is a list of human-readable FAIL
        strings for any non-informational-only gate; gate_results is every
        gate's {gate_id, status, detail} for reporting, including the two
        informational-only gates (never contributing to blockers).
    """
    pipeline_root = str(_ROOT / "scripts" / "pipeline")
    if pipeline_root not in sys.path:
        sys.path.insert(0, pipeline_root)
    try:
        from commands.launch import launch_gate
    except ImportError as exc:
        print(f"WARN: launch_gate wiring unavailable: {exc}", file=sys.stderr)
        return [], []

    launch_gate.configure(repo_root=_ROOT)

    blockers: list[str] = []
    gate_results: list[dict] = []
    for gate_fn in launch_gate._ALL_GATES:
        if gate_fn is launch_gate.gate_l07_pipeline_tests:
            continue  # skipped by default -- see docstring above
        try:
            result = gate_fn(family, platform)
        except Exception as exc:  # noqa: BLE001 -- a crashing gate is a real blocker, not silence
            blockers.append(f"launch gate crashed: {gate_fn.__name__}: {exc}")
            continue
        gate_results.append({
            "gate_id": result.gate_id,
            "name": result.name,
            "status": result.status,
            "detail": result.detail,
        })
        if result.status == launch_gate.STATUS_FAIL and result.gate_id not in _LAUNCH_GATE_INFORMATIONAL_ONLY:
            blockers.append(f"{result.gate_id} {result.name}: {result.detail}")
    return blockers, gate_results


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
    launch_gate_failures: list[str] | None = None,
    blog_post_missing: str | None = None,
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
        launch_gate_failures: H-1 (MT074) — FAIL results from
            _run_launch_gates() for any of launch_gate.py's non-informational-
            only gates (L-01..L-05, L-07..L-13, L-15, L-16). Each is a real
            blocker — this is the fix for the proven gap where this verdict
            could report READY TO SHIP while a live "coming soon" family-page
            placeholder (L-10) or any other launch_gate.py gate was failing,
            unnoticed, because nothing here ever ran them.
        blog_post_missing: H-4 (MT074) — a message from _check_blog_post_exists()
            if the family/platform has zero real blog posts on disk, else None.
            A real blocker — closes INV-021's second half, where a
            zero-blog-post launch previously reported a clean READY TO SHIP
            with no criterion checking blog-post existence at all.

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

    # Criterion 0.7 (H-1, MT074): launch_gate.py's own gates must actually run and pass
    for failure in (launch_gate_failures or []):
        blockers.append(f"launch gate: {failure}")

    # Criterion 0.8 (H-4, MT074): the mandatory announcement blog post must exist
    if blog_post_missing:
        blockers.append(blog_post_missing)

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
            elif result == "UNLINKED":
                # H-2 (MT074): a hand-typed PASS/CONDITIONAL sign-off with no
                # corresponding S-90 final-verdict.md — a self-attestation
                # with nothing real behind it.
                blockers.append(
                    f"{_HGATE_NAMES[gate]} ({gate.upper()}): UNLINKED — sample file claims a "
                    f"result but no reports/publish-review/.../final-verdict.md exists for "
                    f"this product; run /publish-readiness-review"
                )
            elif result == "CONTRADICTED":
                # H-2 (MT074): the real S-90 output disagrees with the
                # hand-typed sign-off — the exact shape of the cells/
                # typescript incident (readiness.md said NOT READY while
                # final-verdict.md said PUBLISH), now mechanically caught.
                blockers.append(
                    f"{_HGATE_NAMES[gate]} ({gate.upper()}): CONTRADICTED — sample file claims "
                    f"a result but the real S-90 final-verdict.md's Final Recommendation is "
                    f"BLOCKED; the two verdicts disagree, re-review required"
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
    launch_gate_failures, launch_gate_results = _run_launch_gates(family, platform)
    blog_post_missing = _check_blog_post_exists(family, platform)
    ready, blockers = compute_verdict(
        grades, coverage, checkpoints, hgate_results,
        skip_human_review=args.skip_human_review,
        checkpoint_integrity=checkpoint_integrity,
        unverified_forbidden_claims=unverified_forbidden_claims,
        launch_gate_failures=launch_gate_failures,
        blog_post_missing=blog_post_missing,
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
            "launch_gates": launch_gate_results,
            "blog_post_missing": blog_post_missing,
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

        # Launch gates (H-1, MT074)
        print("Launch gates (launch_gate.py L-01..L-16, L-07 skipped by default):")
        if launch_gate_results:
            for g in launch_gate_results:
                mark = "+" if g["status"] == "PASS" else ("~" if g["status"] in ("WARN", "SKIP") else "-")
                info_note = " (informational only)" if g["gate_id"] in _LAUNCH_GATE_INFORMATIONAL_ONLY else ""
                print(f"  [{mark}] {g['gate_id']} {g['name']}: {g['status']}{info_note}")
        else:
            print("  (unavailable — see WARN above)")
        print()

        # Blog post existence (H-4, MT074)
        print("Blog post (mandatory announcement post):")
        print(f"  [{'-' if blog_post_missing else '+'}] "
              f"{blog_post_missing or 'at least one real post exists'}")
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

        f.write(f"\n## Launch Gates (launch_gate.py, L-07 skipped by default)\n\n")
        f.write("| Gate | Name | Status |\n")
        f.write("|------|------|--------|\n")
        for g in launch_gate_results:
            note = " (informational only)" if g["gate_id"] in _LAUNCH_GATE_INFORMATIONAL_ONLY else ""
            f.write(f"| {g['gate_id']} | {g['name']} | {g['status']}{note} |\n")

        f.write(f"\n## Blog Post (mandatory announcement post)\n\n")
        f.write(f"{blog_post_missing or 'At least one real post exists.'}\n")

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
