"""Fix orchestration runner — batches fixes by file, applies in deterministic order."""

from __future__ import annotations

import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..models import Finding, Page
from .fixers import get_fixer
from .triage import TriagedFinding


def _log(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)


@dataclass(slots=True)
class FixResult:
    """Result of applying a single fix."""

    finding_id: str
    filepath: str
    fixer_name: str
    action: str         # fixed, skipped, deferred_llm, deferred_human, error
    description: str
    diff_preview: str = ""


# Deterministic fixer execution order — frontmatter first, then body
_FIXER_ORDER = [
    "frontmatter_type",
    "frontmatter_author",
    "frontmatter_categories",
    "frontmatter_layout",
    "code_fence_lang",
    "placeholder_remove",
    "steps_shortcode",
    "evidence_attach",  # always last (subprocess, needs file on disk)
]


def _build_meta(filepath: Path) -> dict[str, Any]:
    """Build fixer metadata dict from filepath, using Page._infer_metadata logic."""
    page = Page(filepath=filepath, raw_text="")
    page._infer_metadata()
    return {
        "filepath": str(filepath),
        "family": page.family,
        "platform": page.platform,
        "subdomain": page.subdomain,
        "page_role": page.page_role,
    }


def run_fixes(
    triaged: list[TriagedFinding],
    *,
    dry_run: bool = False,
    categories: set[str] | None = None,
) -> list[FixResult]:
    """Apply auto-fixable findings grouped by file.

    Args:
        triaged: List of auto-fixable TriagedFindings.
        dry_run: If True, report what would change without writing files.
        categories: If set, only fix findings in these categories.

    Returns:
        List of FixResult for each finding processed.
    """
    results: list[FixResult] = []

    # Filter to auto-fixable only
    auto = [t for t in triaged if t.fix_type == "auto"]
    if categories:
        auto = [t for t in auto if t.finding.category in categories]

    # Group by filepath
    by_file: dict[str, list[TriagedFinding]] = defaultdict(list)
    for t in auto:
        by_file[t.finding.filepath].append(t)

    _log(f"Fixing {len(auto)} findings across {len(by_file)} files"
         f"{' (dry-run)' if dry_run else ''}")

    for filepath_str, file_triaged in sorted(by_file.items()):
        filepath = Path(filepath_str)
        if not filepath.exists():
            for t in file_triaged:
                results.append(FixResult(
                    finding_id=t.finding.id,
                    filepath=filepath_str,
                    fixer_name=t.fixer_name,
                    action="error",
                    description=f"File not found: {filepath_str}",
                ))
            continue

        meta = _build_meta(filepath)
        page_text = filepath.read_text(encoding="utf-8")
        original_text = page_text
        post_step_findings: list[TriagedFinding] = []

        # Sort findings by fixer execution order
        order_map = {name: i for i, name in enumerate(_FIXER_ORDER)}
        sorted_findings = sorted(
            file_triaged,
            key=lambda t: order_map.get(t.fixer_name, 999),
        )

        for tf in sorted_findings:
            fixer_cls = get_fixer(tf.fixer_name)
            fixer = fixer_cls()

            # Check if this is a post-step fixer (e.g. evidence_attach)
            if getattr(fixer, "is_post_step", False):
                post_step_findings.append(tf)
                continue

            if not fixer.can_fix(tf.finding, page_text, meta):
                results.append(FixResult(
                    finding_id=tf.finding.id,
                    filepath=filepath_str,
                    fixer_name=tf.fixer_name,
                    action="skipped",
                    description="Fixer determined fix not applicable",
                ))
                continue

            if dry_run:
                results.append(FixResult(
                    finding_id=tf.finding.id,
                    filepath=filepath_str,
                    fixer_name=tf.fixer_name,
                    action="would_fix",
                    description=f"[dry-run] {tf.reason}",
                ))
                continue

            new_text = fixer.apply(tf.finding, page_text, meta)
            if new_text != page_text:
                # Build a minimal diff preview
                diff = _diff_preview(page_text, new_text, tf.finding.line_no)
                page_text = new_text
                results.append(FixResult(
                    finding_id=tf.finding.id,
                    filepath=filepath_str,
                    fixer_name=tf.fixer_name,
                    action="fixed",
                    description=tf.reason,
                    diff_preview=diff,
                ))
            else:
                results.append(FixResult(
                    finding_id=tf.finding.id,
                    filepath=filepath_str,
                    fixer_name=tf.fixer_name,
                    action="skipped",
                    description="No change after apply (already fixed or not applicable)",
                ))

        # Write file if changed (before post-step fixers)
        if page_text != original_text and not dry_run:
            filepath.write_text(page_text, encoding="utf-8")
            _log(f"  wrote {filepath_str}")

        # Run post-step fixers (e.g. evidence_attach subprocess)
        for tf in post_step_findings:
            if dry_run:
                results.append(FixResult(
                    finding_id=tf.finding.id,
                    filepath=filepath_str,
                    fixer_name=tf.fixer_name,
                    action="would_fix",
                    description=f"[dry-run] {tf.reason}",
                ))
                continue

            fixer_cls = get_fixer(tf.fixer_name)
            fixer = fixer_cls()
            if fixer.can_fix(tf.finding, page_text, meta):
                fixer.apply(tf.finding, page_text, meta)
                results.append(FixResult(
                    finding_id=tf.finding.id,
                    filepath=filepath_str,
                    fixer_name=tf.fixer_name,
                    action="fixed",
                    description=tf.reason,
                ))
            else:
                results.append(FixResult(
                    finding_id=tf.finding.id,
                    filepath=filepath_str,
                    fixer_name=tf.fixer_name,
                    action="skipped",
                    description="Evidence attach not applicable",
                ))

    return results


def _diff_preview(old: str, new: str, line_hint: int) -> str:
    """Generate a compact diff preview around the changed area."""
    old_lines = old.split("\n")
    new_lines = new.split("\n")

    # Find first difference
    first_diff = 0
    for i, (a, b) in enumerate(zip(old_lines, new_lines)):
        if a != b:
            first_diff = i
            break
    else:
        if len(old_lines) != len(new_lines):
            first_diff = min(len(old_lines), len(new_lines))

    # Show 1 line of context
    start = max(0, first_diff - 1)
    end = min(max(len(old_lines), len(new_lines)), first_diff + 3)

    parts = []
    for i in range(start, min(end, len(old_lines))):
        if i < len(new_lines) and old_lines[i] != new_lines[i]:
            parts.append(f"-{old_lines[i]}")
            parts.append(f"+{new_lines[i]}")
        elif i < len(new_lines):
            parts.append(f" {old_lines[i]}")
        else:
            parts.append(f"-{old_lines[i]}")

    # Show any added lines
    if len(new_lines) > len(old_lines):
        for i in range(len(old_lines), min(end, len(new_lines))):
            parts.append(f"+{new_lines[i]}")

    return "\n".join(parts[:8])  # cap at 8 lines
