"""install_literal_sweep.py — ST-054 TC-09
(plans/from_backlog/2026-08-16-st-054-inline-install-command-remediation.md).

Recurring full-corpus sweep for literal (non-shortcode) package-install-command
text -- the durability half of ST-054: every prior sweep (MT015 TC-MT015-12,
MT018 TC-MT018-08/10, this mission's own TC-04) was an ad hoc, manually-run
mission pass. Without a SCHEDULED check, this defect class can silently regrow
to thousands of occurrences again before anyone notices (the exact history
this mission itself exists to close out).

A deliberate sibling of package_publish_watch.py, not an extension of it:
publish_watch.py's job is detecting registry-state changes (a package that
newly resolves, a version bump); this module's job is a content-quality sweep
(does the corpus still literally embed install commands instead of using the
shortcode system) -- a different domain and a much heavier, slower operation
(full-corpus, not just changed entries), better run on its own schedule
(weekly, not daily -- see the governing plan's own §O cadence design) than
folded into publish_watch.py's existing scope.

Reuses verify_package_install_literals() (audit/package_install_literal.py,
TC-MT015-05/TC-MT015-02/ST-054 TC-02) unchanged -- this module only adds the
corpus-iteration, aggregation, and issue-filing wrapper around it.

CLI:
    PYTHONPATH=scripts/pipeline .venv/Scripts/python -m commands.ops.install_literal_sweep
    PYTHONPATH=scripts/pipeline .venv/Scripts/python -m commands.ops.install_literal_sweep --issue-body-out /tmp/issue-body.md
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_PIPELINE_ROOT = Path(__file__).resolve().parents[2]
if str(_PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_ROOT))
_LIB_DIR = str(_PIPELINE_ROOT / "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)

from audit.package_install_literal import verify_package_install_literals  # noqa: E402
from package_registry_data import load_registry  # noqa: E402

_DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[4]
_REPO_ROOT = _DEFAULT_REPO_ROOT
_CONTENT_ROOT = _REPO_ROOT / "content"
_DATA_PATH = _REPO_ROOT / "data" / "package_registry.json"

# Same 4 registries package_install_literal.py covers directly -- maven/cargo
# have their own dedicated gate (maven_coordinates.py), out of this sweep's
# scope, matching every other tool in this mission.
_TRACKED_REGISTRY_TYPES = {"pypi", "nuget", "npm", "go_modules"}

_LOCALE_DIR_SITES = ("docs.aspose.org", "kb.aspose.org", "products.aspose.org")
_LOCALE_SUFFIX_SITES = ("blog.aspose.org",)


def configure(*, repo_root: "Path | str | None" = None) -> None:
    global _REPO_ROOT, _CONTENT_ROOT, _DATA_PATH
    _REPO_ROOT = Path(repo_root) if repo_root is not None else _DEFAULT_REPO_ROOT
    _CONTENT_ROOT = _REPO_ROOT / "content"
    _DATA_PATH = _REPO_ROOT / "data" / "package_registry.json"


def _files_for(family: str, platform: str) -> list[Path]:
    """Every content file for family/platform across all 4 in-scope subsites,
    all locales -- same discovery method as TC-04's sweep and
    package_install_migrator.py's discover_files()."""
    out: list[Path] = []
    for site in _LOCALE_DIR_SITES:
        base = _CONTENT_ROOT / site
        if not base.is_dir():
            continue
        for locale_dir in base.iterdir():
            if not locale_dir.is_dir():
                continue
            target = locale_dir / family / platform
            if target.is_dir():
                out.extend(sorted(target.rglob("*.md")))
    for site in _LOCALE_SUFFIX_SITES:
        target = _CONTENT_ROOT / site / family / platform
        if target.is_dir():
            out.extend(sorted(target.rglob("*.md")))
    return out


