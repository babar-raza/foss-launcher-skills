"""One-off real pilot for taskcard C3 (pdf/python, per the Stage matrix's
pilot scope column): runs BOTH the real, unmodified S-120
python_verification_runner AND the new lib.example_verification.runners.
python port against the SAME real candidate (one real block from
pdf/python's actual clone-cache README) and the SAME factpack, doing a
REAL editable pip install from the real local clone cache (no PyPI
network needed -- published=False), and diffs the two results.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "scripts" / "pipeline"))
sys.path.insert(0, str(REPO_ROOT / "scripts" / "pipeline" / "lib"))
sys.path.insert(0, str(REPO_ROOT / "scripts" / "pipeline" / "commands" / "foss"))

import readme_refresh_run as rr  # noqa: E402
from example_verification.runners.python import python_verification_runner as new_runner  # noqa: E402

CANDIDATE_TEXT = (
    "## Quick Start\n\n"
    "```python\n"
    "from aspose_pdf import Document\n\n"
    "with Document() as document:\n"
    "    page = document.pages.add()\n"
    "    page.add_text(\n"
    "        \"Hello from Aspose.PDF FOSS!\",\n"
    "        x=72,\n"
    "        y=720,\n"
    "        font_size=18,\n"
    "    )\n"
    "    document.save(\"hello.pdf\")\n"
    "```\n"
)


def main() -> int:
    import tempfile
    candidate_dir = Path(tempfile.mkdtemp(prefix="c3-pilot-"))
    candidate_path = candidate_dir / "candidate.md"
    candidate_path.write_text(CANDIDATE_TEXT, encoding="utf-8")

    factpack = {
        "family": "pdf", "platform": "python",
        "install": {"published": False, "candidate": {"name": "aspose-pdf-foss-for-python"}},
    }

    print("Running OLD (real S-120 rr.python_verification_runner)...", file=sys.stderr)
    old_result = rr.python_verification_runner(candidate_path, factpack)

    print("Running NEW (lib.example_verification.runners.python)...", file=sys.stderr)
    new_result = new_runner(candidate_path, factpack)

    print(json.dumps({"old": old_result, "new": new_result, "identical": old_result == new_result}, indent=2))
    return 0 if old_result == new_result else 1


if __name__ == "__main__":
    raise SystemExit(main())
