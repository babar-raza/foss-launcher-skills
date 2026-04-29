"""backtrack_controller.py — Causal backtracking and forward replay orchestrator.

This module is invoked when the triage engine finds findings with cause_class
UPSTREAM_MISSING or BAD_LINK_FORMAT. It:

  1. Collects all upstream-blocked findings from a content_eval report.
  2. Calls DependencyVerifier for each broken link target.
  3. Groups verdicts and records them to evidence files.
  4. For GENERATE verdicts: emits instructions for the agent to run S-62/S-60.
  5. For CORRECT_LINK verdicts: emits instructions for the agent to run S-73.
  6. For ESCALATE verdicts: writes to the human queue; marks grade as stale.
  7. Writes a replay plan listing pages that must be re-evaluated after remediation.

NOTE: This controller writes evidence files and emits a structured action plan.
It does NOT directly invoke skills (skills are agentic, not subprocess-callable).
The agent reads the action plan and executes the required skills.

Usage (CLI):
    python -m scripts.pipeline.backtrack_controller \\
        --eval-report reports/content_eval/eval-20260403-120000.json \\
        --family slides --platform net \\
        [--dry-run] [--depth 0]

The controller writes all evidence to:
    reports/dependency-backtrack/{family}-{platform}-{YYYYMMDD-HHMMSS}/
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# Ensure repo root is on sys.path so both `python script.py` and
# `python -m scripts.pipeline.backtrack_controller` resolve imports correctly.
_PIPELINE_DIR = Path(__file__).resolve().parent          # scripts/pipeline/
_REPO_ROOT = _PIPELINE_DIR.parent.parent                  # repo root
for _p in (str(_PIPELINE_DIR), str(_REPO_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_BACKTRACK_DEPTH = 3   # configurable via --max-depth

# Stage-to-skill mapping: artifact type → (skill_id, skill_name)
_STAGE_SKILL_MAP: dict[str, tuple[str, str]] = {
    "reference.aspose.org": ("S-62", "batch-reference"),
    "docs.aspose.org":       ("S-19", "page-draft"),
    "kb.aspose.org":         ("new-kb-howto", "new-kb-howto"),
    "blog.aspose.org":       ("new-blog-post", "new-blog-post"),
    "products.aspose.org":   ("S-61", "new-products-page"),
}


# ---------------------------------------------------------------------------
# Evidence file models
# ---------------------------------------------------------------------------

@dataclass
class ActionItem:
    """A single remediation action the agent must execute."""
    action_type: str            # GENERATE | CORRECT_LINK | ESCALATE
    skill_id: str
    skill_args: str
    source_pages: list[str]     # pages that contain the broken link
    target_url: str
    target_slug: str
    correct_url: Optional[str]
    reason: str


@dataclass
class BacktrackReport:
    """Full causal backtracking report written to evidence directory."""
    run_id: str
    family: str
    platform: str
    backtrack_depth: int
    dry_run: bool
    started_at: str
    completed_at: str = ""

    failure_report: dict = field(default_factory=dict)
    cause_classifications: list[dict] = field(default_factory=list)
    dependency_verifications: list[dict] = field(default_factory=list)
    action_items: list[dict] = field(default_factory=list)
    replay_plan: list[str] = field(default_factory=list)   # pages to re-evaluate
    grade_stale_pages: list[str] = field(default_factory=list)
    escalated_pages: list[str] = field(default_factory=list)
    status: str = "pending"     # pending | complete | escalated | cycle_detected


# ---------------------------------------------------------------------------
# Controller
# ---------------------------------------------------------------------------

class BacktrackController:
    """Orchestrate causal backtracking for upstream-blocked findings."""

    # TC-3: cap visited URL set at this size (ring buffer) to bound memory and file size
    _MAX_VISITED = 500

    def __init__(
        self,
        repo_root: Path = Path("."),
        dry_run: bool = False,
        max_depth: int = MAX_BACKTRACK_DEPTH,
    ):
        self.repo_root = repo_root.resolve()
        self.dry_run = dry_run
        self.max_depth = max_depth
        self._visited: set[str] = set()   # cycle prevention; loaded from disk per run (TC-3)

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def run(
        self,
        eval_report_path: Path,
        family: str,
        platform: str,
        depth: int = 0,
    ) -> BacktrackReport:
        """Run backtracking against an eval report. Returns BacktrackReport."""
        # TC-3: load visited URLs from prior runs so we don't re-process the same URLs
        self._visited = self._load_prior_visited(family, platform)

        now = datetime.now(timezone.utc)
        run_id = f"{family}-{platform}-{now.strftime('%Y%m%d-%H%M%S')}"
        evidence_dir = (
            self.repo_root / "reports" / "dependency-backtrack" / run_id
        )
        evidence_dir.mkdir(parents=True, exist_ok=True)

        report = BacktrackReport(
            run_id=run_id,
            family=family,
            platform=platform,
            backtrack_depth=depth,
            dry_run=self.dry_run,
            started_at=now.isoformat(),
        )

        # --- Load eval report ---
        if not eval_report_path.exists():
            report.status = "escalated"
            report.completed_at = datetime.now(timezone.utc).isoformat()
            self._write_report(evidence_dir, report)
            return report

        try:
            eval_data = json.loads(eval_report_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            report.status = "escalated"
            report.completed_at = datetime.now(timezone.utc).isoformat()
            self._write_report(evidence_dir, report)
            return report

        findings = eval_data.get("findings", [])
        report.failure_report = {
            "eval_report": str(eval_report_path),
            "total_findings": len(findings),
        }

        # --- Filter upstream-blocked findings ---
        upstream_findings = [
            f for f in findings
            if f.get("cause_class") in ("UPSTREAM_MISSING", "BAD_LINK_FORMAT")
        ]

        if not upstream_findings:
            report.status = "complete"
            report.completed_at = datetime.now(timezone.utc).isoformat()
            self._write_report(evidence_dir, report)
            return report

        # Write cause classification record
        report.cause_classifications = [
            {
                "finding_id": f.get("id", ""),
                "filepath": f.get("filepath", ""),
                "cause_class": f.get("cause_class", ""),
                "message": f.get("message", ""),
                "line_no": f.get("line_no", 0),
            }
            for f in upstream_findings
        ]
        _write_json(evidence_dir / "cause-classification.json", report.cause_classifications)

        # --- Depth guard ---
        if depth >= self.max_depth:
            report.status = "escalated"
            report.grade_stale_pages = list({f.get("filepath", "") for f in upstream_findings})
            report.escalated_pages = report.grade_stale_pages
            self._write_human_queue(evidence_dir, family, platform, upstream_findings,
                                    reason=f"MAX_BACKTRACK_DEPTH ({self.max_depth}) reached")
            report.completed_at = datetime.now(timezone.utc).isoformat()
            self._write_report(evidence_dir, report)
            return report

        # --- Run DependencyVerifier for each unique broken URL ---
        from dependency_resolver import DependencyVerifier
        verifier = DependencyVerifier(repo_root=self.repo_root)

        verifications: dict[str, dict] = {}   # url → verification record
        url_to_source_pages: dict[str, list[str]] = {}

        for f in upstream_findings:
            msg = f.get("message", "")
            filepath = f.get("filepath", "")
            # Extract URL from the finding message (enclosed in backticks).
            url_match = __import__("re").search(r"`(https?://[^`]+)`", msg)
            if not url_match:
                continue
            url = url_match.group(1)
            url_to_source_pages.setdefault(url, [])
            if filepath and filepath not in url_to_source_pages[url]:
                url_to_source_pages[url].append(filepath)

            if url in self._visited:
                _write_json(evidence_dir / "cycle-detected.json", {"url": url, "depth": depth})
                continue
            if url in verifications:
                continue

            self._visited.add(url)
            result = verifier.verify(url=url, family=family, platform=platform)
            verifications[url] = asdict(result)

        report.dependency_verifications = list(verifications.values())
        _write_json(evidence_dir / "dependency-verification.json", report.dependency_verifications)

        # --- Build action items from verdicts ---
        action_items: list[ActionItem] = []
        pages_needing_replay: set[str] = set()
        grade_stale_pages: set[str] = set()
        escalated: set[str] = set()

        for url, rec in verifications.items():
            verdict = rec["verdict"]
            subdomain = rec.get("subdomain", "")
            target_slug = rec.get("target_slug", "")
            source_pages = url_to_source_pages.get(url, [])

            if verdict == "GENERATE":
                skill_id, skill_name = _STAGE_SKILL_MAP.get(
                    subdomain, ("S-62", "batch-reference")
                )
                action_items.append(ActionItem(
                    action_type="GENERATE",
                    skill_id=skill_id,
                    skill_args=f"{family} {platform} --classes {target_slug}",
                    source_pages=source_pages,
                    target_url=url,
                    target_slug=target_slug,
                    correct_url=None,
                    reason=rec["verdict_reason"],
                ))
                pages_needing_replay.update(source_pages)

            elif verdict == "CORRECT_LINK":
                correct_url = rec.get("correct_url") or ""
                action_items.append(ActionItem(
                    action_type="CORRECT_LINK",
                    skill_id="S-73",
                    skill_args=(
                        f'--scope body-wording '
                        f'--intent "Correct reference URL: replace `{url}` with `{correct_url}`"'
                    ),
                    source_pages=source_pages,
                    target_url=url,
                    target_slug=target_slug,
                    correct_url=correct_url,
                    reason=rec["verdict_reason"],
                ))
                pages_needing_replay.update(source_pages)

            else:  # ESCALATE
                escalated.update(source_pages)
                grade_stale_pages.update(source_pages)

        report.action_items = [asdict(a) for a in action_items]
        report.replay_plan = sorted(pages_needing_replay)
        report.grade_stale_pages = sorted(grade_stale_pages)
        report.escalated_pages = sorted(escalated)

        _write_json(evidence_dir / "remediation-decision.json", {
            "dry_run": self.dry_run,
            "depth": depth,
            "action_items": report.action_items,
        })
        _write_json(evidence_dir / "replay-plan.json", {
            "pages_to_reevaluate": report.replay_plan,
            "grade_stale_pages": report.grade_stale_pages,
        })

        if escalated:
            self._write_human_queue(evidence_dir, family, platform, upstream_findings,
                                    reason="DependencyVerifier returned ESCALATE")

        # --- Status ---
        if escalated and not action_items:
            report.status = "escalated"
        elif action_items:
            report.status = "complete" if not self.dry_run else "dry_run"
        else:
            report.status = "complete"

        report.completed_at = datetime.now(timezone.utc).isoformat()
        self._write_report(evidence_dir, report)

        # TC-3: persist visited URLs so future runs skip already-processed targets
        self._save_visited(family, platform)

        # Print human-readable summary to stdout
        self._print_summary(report, evidence_dir, action_items)

        return report

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _visited_state_path(self, family: str, platform: str) -> Path:
        """Canonical path for the persistent visited-URL set (TC-3)."""
        return (
            self.repo_root / "reports" / "dependency-backtrack"
            / f"{family}-{platform}-visited.json"
        )

    def _load_prior_visited(self, family: str, platform: str) -> set[str]:
        """Load the visited URL set from a prior run (TC-3)."""
        state_path = self._visited_state_path(family, platform)
        if not state_path.exists():
            return set()
        try:
            data = json.loads(state_path.read_text(encoding="utf-8"))
            return set(data.get("visited_urls", []))
        except Exception:
            return set()

    def _save_visited(self, family: str, platform: str) -> None:
        """Persist the visited URL set for cross-run cycle prevention (TC-3).

        The set is capped at _MAX_VISITED entries (oldest entries are discarded
        first when the cap is exceeded) to bound both file size and memory use.
        """
        state_path = self._visited_state_path(family, platform)
        state_path.parent.mkdir(parents=True, exist_ok=True)
        urls = list(self._visited)
        if len(urls) > self._MAX_VISITED:
            # Keep the most-recent _MAX_VISITED entries (simple truncation from front)
            urls = urls[-self._MAX_VISITED:]
        try:
            state_path.write_text(
                json.dumps({"visited_urls": sorted(urls)}, indent=2),
                encoding="utf-8",
            )
        except Exception:
            pass  # non-critical: visited state is best-effort persistence

    def _write_report(self, evidence_dir: Path, report: BacktrackReport) -> None:
        _write_json(evidence_dir / "backtrack-report.json", asdict(report))
        # Write human-readable summary markdown
        lines = [
            f"# Causal Backtrack Report — {report.run_id}",
            "",
            f"- **Family/Platform:** {report.family}/{report.platform}",
            f"- **Depth:** {report.backtrack_depth}",
            f"- **Status:** {report.status}",
            f"- **Started:** {report.started_at}",
            f"- **Completed:** {report.completed_at}",
            f"- **Dry run:** {report.dry_run}",
            "",
            "## Action Items",
            "",
        ]
        for item in report.action_items:
            lines.append(
                f"- **{item['action_type']}** `{item['target_url']}` "
                f"→ `/{item['skill_id']} {item['skill_args']}`"
            )
            for sp in item.get("source_pages", []):
                lines.append(f"  - Source page: `{sp}`")
        lines += [
            "",
            "## Replay Plan",
            "",
        ]
        for p in report.replay_plan:
            lines.append(f"- `{p}`")
        if report.grade_stale_pages:
            lines += ["", "## Grade-Stale Pages (grade_final=false)", ""]
            for p in report.grade_stale_pages:
                lines.append(f"- `{p}`")
        (evidence_dir / "backtrack-summary.md").write_text(
            "\n".join(lines), encoding="utf-8"
        )

    def _write_human_queue(
        self,
        evidence_dir: Path,
        family: str,
        platform: str,
        findings: list[dict],
        reason: str,
    ) -> None:
        today = datetime.now(timezone.utc).strftime("%Y%m%d")
        queue_path = (
            self.repo_root / "reports" / "dependency-backtrack"
            / f"needs-human-{today}.md"
        )
        entry = (
            f"\n## {family}/{platform} — {datetime.now(timezone.utc).isoformat()}\n\n"
            f"**Reason:** {reason}\n\n"
            "**Findings requiring human review:**\n\n"
        )
        for f in findings:
            entry += f"- `{f.get('filepath', '')}`: {f.get('message', '')}\n"
        entry += "\n"

        existing = queue_path.read_text(encoding="utf-8") if queue_path.exists() else (
            "# Human Review Queue — Causal Backtracking Escalations\n"
        )
        queue_path.write_text(existing + entry, encoding="utf-8")

    def _print_summary(
        self,
        report: BacktrackReport,
        evidence_dir: Path,
        action_items: list[ActionItem],
    ) -> None:
        print(f"\n{'='*60}", file=sys.stderr)
        print(f"BACKTRACK REPORT: {report.run_id}", file=sys.stderr)
        print(f"Status: {report.status}", file=sys.stderr)
        print(f"Evidence: {evidence_dir}", file=sys.stderr)
        print(f"Actions:", file=sys.stderr)
        for item in action_items:
            print(
                f"  [{item.action_type}] {item.target_url}\n"
                f"    Skill: /{item.skill_id} {item.skill_args}",
                file=sys.stderr,
            )
            for sp in item.source_pages:
                print(f"    Source: {sp}", file=sys.stderr)
        if report.grade_stale_pages:
            print(f"Grade-stale pages: {report.grade_stale_pages}", file=sys.stderr)
        if not self.dry_run and action_items:
            print(
                "\nNEXT STEPS: Execute the action items above using the listed skills.\n"
                "After all skills complete, re-run content_eval on the replay plan pages\n"
                "and update their grades with write_grade(..., grade_final=True).",
                file=sys.stderr,
            )
        print('='*60, file=sys.stderr)


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def _write_json(path: Path, data: object) -> None:
    path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run causal backtracking against a content_eval report."
    )
    parser.add_argument(
        "--eval-report", required=True,
        help="Path to an eval-*.json report from content_eval"
    )
    parser.add_argument("--family", required=True, help="Product family")
    parser.add_argument("--platform", required=True, help="Platform")
    parser.add_argument(
        "--depth", type=int, default=0,
        help="Current backtrack depth (used for recursion guard)"
    )
    parser.add_argument(
        "--max-depth", type=int, default=MAX_BACKTRACK_DEPTH,
        help=f"Maximum backtrack depth (default: {MAX_BACKTRACK_DEPTH})"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Write evidence files without invoking any skills"
    )
    parser.add_argument("--repo-root", default=".", help="Repository root")
    args = parser.parse_args()

    controller = BacktrackController(
        repo_root=Path(args.repo_root),
        dry_run=args.dry_run,
        max_depth=args.max_depth,
    )
    report = controller.run(
        eval_report_path=Path(args.eval_report),
        family=args.family,
        platform=args.platform,
        depth=args.depth,
    )

    exit_codes = {
        "complete": 0,
        "dry_run": 0,
        "escalated": 2,
        "cycle_detected": 3,
        "pending": 1,
    }
    sys.exit(exit_codes.get(report.status, 1))


if __name__ == "__main__":
    main()
