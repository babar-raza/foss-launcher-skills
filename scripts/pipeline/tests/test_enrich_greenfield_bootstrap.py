"""Regression test for TC-03/G-03 (MT009 SEED-04): knowledge-enrich (S-37)
must not fail on a greenfield product where scout/ exists but merged/
does not -- exactly the state at S-37's position in the documented
first-time bootstrap chain (S-34 -> S-37 -> S-35).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
_ENRICH_SCRIPT = _REPO_ROOT / "scripts" / "pipeline" / "commands" / "knowledge" / "enrich.py"


def test_greenfield_bootstrap_no_merged_dir_does_not_prerequisite_fail(tmp_path):
    """scout/api_surface.json present, merged/ absent -> must NOT print
    PREREQUISITE FAILED or exit non-zero due to the removed require_all() check.
    """
    knowledge_root = tmp_path / "knowledge"
    scout_dir = knowledge_root / "testfam" / "testplat" / "scout"
    scout_dir.mkdir(parents=True)
    (scout_dir / "api_surface.json").write_text("[]", encoding="utf-8")
    (scout_dir / "claims.json").write_text(json.dumps({"claims": []}), encoding="utf-8")
    # merged/ deliberately does not exist -- this is the greenfield bootstrap state.
    assert not (knowledge_root / "testfam" / "testplat" / "merged").exists()

    result = subprocess.run(
        [sys.executable, str(_ENRICH_SCRIPT), "testfam", "testplat",
         "--knowledge-root", str(knowledge_root), "--no-llm"],
        cwd=str(_REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=60,
    )

    combined = result.stdout + result.stderr
    assert "PREREQUISITE FAILED" not in combined, (
        f"enrich.py must not fail the removed require_all() precondition check "
        f"on a greenfield product (merged/ not yet created). Output:\n{combined}"
    )
    assert result.returncode == 0, (
        f"enrich.py should succeed with --no-llm on a valid scout/ dir even "
        f"without merged/. Output:\n{combined}"
    )