def run_sweep(*, registry: "dict[str, Any] | None" = None) -> dict[str, Any]:
    """Sweep every family/platform tracked in the package registry with a
    covered registry_type, across the full corpus. Pure with respect to the
    filesystem it's given (no writes) -- returns an aggregate report."""
    data = registry if registry is not None else load_registry(_DATA_PATH)

    per_product: list[dict[str, Any]] = []
    total_files_checked = 0
    total_files_with_findings = 0
    total_findings = 0

    for family, platforms in sorted(data.items()):
        if not isinstance(platforms, dict):
            continue
        for platform, entry in sorted(platforms.items()):
            if not isinstance(entry, dict):
                continue
            if entry.get("registry_type") not in _TRACKED_REGISTRY_TYPES:
                continue
            files = _files_for(family, platform)
            files_with_findings = 0
            findings_count = 0
            sample_findings: list[dict[str, Any]] = []
            for fp in files:
                findings = verify_package_install_literals(fp, family, platform, registry=data)
                if findings:
                    files_with_findings += 1
                    findings_count += len(findings)
                    if len(sample_findings) < 3:
                        rel = str(fp.relative_to(_REPO_ROOT)) if fp.is_relative_to(_REPO_ROOT) else str(fp)
                        sample_findings.append({"path": rel, "message": findings[0].message})
            per_product.append({
                "family": family, "platform": platform,
                "registry_type": entry.get("registry_type"),
                "published": bool(entry.get("verification", {}).get("published")),
                "files_checked": len(files), "files_with_findings": files_with_findings,
                "findings": findings_count, "sample_findings": sample_findings,
            })
            total_files_checked += len(files)
            total_files_with_findings += files_with_findings
            total_findings += findings_count

    return {
        "per_product": per_product,
        "total_files_checked": total_files_checked,
        "total_files_with_findings": total_files_with_findings,
        "total_findings": total_findings,
    }


def format_issue_body(report: dict[str, Any]) -> str:
    lines = [
        "# ST-054 recurring literal-install-command sweep",
        "",
        f"Total: {report['total_files_checked']} files checked, "
        f"{report['total_files_with_findings']} files with findings, "
        f"**{report['total_findings']} total findings**.",
        "",
        "| Family/Platform | Files checked | Files w/ findings | Findings |",
        "|---|---|---|---|",
    ]
    for p in report["per_product"]:
        if p["findings"] == 0:
            continue
        lines.append(
            f"| {p['family']}/{p['platform']} | {p['files_checked']} | "
            f"{p['files_with_findings']} | {p['findings']} |"
        )
    lines.append("")
    lines.append("## Sample findings (first 3 per affected product)")
    lines.append("")
    for p in report["per_product"]:
        if p["findings"] == 0:
            continue
        lines.append(f"### {p['family']}/{p['platform']}")
        for s in p["sample_findings"]:
            lines.append(f"- `{s['path']}`: {s['message']}")
        lines.append("")
    lines.append(
        "This defect class was the subject of ST-054 "
        "(plans/from_backlog/2026-08-16-st-054-inline-install-command-remediation.md) -- "
        "if this count has grown significantly since that mission's closeout, treat it as a "
        "regression needing the same remediation approach (package-install-inline shortcode + "
        "S-75 locale propagation), not a fresh investigation from scratch."
    )
    return "\n".join(lines)


