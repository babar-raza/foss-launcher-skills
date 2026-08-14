"""CONTRACT: scripts/pipeline/commands/governance/publish_readiness_review_run.py — backing
script for the /publish-readiness-review skill (S-90).

RC-W1-006 (MT026-2026-08-09-BLIND-SPOT-AUDIT-WAVE1, TC-BSA-...-06): S-90 had NO
deterministic CLI/backing script anywhere in the repo. The only real, live component,
``commands/launch/publish_classifier.py``, is a pure function of the PERSISTED
frontmatter ``grade:`` field — nothing enforced that this persisted grade was actually
current. Confirmed live 2026-08-09 on words/python: ``content/reference.aspose.org/en/
words/python/Document.md`` and ``Table.md`` both document the WRONG internal class
entirely (a correctness-critical defect) yet carry ``grade: A`` with no
``graded_logic_version`` anywhere in their frontmatter. A literal S-90 pass over
frontmatter alone would classify both PUBLISH-READY.

What this script actually verifies before trusting a page's grade
--------------------------------------------------------------------
Per ARCH-04/D-1, current-architecture pages do NOT carry ``graded_logic_version`` in
frontmatter at all — that field now lives in the external ``reports/grade_manifest.json``
manifest (see ``lib/grade_manifest.py``), keyed by relative filepath. Its absence from a
page's frontmatter is therefore NOT, by itself, informative — every page under the
current architecture lacks it, whether freshly graded or years stale. The only way to
tell the difference is to cross-reference the manifest:

  1. If neither frontmatter nor the manifest carries a logic version that matches the
     live ``EVALUATOR_LOGIC_VERSION`` (``content_eval/__init__.py``), the grade is
     STALE — untrustworthy for classification, regardless of the letter grade stored.
  2. If the manifest's ``content_hash`` no longer matches the page's current body hash,
     the page changed since it was last graded — also STALE.
  3. Only a page whose logic version AND content hash both check out is FRESH enough to
     classify via ``publish_classifier.classify_page()``.
  4. Even a FRESH grade that would otherwise auto-publish (PUBLISH_READY /
     ACCEPTABLE_GRADE_C) is cross-checked against the most recent
     ``reports/truth-audit/{family}-{platform}-*.json`` and
     ``reports/gap-analysis/{family}-{platform}.json`` — a live UNSUPPORTED/
     CONTRADICTED/FABRICATED unit, or an open M/S-severity finding, downgrades the
     page: the content-eval grade rubric never consumes these signals (the actual
     defect this taskcard fixes).

Deferred scope (documented, not silently dropped)
---------------------------------------------------
This script implements Steps 1-6 of the S-90 skill (parse args, build page roster,
inspect/classify each page, write the inspection manifest). It deliberately does NOT
implement Step 7+ (routing to fix skills S-21/S-26/batch-reference/S-65/S-38/S-73,
re-evaluation of actioned pages, or final-verdict.md authoring) — those steps invoke
other skills interactively and are out of scope for a single deterministic CLI. Running
the full live content_eval evaluation pipeline per-page (rather than reading the
persisted grade + external manifest) is also deferred: it is expensive and the actual
defect being fixed here is the missing staleness/cross-check gate, not the evaluator
itself. ``--dry-run`` and its absence both run the same read-only classification; the
only difference is whether the inspection manifest is written to
``reports/publish-review/{family}-{platform}-{YYYYMMDD}/inspection-manifest.json``
(non-dry-run) or only printed (dry-run) — this script never mutates content/ or
knowledge/.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_PIPELINE_ROOT = Path(__file__).resolve().parents[2]
if str(_PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_ROOT))
_LIB_DIR = str(_PIPELINE_ROOT / "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)

import content_discovery  # noqa: E402
from grade_manifest import load_manifest  # noqa: E402
from grade_writer import content_hash  # noqa: E402
from core.markdown import parse_frontmatter, _FRONTMATTER_WRITER_RE as _FM_RE  # noqa: E402
from core.fs import atomic_write  # noqa: E402
from content_eval import EVALUATOR_LOGIC_VERSION as CURRENT_LOGIC_VERSION  # noqa: E402
from commands.launch.publish_classifier import classify_page  # noqa: E402

_DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[4]
_repo_root = _DEFAULT_REPO_ROOT
_now = lambda: datetime.now(timezone.utc)  # noqa: E731


def configure(*, repo_root: "Path | str | None" = None, now=None) -> None:
    """Override the repo root (and, for tests, the clock). Call with no arguments to reset."""
    global _repo_root, _now
    _repo_root = Path(repo_root) if repo_root is not None else _DEFAULT_REPO_ROOT
    _now = now or (lambda: datetime.now(timezone.utc))


# Site content roots (S-90 skill Step 4). Reimplemented locally rather than via
# lib/content_discovery.py's discover_content(): that module's SITE_PATHS is a
# module-level constant frozen at import time against the REAL repo root --
# content_discovery.configure(repo_root=...) updates _REPO_ROOT but never rebuilds
# SITE_PATHS from it, so discover_content() cannot be pointed at a tmp_path in tests
# (confirmed live while building this script's test suite). Duplicating the (small,
# stable) site list here keeps this script's own configure(repo_root=...) fully
# effective end-to-end.
_SITE_DIR_PATTERNS = (
    "content/products.aspose.org/en/{family}/{platform}",
    "content/reference.aspose.org/en/{family}/{platform}",
    "content/docs.aspose.org/en/{family}/{platform}",
    "content/blog.aspose.org/{family}/{platform}",
    "content/kb.aspose.org/en/{family}/{platform}",
)


def _discover_pages(family: str, platform: str, repo_root: Path) -> list[Path]:
    """Enumerate English content pages for a family/platform across all 5 sites."""
    files: list[Path] = []
    for pattern in _SITE_DIR_PATTERNS:
        site_dir = repo_root / pattern.format(family=family, platform=platform)
        if not site_dir.exists():
            continue
        for f in sorted(site_dir.rglob("*.md")):
            if content_discovery.LOCALE_RE.search(f.name):
                continue
            files.append(f)
    return files


# ---------------------------------------------------------------------------
# Dispositions
# ---------------------------------------------------------------------------

DISPOSITIONS = ("PUBLISH", "CONDITIONAL", "BLOCKED", "SKIP")

# publish_classifier's own labels -> this script's coarser PUBLISH/CONDITIONAL/BLOCKED
# disposition, before cross-check downgrades are applied.
_RAW_TO_BASE_DISPOSITION = {
    "PUBLISH_READY": "PUBLISH",
    "ACCEPTABLE_GRADE_C": "PUBLISH",
    "NEEDS_ACTION_S21": "CONDITIONAL",
    "NEEDS_ACTION_S26": "CONDITIONAL",
    "BLOCKED": "BLOCKED",
}

_DEFECT_VERDICTS = frozenset({"UNSUPPORTED", "CONTRADICTED", "FABRICATED"})
_SEVERE_VERDICTS = frozenset({"CONTRADICTED", "FABRICATED"})

_FAIL_COUNT_RE = re.compile(r"(\d+)\s+FAIL finding")


@dataclass
class PageResult:
    filepath: str
    grade: str
    grade_status: str
    grade_status_detail: str
    raw_classification: str
    suggested_skill: str
    disposition: str
    reasons: list[str] = field(default_factory=list)
    cross_check_hits: list[dict] = field(default_factory=list)


@dataclass
class ProductReadinessReport:
    family: str
    platform: str
    dry_run: bool
    evaluator_logic_version: str
    truth_audit_report: "str | None"
    gap_analysis_report: "str | None"
    results: list[PageResult] = field(default_factory=list)

    @property
    def total_pages(self) -> int:
        return len(self.results)

    @property
    def summary(self) -> dict[str, int]:
        counts: dict[str, int] = {d: 0 for d in DISPOSITIONS}
        for r in self.results:
            counts[r.disposition] = counts.get(r.disposition, 0) + 1
        return counts

    @property
    def grade_status_summary(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for r in self.results:
            counts[r.grade_status] = counts.get(r.grade_status, 0) + 1
        return counts


# ---------------------------------------------------------------------------
# Helpers — grade manifest lookup + staleness
# ---------------------------------------------------------------------------

def _lookup_manifest_entry(manifest: dict, rel_path: str, abs_path: str) -> "dict | None":
    """Look up a page's manifest entry.

    Tolerates the two key styles observed live in reports/grade_manifest.json
    (relative-to-repo-root, and absolute-with-forward-slashes -- an artifact of
    different invocation styles over time, not something this script can fix).
    When both exist, prefer whichever has a non-empty logic_version; break
    remaining ties by evaluated_at (most recent wins).
    """
    rel_entry = manifest.get(rel_path)
    abs_entry = manifest.get(abs_path)
    if rel_entry is None:
        return abs_entry
    if abs_entry is None:
        return rel_entry
    rel_lv = rel_entry.get("logic_version") or ""
    abs_lv = abs_entry.get("logic_version") or ""
    if bool(rel_lv) != bool(abs_lv):
        return rel_entry if rel_lv else abs_entry
    if (abs_entry.get("evaluated_at") or "") > (rel_entry.get("evaluated_at") or ""):
        return abs_entry
    return rel_entry


def _grade_status(fm: dict, manifest_entry: "dict | None", current_body_hash: str) -> tuple[str, str]:
    """Determine whether a page's persisted grade can be trusted for classification.

    Returns (status, detail). status is one of:
      NO_GRADE, STALE_NO_MANIFEST_ENTRY, STALE_LOGIC_VERSION, STALE_CONTENT_HASH, FRESH
    """
    grade = fm.get("grade")
    if not grade:
        return "NO_GRADE", "no grade field in frontmatter -- page has never been graded"

    # Legacy path: a pre-ARCH-04 page may still carry graded_logic_version directly in
    # frontmatter. If present and current, and content_hash still matches, trust it
    # without needing the external manifest.
    fm_logic_version = fm.get("graded_logic_version") or ""
    fm_hash = fm.get("graded_content_hash") or ""

    if fm_logic_version:
        if fm_logic_version != CURRENT_LOGIC_VERSION:
            return "STALE_LOGIC_VERSION", (
                f"frontmatter graded_logic_version={fm_logic_version!r} != "
                f"current EVALUATOR_LOGIC_VERSION={CURRENT_LOGIC_VERSION!r}"
            )
        if fm_hash and fm_hash != current_body_hash:
            return "STALE_CONTENT_HASH", (
                "frontmatter graded_content_hash does not match the page's current "
                "body hash -- content changed since last grading"
            )
        return "FRESH", "frontmatter graded_logic_version matches current EVALUATOR_LOGIC_VERSION"

    # Current architecture (ARCH-04/D-1 onward): logic_version lives ONLY in the
    # external grade manifest, not in .md frontmatter. Its absence here is expected
    # for every page, fresh or stale alike -- the manifest is the only place the real
    # answer lives.
    if manifest_entry is None:
        return "STALE_NO_MANIFEST_ENTRY", (
            "no graded_logic_version in frontmatter AND no entry in "
            "reports/grade_manifest.json for this page -- grade provenance cannot "
            "be verified"
        )

    manifest_logic_version = manifest_entry.get("logic_version") or ""
    if manifest_logic_version != CURRENT_LOGIC_VERSION:
        return "STALE_LOGIC_VERSION", (
            f"grade_manifest.json logic_version={manifest_logic_version!r} != "
            f"current EVALUATOR_LOGIC_VERSION={CURRENT_LOGIC_VERSION!r}"
        )

    manifest_hash = manifest_entry.get("content_hash") or ""
    if manifest_hash and manifest_hash != current_body_hash:
        return "STALE_CONTENT_HASH", (
            "grade_manifest.json content_hash does not match the page's current body "
            "hash -- content changed since last grading"
        )

    return "FRESH", "grade_manifest.json logic_version matches current EVALUATOR_LOGIC_VERSION"


def _extract_fail_count(grade_reasons: "list[str] | None") -> int:
    """Parse the real FAIL count out of a persisted grade_reasons list.

    content_eval writes at most one "N FAIL finding(s) [...] -> base grade X" reason
    (models.py EvalReport.grade_reasons()). Using the real count -- rather than assuming
    grade A/B implies zero FAILs -- matters: category ceilings (CP, AC) can cap a page at
    grade B even with a live FAIL finding, so a naive "A/B means no FAILs" assumption
    would misclassify those pages as PUBLISH_READY.
    """
    for reason in grade_reasons or []:
        m = _FAIL_COUNT_RE.search(reason)
        if m:
            return int(m.group(1))
    return 0


# ---------------------------------------------------------------------------
# Helpers — truth-audit / gap-analysis cross-check
# ---------------------------------------------------------------------------

def _find_latest_report(reports_dir: Path, family: str, platform: str) -> "Path | None":
    """Find the newest report for a product: {family}-{platform}-*.json (date-stamped,
    truth-audit style) or the exact {family}-{platform}.json (gap-analysis style).
    Sorted by mtime, filename as tiebreaker (date-stamped names also sort correctly
    lexicographically).
    """
    if not reports_dir.exists():
        return None
    candidates = list(reports_dir.glob(f"{family}-{platform}-*.json"))
    exact = reports_dir / f"{family}-{platform}.json"
    if exact.exists():
        candidates.append(exact)
    if not candidates:
        return None
    candidates.sort(key=lambda p: (p.stat().st_mtime, p.name))
    return candidates[-1]


def _norm_repo_rel(raw_path: str, repo_root: Path) -> str:
    """Normalize a finding's `file` field to a repo-root-relative posix path.

    Report findings have been observed with both relative
    ("content/reference.aspose.org/en/words/python/Document.md") and absolute
    Windows ("D:\\\\...\\\\content\\\\...") path forms in the same report -- the same
    key-format inconsistency seen in grade_manifest.json. Normalize both to the same
    relative form so cross-check lookups aren't silently missed.
    """
    p = (raw_path or "").replace("\\", "/")
    repo_str = str(repo_root).replace("\\", "/")
    if p.startswith(repo_str):
        p = p[len(repo_str):].lstrip("/")
    return p


def _load_findings_by_file(path: "Path | None", repo_root: Path) -> dict[str, list[dict]]:
    if path is None:
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return {}
    by_file: dict[str, list[dict]] = {}
    for f in data.get("findings", []) or []:
        rel = _norm_repo_rel(f.get("file", ""), repo_root)
        if rel:
            by_file.setdefault(rel, []).append(f)
    return by_file


def _severity_is_high(severity: str) -> bool:
    """True for severity values whose first letter is M or S -- tolerates both the
    truth-audit convention (single uppercase letter: "M", "S") and the gap-analysis
    convention (full words for some finding types: "medium", "low", ...)."""
    if not severity:
        return False
    letter = severity.strip()[0].upper()
    return letter in ("M", "S")


def _cross_check(rel_path: str, truth_by_file: dict, gap_by_file: dict) -> list[dict]:
    """Return live findings for *rel_path* that the content-eval grade rubric never
    consumes: a defect verdict (UNSUPPORTED/CONTRADICTED/FABRICATED) or an open
    M/S-severity finding from either report. Only ``status == "open"`` findings count
    -- a finding already marked "fixed"/"resolved" does not block publication."""
    hits: list[dict] = []
    for f in truth_by_file.get(rel_path, []):
        if (f.get("status") or "open") != "open":
            continue
        verdict = f.get("verdict", "")
        severity = f.get("severity", "")
        if verdict in _DEFECT_VERDICTS or _severity_is_high(severity):
            hits.append({
                "source": "truth-audit",
                "id": f.get("id", ""),
                "verdict": verdict,
                "severity": severity,
                "severe": verdict in _SEVERE_VERDICTS,
                "description": (f.get("description") or "")[:200],
            })
    for f in gap_by_file.get(rel_path, []):
        if (f.get("status") or "open") != "open":
            continue
        severity = f.get("severity", "")
        if _severity_is_high(severity):
            hits.append({
                "source": "gap-analysis",
                "id": f.get("id", ""),
                "verdict": f.get("type", ""),
                "severity": severity,
                "severe": False,
                "description": (f.get("description") or "")[:200],
            })
    return hits


# ---------------------------------------------------------------------------
# Per-page classification
# ---------------------------------------------------------------------------

def _page_body(text: str) -> str:
    m = _FM_RE.match(text)
    return text[m.end():] if m else text


def classify_page_full(
    filepath: Path,
    *,
    repo_root: Path,
    manifest: dict,
    truth_by_file: dict,
    gap_by_file: dict,
) -> PageResult:
    """Classify one page: staleness gate first, then (only for a FRESH grade) the
    deterministic S-90 table via publish_classifier.classify_page(), then the
    truth-audit/gap-analysis cross-check for any tentative PUBLISH disposition."""
    rel_path = str(filepath.relative_to(repo_root)).replace("\\", "/")

    try:
        text = filepath.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return PageResult(
            filepath=rel_path, grade="", grade_status="READ_ERROR",
            grade_status_detail=str(exc), raw_classification="", suggested_skill="",
            disposition="BLOCKED", reasons=[f"cannot read file: {exc}"],
        )

    fm = parse_frontmatter(filepath)
    if fm.get("draft") is True:
        return PageResult(
            filepath=rel_path, grade=fm.get("grade", "") or "", grade_status="SKIP",
            grade_status_detail="draft: true", raw_classification="", suggested_skill="",
            disposition="SKIP", reasons=["draft page -- excluded from publish review"],
        )

    current_hash = content_hash(_page_body(text))
    abs_path = str(filepath).replace("\\", "/")
    manifest_entry = _lookup_manifest_entry(manifest, rel_path, abs_path)

    status, detail = _grade_status(fm, manifest_entry, current_hash)
    grade = fm.get("grade") or (manifest_entry or {}).get("grade") or ""

    if status == "NO_GRADE":
        return PageResult(
            filepath=rel_path, grade="", grade_status=status, grade_status_detail=detail,
            raw_classification="", suggested_skill="", disposition="BLOCKED",
            reasons=[detail],
        )

    if status != "FRESH":
        return PageResult(
            filepath=rel_path, grade=grade, grade_status=status, grade_status_detail=detail,
            raw_classification="", suggested_skill="", disposition="CONDITIONAL",
            reasons=[
                detail,
                "grade cannot be trusted for classification -- re-run "
                "`content_eval evaluate --write-grade` before this page can be assessed",
            ],
        )

    # FRESH -- safe to reuse the deterministic S-90 classification table.
    grade_reasons = fm.get("grade_reasons") or (manifest_entry or {}).get("grade_reasons") or []
    fail_count = _extract_fail_count(grade_reasons)
    is_reference = "reference.aspose.org" in rel_path
    evidence = fm.get("evidence") or {}
    apis = evidence.get("apis") or [] if isinstance(evidence, dict) else []
    has_apis = bool(apis)

    raw_label, suggested_skill = classify_page(grade, fail_count, is_reference, has_apis)
    disposition = _RAW_TO_BASE_DISPOSITION.get(raw_label, "CONDITIONAL")
    reasons = [f"fresh grade {grade} -> {raw_label} (fail_count={fail_count})"]

    cross_check_hits: list[dict] = []
    if disposition == "PUBLISH":
        cross_check_hits = _cross_check(rel_path, truth_by_file, gap_by_file)
        if cross_check_hits:
            severe = any(h["severe"] for h in cross_check_hits)
            disposition = "BLOCKED" if severe else "CONDITIONAL"
            reasons.append(
                f"downgraded from PUBLISH: {len(cross_check_hits)} live truth-audit/"
                "gap-analysis finding(s) not consumed by the content-eval grade rubric"
            )

    return PageResult(
        filepath=rel_path, grade=grade, grade_status=status, grade_status_detail=detail,
        raw_classification=raw_label, suggested_skill=suggested_skill,
        disposition=disposition, reasons=reasons, cross_check_hits=cross_check_hits,
    )


# ---------------------------------------------------------------------------
# Product-level orchestration
# ---------------------------------------------------------------------------

def review_product(family: str, platform: str, *, dry_run: bool = True) -> ProductReadinessReport:
    """Build the page roster (S-90 Step 4) and classify every page (Step 5), gated by
    grade staleness (RC-W1-006 fix) and cross-checked against the latest truth-audit /
    gap-analysis reports. Always read-only against content/ and knowledge/ regardless of
    *dry_run* -- see module docstring for what dry_run actually controls."""
    repo_root = _repo_root
    manifest_path = repo_root / "reports" / "grade_manifest.json"
    manifest = load_manifest(path=manifest_path)

    truth_report_path = _find_latest_report(repo_root / "reports" / "truth-audit", family, platform)
    gap_report_path = _find_latest_report(repo_root / "reports" / "gap-analysis", family, platform)
    truth_by_file = _load_findings_by_file(truth_report_path, repo_root)
    gap_by_file = _load_findings_by_file(gap_report_path, repo_root)

    pages = _discover_pages(family, platform, repo_root)

    results = [
        classify_page_full(
            fp, repo_root=repo_root, manifest=manifest,
            truth_by_file=truth_by_file, gap_by_file=gap_by_file,
        )
        for fp in pages
    ]

    return ProductReadinessReport(
        family=family, platform=platform, dry_run=dry_run,
        evaluator_logic_version=CURRENT_LOGIC_VERSION,
        truth_audit_report=(
            str(truth_report_path.relative_to(repo_root)).replace("\\", "/")
            if truth_report_path else None
        ),
        gap_analysis_report=(
            str(gap_report_path.relative_to(repo_root)).replace("\\", "/")
            if gap_report_path else None
        ),
        results=results,
    )


def to_json_report(report: ProductReadinessReport) -> dict:
    return {
        "family": report.family,
        "platform": report.platform,
        "dry_run": report.dry_run,
        "evaluator_logic_version": report.evaluator_logic_version,
        "truth_audit_report": report.truth_audit_report,
        "gap_analysis_report": report.gap_analysis_report,
        "total_pages": report.total_pages,
        "disposition_summary": report.summary,
        "grade_status_summary": report.grade_status_summary,
        "pages": [
            {
                "filepath": r.filepath,
                "grade": r.grade,
                "grade_status": r.grade_status,
                "grade_status_detail": r.grade_status_detail,
                "raw_classification": r.raw_classification,
                "suggested_skill": r.suggested_skill,
                "disposition": r.disposition,
                "reasons": r.reasons,
                "cross_check_hits": r.cross_check_hits,
            }
            for r in report.results
        ],
    }


def _write_inspection_manifest(report: ProductReadinessReport) -> Path:
    """Write reports/publish-review/{family}-{platform}-{YYYYMMDD}/inspection-manifest.json
    per S-90 skill Step 6. Only called when --dry-run is NOT passed."""
    date_str = _now().strftime("%Y%m%d")
    out_dir = _repo_root / "reports" / "publish-review" / f"{report.family}-{report.platform}-{date_str}"
    out_path = out_dir / "inspection-manifest.json"
    payload = to_json_report(report)
    payload["inspected_at"] = _now().isoformat().replace("+00:00", "Z")
    atomic_write(out_path, json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    return out_path


def _print_text_summary(report: ProductReadinessReport, out_path: "Path | None") -> None:
    print(f"PUBLISH READINESS REVIEW -- {report.family}/{report.platform}")
    print(f"Evaluator logic version: {report.evaluator_logic_version} | "
          f"Pages inspected: {report.total_pages} | dry-run: {report.dry_run}")
    print(f"Truth-audit report used: {report.truth_audit_report or 'none found'}")
    print(f"Gap-analysis report used: {report.gap_analysis_report or 'none found'}")
    print()
    print("DISPOSITIONS:")
    for label, count in report.summary.items():
        print(f"  {label:<12} {count}")
    print()
    print("GRADE STATUS (staleness gate):")
    for label, count in sorted(report.grade_status_summary.items()):
        print(f"  {label:<28} {count}")
    stale_or_ungraded = [
        r for r in report.results
        if r.grade_status not in ("FRESH", "SKIP")
    ]
    if stale_or_ungraded:
        print()
        print(f"PAGES WITH STALE/UNVERIFIABLE GRADES ({len(stale_or_ungraded)}):")
        for r in stale_or_ungraded:
            print(f"  [{r.grade_status}] {r.filepath} (stored grade={r.grade or 'none'}) "
                  f"-> {r.disposition}: {r.grade_status_detail}")
    cross_checked = [r for r in report.results if r.cross_check_hits]
    if cross_checked:
        print()
        print(f"FRESH-GRADE PAGES DOWNGRADED BY CROSS-CHECK ({len(cross_checked)}):")
        for r in cross_checked:
            print(f"  {r.filepath} -> {r.disposition} ({len(r.cross_check_hits)} live finding(s))")
    print()
    if out_path is not None:
        print(f"Inspection manifest written: {out_path}")
    else:
        print("--dry-run: inspection manifest not written (report above only)")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: "list[str] | None" = None) -> int:
    parser = argparse.ArgumentParser(
        description="publish-readiness-review (S-90) deterministic grade-staleness + "
                     "cross-check classifier"
    )
    parser.add_argument("family")
    parser.add_argument("platform")
    parser.add_argument("--dry-run", action="store_true",
                         help="Classify and print only; do not write the inspection manifest")
    parser.add_argument("--format", choices=["text", "json"], default="text")
    args = parser.parse_args(argv)

    report = review_product(args.family, args.platform, dry_run=args.dry_run)

    out_path = None if args.dry_run else _write_inspection_manifest(report)

    if args.format == "json":
        print(json.dumps(to_json_report(report), indent=2, ensure_ascii=False))
    else:
        _print_text_summary(report, out_path)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
