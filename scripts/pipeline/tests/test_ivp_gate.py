"""Tests for ivp_gate.py (MT074 B20): promoted S-127 verdict gate.

Mirrors the inline block's behaviour exactly (same logic, same field names) so the skill's
Step 6 can be repointed to this module with no behaviour change, plus failing-first coverage
of the fail-closed rules the inline block already enforced.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from commands.content import ivp_gate


def _write_page(tmp_path: Path, name: str, text: str) -> Path:
    p = tmp_path / name
    p.write_text(text, encoding="utf-8", newline="\n")
    return p


def _verdict(page, sha, reviewer, verdict="PASS", findings=None, checks=None):
    return {
        "page": str(page),
        "content_sha256": sha,
        "reviewer_id": reviewer,
        "tier": 1,
        "checks": checks if checks is not None else [{"id": f"{d}.1", "result": "PASS"} for d in ivp_gate.DIMS],
        "findings": findings or [],
        "verdict": verdict,
    }


def _run_dir(tmp_path: Path) -> Path:
    run_dir = tmp_path / "run"
    (run_dir / "verdicts").mkdir(parents=True)
    return run_dir


class TestSha256Lf:
    def test_crlf_and_lf_hash_the_same(self, tmp_path):
        a = tmp_path / "a.md"
        a.write_bytes(b"line one\r\nline two\r\n")
        b = tmp_path / "b.md"
        b.write_bytes(b"line one\nline two\n")
        assert ivp_gate.sha256_lf(a) == ivp_gate.sha256_lf(b)


class TestValidateVerdict:
    def test_missing_key_is_invalid(self):
        v = _verdict("p.md", "s", "r1")
        del v["tier"]
        ok, why = ivp_gate.validate_verdict(v, set())
        assert not ok and "missing key tier" in why

    def test_author_as_reviewer_is_invalid(self):
        v = _verdict("p.md", "s", "author-1")
        ok, why = ivp_gate.validate_verdict(v, {"author-1"})
        assert not ok and "author" in why

    def test_pass_with_major_finding_is_invalid(self):
        v = _verdict("p.md", "s", "r1", findings=[{"severity": "major"}])
        ok, why = ivp_gate.validate_verdict(v, set())
        assert not ok and "blocker/major" in why

    def test_pass_with_failed_check_is_invalid(self):
        v = _verdict("p.md", "s", "r1", checks=[{"id": "R1.1", "result": "FAIL"}])
        ok, why = ivp_gate.validate_verdict(v, set())
        assert not ok and "failed check" in why

    def test_na_without_note_is_invalid(self):
        checks = [{"id": f"{d}.1", "result": "PASS"} for d in ivp_gate.DIMS]
        checks[0] = {"id": "R1.1", "result": "NA"}
        v = _verdict("p.md", "s", "r1", checks=checks)
        ok, why = ivp_gate.validate_verdict(v, set())
        assert not ok and "NA without a note" in why

    def test_na_with_note_is_valid(self):
        checks = [{"id": f"{d}.1", "result": "PASS"} for d in ivp_gate.DIMS]
        checks[0] = {"id": "R1.1", "result": "NA", "note": "not applicable here"}
        v = _verdict("p.md", "s", "r1", checks=checks)
        ok, why = ivp_gate.validate_verdict(v, set())
        assert ok, why

    def test_missing_dimension_is_invalid(self):
        checks = [{"id": f"{d}.1", "result": "PASS"} for d in ivp_gate.DIMS if d != "R5"]
        v = _verdict("p.md", "s", "r1", checks=checks)
        ok, why = ivp_gate.validate_verdict(v, set())
        assert not ok and "R5" in why

    def test_fail_verdict_valid_regardless_of_checks(self):
        v = _verdict("p.md", "s", "r1", verdict="FAIL", checks=[{"id": "R1.1", "result": "FAIL"}])
        ok, why = ivp_gate.validate_verdict(v, set())
        assert ok, why


class TestRunGate:
    def test_tier1_needs_two_distinct_reviewers(self, tmp_path):
        page = _write_page(tmp_path, "p.md", "hello\n")
        run_dir = _run_dir(tmp_path)
        (run_dir / "tiers.json").write_text(json.dumps({str(page): 1}), encoding="utf-8")
        sha = ivp_gate.sha256_lf(page)
        (run_dir / "verdicts" / "r1.json").write_text(json.dumps(_verdict(page, sha, "r1")), encoding="utf-8")
        out = ivp_gate.run_gate(run_dir, [str(page)], set())
        assert out["pages"][0]["status"] == "NEEDS_REVIEW"
        assert not out["all_cleared"]

        (run_dir / "verdicts" / "r2.json").write_text(json.dumps(_verdict(page, sha, "r2")), encoding="utf-8")
        out2 = ivp_gate.run_gate(run_dir, [str(page)], set())
        assert out2["pages"][0]["status"] == "CLEARED"
        assert out2["all_cleared"]

    def test_tier2_needs_only_one(self, tmp_path):
        page = _write_page(tmp_path, "p.md", "hello\n")
        run_dir = _run_dir(tmp_path)
        (run_dir / "tiers.json").write_text(json.dumps({str(page): 2}), encoding="utf-8")
        sha = ivp_gate.sha256_lf(page)
        (run_dir / "verdicts" / "r1.json").write_text(json.dumps(_verdict(page, sha, "r1")), encoding="utf-8")
        out = ivp_gate.run_gate(run_dir, [str(page)], set())
        assert out["pages"][0]["status"] == "CLEARED"

    def test_blocker_overrides_two_passes(self, tmp_path):
        page = _write_page(tmp_path, "p.md", "hello\n")
        run_dir = _run_dir(tmp_path)
        (run_dir / "tiers.json").write_text(json.dumps({str(page): 1}), encoding="utf-8")
        sha = ivp_gate.sha256_lf(page)
        (run_dir / "verdicts" / "r1.json").write_text(json.dumps(_verdict(page, sha, "r1")), encoding="utf-8")
        (run_dir / "verdicts" / "r2.json").write_text(json.dumps(_verdict(page, sha, "r2")), encoding="utf-8")
        (run_dir / "verdicts" / "r3.json").write_text(
            json.dumps(_verdict(page, sha, "r3", verdict="FAIL", findings=[{"severity": "blocker"}])),
            encoding="utf-8",
        )
        out = ivp_gate.run_gate(run_dir, [str(page)], set())
        assert out["pages"][0]["status"] == "REWORK_REQUIRED"
        assert not out["all_cleared"]

    def test_stale_hash_verdict_is_ignored_after_edit(self, tmp_path):
        page = _write_page(tmp_path, "p.md", "hello\n")
        run_dir = _run_dir(tmp_path)
        (run_dir / "tiers.json").write_text(json.dumps({str(page): 2}), encoding="utf-8")
        old_sha = ivp_gate.sha256_lf(page)
        (run_dir / "verdicts" / "r1.json").write_text(json.dumps(_verdict(page, old_sha, "r1")), encoding="utf-8")
        # edit the page after the review -- the stored verdict is now stale
        page.write_text("hello again\n", encoding="utf-8", newline="\n")
        out = ivp_gate.run_gate(run_dir, [str(page)], set())
        row = out["pages"][0]
        assert row["status"] == "NEEDS_REVIEW"
        assert any("stale hash" in w for w in row["why"])

    def test_author_reviewer_does_not_count(self, tmp_path):
        page = _write_page(tmp_path, "p.md", "hello\n")
        run_dir = _run_dir(tmp_path)
        (run_dir / "tiers.json").write_text(json.dumps({str(page): 2}), encoding="utf-8")
        sha = ivp_gate.sha256_lf(page)
        (run_dir / "verdicts" / "r1.json").write_text(json.dumps(_verdict(page, sha, "author-x")), encoding="utf-8")
        out = ivp_gate.run_gate(run_dir, [str(page)], {"author-x"})
        assert out["pages"][0]["status"] == "NEEDS_REVIEW"

    def test_missing_page_file(self, tmp_path):
        run_dir = _run_dir(tmp_path)
        (run_dir / "tiers.json").write_text(json.dumps({}), encoding="utf-8")
        out = ivp_gate.run_gate(run_dir, [str(tmp_path / "ghost.md")], set())
        assert out["pages"][0]["status"] == "MISSING_PAGE"
        assert not out["all_cleared"]

    def test_no_verdicts_dir_is_empty_not_a_crash(self, tmp_path):
        page = _write_page(tmp_path, "p.md", "hello\n")
        run_dir = tmp_path / "bare_run"
        run_dir.mkdir()
        out = ivp_gate.run_gate(run_dir, [str(page)], set())
        assert out["pages"][0]["status"] == "NEEDS_REVIEW"

    def test_malformed_verdict_json_is_discarded_not_fatal(self, tmp_path):
        page = _write_page(tmp_path, "p.md", "hello\n")
        run_dir = _run_dir(tmp_path)
        (run_dir / "tiers.json").write_text(json.dumps({str(page): 2}), encoding="utf-8")
        (run_dir / "verdicts" / "bad.json").write_text("{not json", encoding="utf-8")
        out = ivp_gate.run_gate(run_dir, [str(page)], set())
        assert out["pages"][0]["status"] == "NEEDS_REVIEW"

    def test_default_tier_is_one_when_unlisted(self, tmp_path):
        page = _write_page(tmp_path, "p.md", "hello\n")
        run_dir = _run_dir(tmp_path)
        (run_dir / "tiers.json").write_text(json.dumps({}), encoding="utf-8")
        sha = ivp_gate.sha256_lf(page)
        (run_dir / "verdicts" / "r1.json").write_text(json.dumps(_verdict(page, sha, "r1")), encoding="utf-8")
        out = ivp_gate.run_gate(run_dir, [str(page)], set())
        assert out["pages"][0]["tier"] == 1
        assert out["pages"][0]["status"] == "NEEDS_REVIEW"  # tier 1 default needs 2

    def test_all_cleared_true_only_when_every_page_cleared(self, tmp_path):
        p1 = _write_page(tmp_path, "p1.md", "a\n")
        p2 = _write_page(tmp_path, "p2.md", "b\n")
        run_dir = _run_dir(tmp_path)
        (run_dir / "tiers.json").write_text(json.dumps({str(p1): 2, str(p2): 2}), encoding="utf-8")
        s1 = ivp_gate.sha256_lf(p1)
        (run_dir / "verdicts" / "r1.json").write_text(json.dumps(_verdict(p1, s1, "r1")), encoding="utf-8")
        out = ivp_gate.run_gate(run_dir, [str(p1), str(p2)], set())
        assert out["all_cleared"] is False
        assert out["cleared"] == [str(p1)]


class TestReadPages:
    def test_blank_lines_and_comments_stripped(self, tmp_path):
        f = tmp_path / "pages.txt"
        f.write_text("a.md\n\n# comment\nb.md\n   \n", encoding="utf-8")
        assert ivp_gate._read_pages(f) == ["a.md", "b.md"]


class TestMainCli:
    def test_exit_code_reflects_all_cleared(self, tmp_path, capsys):
        page = _write_page(tmp_path, "p.md", "hello\n")
        run_dir = _run_dir(tmp_path)
        (run_dir / "tiers.json").write_text(json.dumps({str(page): 2}), encoding="utf-8")
        sha = ivp_gate.sha256_lf(page)
        (run_dir / "verdicts" / "r1.json").write_text(json.dumps(_verdict(page, sha, "r1")), encoding="utf-8")
        pages_file = tmp_path / "pages.txt"
        pages_file.write_text(str(page) + "\n", encoding="utf-8")

        rc = ivp_gate.main([str(run_dir), str(pages_file)])
        assert rc == 0
        out = capsys.readouterr().out
        assert "ALL_CLEARED" in out
        gate = json.loads((run_dir / "gate.json").read_text(encoding="utf-8"))
        assert gate["all_cleared"] is True

    def test_exit_code_nonzero_when_not_cleared(self, tmp_path):
        run_dir = _run_dir(tmp_path)
        (run_dir / "tiers.json").write_text(json.dumps({}), encoding="utf-8")
        pages_file = tmp_path / "pages.txt"
        pages_file.write_text(str(tmp_path / "ghost.md") + "\n", encoding="utf-8")
        rc = ivp_gate.main([str(run_dir), str(pages_file)])
        assert rc == 1

    def test_author_ids_argument_excludes_them(self, tmp_path):
        page = _write_page(tmp_path, "p.md", "hello\n")
        run_dir = _run_dir(tmp_path)
        (run_dir / "tiers.json").write_text(json.dumps({str(page): 2}), encoding="utf-8")
        sha = ivp_gate.sha256_lf(page)
        (run_dir / "verdicts" / "r1.json").write_text(json.dumps(_verdict(page, sha, "author-z")), encoding="utf-8")
        pages_file = tmp_path / "pages.txt"
        pages_file.write_text(str(page) + "\n", encoding="utf-8")
        rc = ivp_gate.main([str(run_dir), str(pages_file), "author-z,author-y"])
        assert rc == 1
