"""Fixer: attach evidence block via ``attach_evidence.py`` subprocess.

Rather than reimplementing evidence generation, this fixer shells out to
the existing deterministic ``attach_evidence.py`` script. It runs *after*
all other fixers for a given file have been applied and the file written.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from ...models import Finding
from . import BaseFixer

_FM_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


class EvidenceAttachFixer(BaseFixer):
    name = "evidence_attach"
    categories = {"EG"}

    # This fixer is special: it runs as a post-step subprocess,
    # not an in-memory text transformation.
    is_post_step = True

    def can_fix(self, finding: Finding, page_text: str, meta: dict[str, Any]) -> bool:
        msg = finding.message.lower()
        if "evidence" not in msg:
            return False
        # Must have family/platform to look up knowledge
        if not meta.get("family") or not meta.get("platform"):
            return False
        return True

    def apply(self, finding: Finding, page_text: str, meta: dict[str, Any]) -> str:
        """Run attach_evidence.py as subprocess. Returns original text unchanged.

        The actual modification is done by the subprocess writing to the file.
        The runner must write pending text changes before calling this fixer,
        then re-read the file afterward.
        """
        filepath = meta.get("filepath", "")
        if not filepath:
            return page_text

        script = Path(__file__).resolve().parents[3] / "attach_evidence.py"
        if not script.exists():
            return page_text

        try:
            subprocess.run(
                [sys.executable, str(script), "--files", str(filepath), "--force"],
                capture_output=True,
                text=True,
                timeout=60,
            )
        except (subprocess.TimeoutExpired, OSError):
            pass  # Non-fatal — evidence attachment is best-effort

        return page_text
