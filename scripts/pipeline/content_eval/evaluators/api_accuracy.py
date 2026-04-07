"""API accuracy evaluator — wraps audit.py's token verification.

Architectural boundary (Phase 7 / Option A)
-------------------------------------------
This module is the **explicit bridge** between the two evaluation systems:

- ``audit/`` (verification layer): fast CI gate, emits ``token_ops.Finding``
- ``content_eval/`` (quality layer): rubric-driven scoring, emits ``models.Finding``

This evaluator calls ``extract_tokens`` + ``verify_tokens`` from the audit layer
and converts the results into ``content_eval`` Finding objects so they appear in
the quality report alongside all other rubric dimensions.

Remediation: ``remediate.py`` acts on ``content_eval`` findings, including those
produced here.  Audit-layer findings that bypass this bridge are **not**
remediated — they are CI-blocking gates only.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from ..models import Finding, Page
from . import BaseEvaluator

# Import audit.py machinery
# sibling-import guard: content_eval sub-package needs the pipeline root for knowledge_core/token_ops imports
_HERE = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_HERE))

from knowledge_core import Knowledge  # noqa: E402
from evidence_verifier import verify_evidence  # noqa: E402  (R-3b: was knowledge_core)
from token_ops import extract_tokens, verify_tokens  # noqa: E402


class ApiAccuracyEvaluator(BaseEvaluator):
    """Verifies API tokens in content against knowledge model.

    Delegates to audit.py's extract_tokens + verify_tokens for deterministic
    API accuracy checking. Also validates evidence frontmatter via verify_evidence.
    """

    name = "api_accuracy"

    def evaluate(self, page: Page, knowledge: Any) -> list[Finding]:
        if not isinstance(knowledge, Knowledge) or not knowledge.available:
            return []

        findings: list[Finding] = []

        # Extract and verify API tokens
        tokens = extract_tokens(page.filepath, page.platform)
        audit_findings = verify_tokens(tokens, knowledge, page.filepath)

        # Verify evidence frontmatter
        audit_findings.extend(verify_evidence(page.frontmatter, knowledge, page.filepath))

        # Convert audit.Finding → content_eval.Finding
        for af in audit_findings:
            findings.append(Finding(
                level=af.level,
                category="AA",
                filepath=str(af.filepath),
                line_no=af.line_no,
                message=af.message,
                suggestion=af.suggestion,
                evaluator=self.name,
            ))

        return findings