def _git(*args: str) -> "str | None":
    """Best-effort git call against _REPO_ROOT -- returns None (never raises)
    on any failure, including when _REPO_ROOT isn't a git worktree at all
    (e.g. test fixtures under tmp_path). Provenance is an honesty aid, not a
    hard requirement -- a sweep must still run without it."""
    try:
        result = subprocess.run(
            ["git", *args], cwd=str(_REPO_ROOT), capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def build_provenance() -> dict[str, Any]:
    """ST-054 TC-17: no prior sweep run has ever recorded the git state it
    measured against -- three same-day counts (6,522 / 6,248 / 6,454) were
    reported with nothing pinning what was actually measured, during a
    session with 9 other concurrent agents mutating content/. This makes any
    two sweep reports honestly comparable (or honestly flagged as not
    comparable, if the tree was dirty when either ran)."""
    sha = _git("rev-parse", "HEAD")
    dirty_content_files = None
    porcelain = _git("status", "--porcelain", "--", "content")
    if porcelain is not None:
        dirty_content_files = len([line for line in porcelain.splitlines() if line.strip()])
    return {
        "base_sha": sha,
        "base_sha_short": sha[:12] if sha else None,
        "dirty_content_files": dirty_content_files,
        "tree_dirty_in_content": bool(dirty_content_files),
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def format_report_markdown(record: dict[str, Any]) -> str:
    """Full audit-trail rendering -- unlike format_issue_body() (which skips
    clean products to keep a GitHub issue focused), this includes every
    tracked family/platform, matching TC-04's original persisted-report
    style, plus the provenance block that makes this report comparable to
    future ones."""
    prov = record["provenance"]
    report = record["report"]
    lines = [
        "# ST-054 literal-install-command sweep",
        "",
        f"- Generated: {prov['generated_at']}",
        f"- base_sha: `{prov['base_sha'] or 'UNKNOWN (not a git worktree)'}`",
        f"- Working tree dirty inside content/: {prov['tree_dirty_in_content']} "
        f"({prov['dirty_content_files'] if prov['dirty_content_files'] is not None else 'unknown'} files) "
        "-- a dirty tree means this count may not be directly comparable to a report "
        "generated against a different tree state, even at the same base_sha.",
        "",
        f"Total: {report['total_files_checked']} files checked, "
        f"{report['total_files_with_findings']} files with findings, "
        f"**{report['total_findings']} total findings**.",
        "",
        "| Family/Platform | Registry | Published | Files checked | Files w/ findings | Findings |",
        "|---|---|---|---|---|---|",
    ]
    for p in report["per_product"]:
        lines.append(
            f"| {p['family']}/{p['platform']} | {p.get('registry_type', '?')} | "
            f"{p.get('published', '?')} | {p['files_checked']} | "
            f"{p['files_with_findings']} | {p['findings']} |"
        )
    lines.append("")
    lines.append("## Sample findings (first 3 per affected product)")
    lines.append("")
    for p in report["per_product"]:
        if p["findings"] == 0:
            continue
        lines.append(f"### {p['family']}/{p['platform']}")
        for s in p["sample_findings"]:
            lines.append(f"- `{s['path']}`: {s['message']}")
        lines.append("")
    return "\n".join(lines)


_DEFAULT_REPORT_DIR_NAME = Path("reports") / "audit" / "st054"


def write_report(report: dict[str, Any], *, out_dir: "Path | None" = None) -> dict[str, Any]:
    """Persist a sweep result durably -- every invocation, not gated behind
    --issue-body-out (which previously pointed CI at ephemeral /tmp, leaving
    zero artifacts in the repo for any sweep, scheduled or manual). Returns
    the full record (provenance + report) plus the paths written."""
    provenance = build_provenance()
    record = {"provenance": provenance, "report": report}

    target_dir = out_dir if out_dir is not None else (_REPO_ROOT / _DEFAULT_REPORT_DIR_NAME)
    target_dir.mkdir(parents=True, exist_ok=True)

    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    sha_part = provenance["base_sha_short"] or "nogit"
    stem = f"sweep-{ts}-{sha_part}"
    json_path = target_dir / f"{stem}.json"
    md_path = target_dir / f"{stem}.md"

    json_path.write_text(json.dumps(record, indent=2, sort_keys=True), encoding="utf-8")
    md_path.write_text(format_report_markdown(record), encoding="utf-8")

    record["json_path"] = str(json_path)
    record["md_path"] = str(md_path)
    return record


def _write_github_output(key: str, value: str) -> None:
    """Best-effort write to $GITHUB_OUTPUT if running inside a GitHub Actions
    step; a no-op (never raises) outside that environment. Mirrors
    package_publish_watch.py's own helper of the same name."""
    path = os.environ.get("GITHUB_OUTPUT")
    if not path:
        return
    with open(path, "a", encoding="utf-8") as f:
        f.write(f"{key}={value}\n")


def main(argv: "list[str] | None" = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(prog="install_literal_sweep")
    parser.add_argument("--issue-body-out", metavar="PATH", help="Write the issue body to this path if any findings are found")
    parser.add_argument(
        "--report-dir", metavar="PATH",
        help=f"Directory to persist the durable JSON+MD report into "
             f"(default: repo_root/{_DEFAULT_REPORT_DIR_NAME.as_posix()})",
    )
    parser.add_argument(
        "--no-persist", action="store_true",
        help="Skip writing the durable report (ST-054 TC-17 default is to always persist; "
             "use this only for a throwaway/manual check).",
    )
    args = parser.parse_args(argv)

    report = run_sweep()
    print(f"files_checked={report['total_files_checked']} "
          f"files_with_findings={report['total_files_with_findings']} "
          f"total_findings={report['total_findings']}")

    if not args.no_persist:
        out_dir = Path(args.report_dir) if args.report_dir else None
        record = write_report(report, out_dir=out_dir)
        print(f"report_json={record['json_path']}")
        print(f"report_md={record['md_path']}")
        if not record["provenance"]["base_sha"]:
            print("WARNING: could not resolve git HEAD -- report has no base_sha provenance", file=sys.stderr)
        elif record["provenance"]["tree_dirty_in_content"]:
            print(
                f"WARNING: working tree has "
                f"{record['provenance']['dirty_content_files']} dirty file(s) under content/ -- "
                "this count may not be directly comparable to a report from a clean tree",
                file=sys.stderr,
            )

    if report["total_findings"] == 0:
        _write_github_output("has_findings", "false")
        return 0

    _write_github_output("has_findings", "true")
    if args.issue_body_out:
        Path(args.issue_body_out).write_text(format_issue_body(report), encoding="utf-8")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
