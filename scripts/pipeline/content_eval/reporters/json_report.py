"""JSON report generator."""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone

from ..models import EvalReport
from ..remediation.planner import RemediationBatch


def generate_json(report: EvalReport,
                  remediation: list[RemediationBatch] | None = None) -> str:
    """Generate a machine-readable JSON report."""
    now = datetime.now(timezone.utc).isoformat()

    cat_counts = Counter(f.category for f in report.findings)
    level_counts = Counter(f.level for f in report.findings)

    data = {
        "schema_version": 1,
        "generated_at": now,
        "scope": report.scope,
        "summary": {
            "total_findings": len(report.findings),
            "pages_evaluated": report.pages_evaluated,
            "evaluators_run": report.evaluators_run,
            "by_severity": {
                "FAIL": level_counts.get("FAIL", 0),
                "WARN": level_counts.get("WARN", 0),
                "INFO": level_counts.get("INFO", 0),
            },
            "by_category": dict(cat_counts),
            "pages_clean": report.pages_evaluated - len(report.by_file()),
            "pages_with_findings": len(report.by_file()),
        },
        "findings": [
            {
                "id": f.id,
                "level": f.level,
                "category": f.category,
                "file": f.filepath,
                "line": f.line_no,
                "message": f.message,
                "suggestion": f.suggestion,
                "evaluator": f.evaluator,
            }
            for f in report.findings
        ],
    }

    if remediation:
        data["remediation"] = [
            {
                "priority": b.priority,
                "description": b.description,
                "files": b.files,
                "estimated_effort": b.estimated_effort,
                "post_actions": b.post_actions,
                "finding_count": len(b.findings),
            }
            for b in remediation
        ]

    return json.dumps(data, indent=2, ensure_ascii=False)
