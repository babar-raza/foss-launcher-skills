"""Tests for scripts/ci/checks/check_contract_claims.py (HARDEN-A9).

Proves the checker is not vacuously "always clean": it must actually flag a
constructed false claim, and must NOT flag a true one, against real files it
resolves via the repo's own scripts/pipeline tree.
"""
from __future__ import annotations

import sys
from pathlib import Path

_CHECKS_DIR = Path(__file__).resolve().parent.parent / "checks"
if str(_CHECKS_DIR) not in sys.path:
    sys.path.insert(0, str(_CHECKS_DIR))

import check_contract_claims as ccc  # noqa: E402


def test_true_claim_not_flagged(tmp_path):
    """check_grade_downgrade.py genuinely imports from no_downgrade_guard —
    a claim naming that real relationship must NOT be flagged."""
    md = tmp_path / "true_claim.md"
    md.write_text("check_grade_downgrade.py uses no_downgrade_guard.py for the decision matrix.\n",
                  encoding="utf-8")
    findings = ccc.scan_file(md)
    assert findings == [], findings


def test_false_claim_is_flagged(tmp_path):
    """change_guard.py does NOT import/invoke no_downgrade_guard.py (verified
    false during the 2026-07-22 audit) — a claim asserting it must be flagged.
    This is exactly the shape of the real bug this checker exists to catch."""
    md = tmp_path / "false_claim.md"
    md.write_text("change_guard.py calls no_downgrade_guard.py before writing.\n",
                  encoding="utf-8")
    findings = ccc.scan_file(md)
    assert len(findings) == 1
    assert findings[0]["subject"] == "change_guard.py"
    assert findings[0]["object"] == "no_downgrade_guard.py"


def test_unresolvable_subject_does_not_false_flag(tmp_path):
    """A claim about a file that doesn't exist in scripts/pipeline (typo, or a
    file outside the pipeline tree) can't be contradicted — must not flag."""
    md = tmp_path / "unknown.md"
    md.write_text("totally_made_up_script.py calls no_downgrade_guard.py.\n",
                  encoding="utf-8")
    findings = ccc.scan_file(md)
    assert findings == []


def test_non_file_gated_on_claim_is_advisory_not_hard(tmp_path):
    """finding-2 remediation: an 'is gated on <prose>' claim (not two .py
    files — the exact shape of the original refresh-product.md bug) is no
    longer silently dropped. It's surfaced as an UNVERIFIABLE_PROSE_CLAIM
    advisory finding, but must NOT be treated as a hard FALSE_CLAIM (it can't
    be machine-verified, so it must never block a commit on its own)."""
    md = tmp_path / "prose.md"
    md.write_text("S-76 is gated on manifest validation == PASS (schema 5e).\n",
                  encoding="utf-8")
    findings = ccc.scan_file(md)
    assert len(findings) == 1
    assert findings[0]["kind"] == "UNVERIFIABLE_PROSE_CLAIM"
    assert findings[0]["subject"] == "S-76"
    assert "schema 5e" in findings[0]["object"]

    # Advisory-only: main() must still exit 0 for a file with ONLY this claim.
    rc = ccc.main(["--paths", str(md)])
    assert rc == 0


def test_calls_uses_verbs_are_not_advisory_flagged(tmp_path):
    """Only 'is gated on' generates the prose advisory — 'calls'/'invokes'/
    'uses' claims with a non-.py object stay fully out of scope, per the
    original design (too broad a net otherwise: nearly every skill doc says
    'X uses Y' about non-code things)."""
    md = tmp_path / "prose2.md"
    md.write_text("The launch skill uses careful judgement throughout.\n",
                  encoding="utf-8")
    findings = ccc.scan_file(md)
    assert findings == []


def test_known_human_gates_excluded_from_advisory(tmp_path):
    """'is gated on human/manual/editorial review' etc. is a legitimate
    non-code gate, not a claim about pipeline enforcement — must not be
    flagged at all (avoids drowning real signal in routine editorial prose)."""
    md = tmp_path / "human_gate.md"
    md.write_text(
        "S-90 is gated on human review of the final draft.\n"
        "S-91 is gated on manual sign-off from the maintainer.\n"
        "S-92 is gated on editorial approval before publish.\n",
        encoding="utf-8",
    )
    findings = ccc.scan_file(md)
    assert findings == []


def test_gated_on_py_object_stays_hard_checkable_only(tmp_path):
    """A claim whose object DOES end in .py must still go through the hard,
    verifiable path (already covered by test_false_claim_is_flagged) and must
    NOT also produce a duplicate advisory entry for the same line."""
    md = tmp_path / "mixed.md"
    md.write_text("change_guard.py is gated on no_downgrade_guard.py.\n",
                  encoding="utf-8")
    findings = ccc.scan_file(md)
    assert len(findings) == 1
    assert findings[0]["kind"] == "FALSE_CLAIM"


def test_real_repo_registry_and_refresh_product_are_clean():
    """Regression guard for the two ACTUAL findings this checker was built to
    catch: registry.yaml's change_guard.py claim and refresh-product.md's S-76
    gating claim were both corrected during HARDEN-A9. Scanning the real repo
    files must report zero HARD findings now (the corrected refresh-product.md
    text no longer uses "is gated on" at all, so it produces no advisory
    entries either — asserted here as a documented baseline, not just assumed,
    so a future prose claim slipping back in in this exact shape is caught)."""
    findings = ccc.scan(ccc._DEFAULT_GLOBS)
    hard = [f for f in findings if f.get("kind", "FALSE_CLAIM") == "FALSE_CLAIM"]
    advisory = [f for f in findings if f.get("kind") == "UNVERIFIABLE_PROSE_CLAIM"]
    assert hard == [], hard
    assert advisory == [], advisory


def test_cli_exit_code_reflects_findings(tmp_path, monkeypatch, capsys):
    md = tmp_path / "false_claim.md"
    md.write_text("change_guard.py calls no_downgrade_guard.py.\n", encoding="utf-8")
    rc = ccc.main(["--paths", str(md)])
    assert rc == 1
    err = capsys.readouterr().err
    assert "CONTRACT_CLAIM_DRIFT" in err

    clean = tmp_path / "clean.md"
    clean.write_text("Nothing to see here.\n", encoding="utf-8")
    rc2 = ccc.main(["--paths", str(clean)])
    assert rc2 == 0
