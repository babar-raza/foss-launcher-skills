"""One-off real pilot for taskcard C3 (pdf/typescript): runs BOTH the
real, unmodified S-120 typescript_verification_runner AND the new
lib.example_verification.runners.typescript port against the SAME real
candidate (the one real block from pdf/typescript's actual clone-cache
README) and the SAME factpack, doing a REAL npm install against the real
local clone cache, and diffs the two results.
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
from example_verification.runners.typescript import typescript_verification_runner as new_runner  # noqa: E402

CANDIDATE_TEXT = (
    "## Quick Start\n\n"
    "```typescript\n"
    "import { Document } from '@asposefoss/pdf';\n"
    "const doc = Document.OpenFile('in.pdf');\n"
    "const svg = doc.Pages[0].ToSvg();\n"
    "```\n"
)


def main() -> int:
    import tempfile
    candidate_dir = Path(tempfile.mkdtemp(prefix="c3-pilot-ts-"))
    candidate_path = candidate_dir / "candidate.md"
    candidate_path.write_text(CANDIDATE_TEXT, encoding="utf-8")

    factpack = {"family": "pdf", "platform": "typescript"}

    print("Running OLD (real S-120 rr.typescript_verification_runner)...", file=sys.stderr)
    old_result = rr.typescript_verification_runner(candidate_path, factpack)

    print("Running NEW (lib.example_verification.runners.typescript)...", file=sys.stderr)
    new_result = new_runner(candidate_path, factpack)

    print(json.dumps({"old": old_result, "new": new_result, "identical": old_result == new_result}, indent=2))
    return 0 if old_result == new_result else 1


if __name__ == "__main__":
    raise SystemExit(main())
