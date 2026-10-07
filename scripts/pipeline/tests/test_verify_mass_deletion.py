"""Tests for post_refresh_verify.py Check 12 -- the mass-deletion guard (MT074 B15).

Incident reproduced here: after a claim-ID reassignment the pipeline deleted
the whole body of 41 pages (2,390 deleted lines, 0 added) and nothing GUARDED
the outcome. Check 12 compares base vs working bytes for every in-scope page.

Coverage:
- both sides of every threshold: per-page fraction, per-page word floor,
  run-wide share, run-wide page floor, removed-claim share, reidentified coverage
- the incident fixture (41 pages, big shrink, 0 additions) trips verify()
- a legitimate retirement / authorized removal does not
- evidence-only restamp diffs (frontmatter-only) never trip it
- two differently shaped products (reference/python vs kb/net)
- the real ``git cat-file --batch`` base reader against a throwaway repo
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

import post_refresh_verify as prv


BASE = "BASEREF"


@pytest.fixture(autouse=True)
def _isolate(tmp_path):
    prv.configure(
        repo_root=tmp_path,
        reports_root=tmp_path / "refresh_state",
        here=tmp_path / "_nonexistent_scripts",
    )
    yield
    prv.configure()


def _words(n: int, tag: str = "w") -> str:
    return " ".join(f"{tag}{i}" for i in range(n))


def _page(body: str, *, evidence: str = "model_sha: aaa") -> str:
    return f"---\ntitle: T\nevidence:\n  {evidence}\n---\n{body}\n"


class Tree:
    """Base blobs (served through the git_base_blobs seam) + working files."""

    def __init__(self, root: Path):
        self.root = root
        self.base: dict[str, bytes] = {}
        prv.configure(
            repo_root=root,
            reports_root=root / "refresh_state",
            here=root / "_nonexistent_scripts",
            git_base_blobs=self._blobs,
        )

    def _blobs(self, paths, base_ref):
        assert base_ref == BASE
        return {p: self.base.get(p) for p in paths}

    def add(self, rel: str, base_text: str | None, work_text: str | None):
        if base_text is not None:
            self.base[rel] = base_text.encode("utf-8")
        if work_text is not None:
            f = self.root / rel
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_bytes(work_text.encode("utf-8"))

    def check(self, paths=None, **kw):
        failures, notes, self.unknowns = prv.check_mass_deletion(
            paths if paths is not None else sorted(self.base), base_ref=BASE, **kw
        )
        return failures, notes


# ---------------------------------------------------------------------------
# (a) per-page thresholds
# ---------------------------------------------------------------------------

class TestPerPageThreshold:
    @pytest.mark.parametrize("rel", [
        "content/reference.aspose.org/en/cells/python/workbook.md",
        "content/kb.aspose.org/en/pdf/net/how-to-merge.md",
    ])
    def test_fraction_boundary(self, tmp_path, rel):
        t = Tree(tmp_path)
        # 1000 words -> 610 = 39% shrink (<= 40%): pass; -> 590 = 41%: fail.
        t.add(rel, _page(_words(1000)), _page(_words(610)))
        failures, _ = t.check()
        assert failures == []
        t.add(rel, _page(_words(1000)), _page(_words(590)))
        failures, _ = t.check()
        assert len(failures) == 1
        assert rel in failures[0] and "1000 -> 590" in failures[0] and "-41%" in failures[0]

    def test_exactly_at_fraction_is_not_a_failure(self, tmp_path):
        t = Tree(tmp_path)
        t.add("content/a.md", _page(_words(1000)), _page(_words(600)))  # exactly 40%
        assert t.check()[0] == []

    @pytest.mark.parametrize("rel", [
        "content/docs.aspose.org/en/slides/java/intro.md",
        "content/reference.aspose.org/en/words/net/Document.md",
    ])
    def test_word_floor_boundary(self, tmp_path, rel):
        t = Tree(tmp_path)
        # 100 -> 20: an 80% shrink but exactly 80 words (not > 80): pass.
        t.add(rel, _page(_words(100)), _page(_words(20)))
        assert t.check()[0] == []
        # 100 -> 19: 81 words: fail.
        t.add(rel, _page(_words(100)), _page(_words(19)))
        assert len(t.check()[0]) == 1

    def test_growth_and_small_edits_never_trip(self, tmp_path):
        t = Tree(tmp_path)
        t.add("content/a.md", _page(_words(500)), _page(_words(900)))
        t.add("content/b.md", _page(_words(500)), _page(_words(495)))
        assert t.check()[0] == []

    def test_deleted_working_file_counts_as_full_shrink(self, tmp_path):
        t = Tree(tmp_path)
        t.add("content/gone.md", _page(_words(300)), None)
        failures, _ = t.check()
        assert len(failures) == 1 and "300 -> 0" in failures[0] and "-100%" in failures[0]

    def test_generated_page_without_base_is_expected_not_unknown(self, tmp_path):
        t = Tree(tmp_path)
        t.add("content/new.md", None, _page(_words(50)))
        rows = [{"page_path": "content/new.md", "disposition": "GENERATED"}]
        assert t.check(["content/new.md"], decision_rows=rows)[0] == []
        assert t.unknowns == []

    def test_message_names_page_and_line_numbers(self, tmp_path):
        t = Tree(tmp_path)
        body = "\n".join(f"line {i} " + _words(5, f"x{i}_") for i in range(60))
        t.add("content/p.md", _page(body), _page("kept line"))
        failures, _ = t.check()
        assert "content/p.md" in failures[0]
        assert "lines -60/+1" in failures[0]


# ---------------------------------------------------------------------------
# Explanations: retirement / authorization vs plain BODY_UPDATED
# ---------------------------------------------------------------------------

class TestExplainedShrink:
    REL = "content/reference.aspose.org/en/cells/python/old_class.md"

    def _tree(self, tmp_path):
        t = Tree(tmp_path)
        t.add(self.REL, _page(_words(400)), _page(_words(10)))
        return t

    def test_retired_disposition_explains(self, tmp_path):
        t = self._tree(tmp_path)
        rows = [{"page_path": self.REL, "disposition": "RETIRED"}]
        assert t.check(decision_rows=rows)[0] == []

    def test_explaining_intended_action_explains(self, tmp_path):
        t = self._tree(tmp_path)
        rows = [{"page_path": self.REL, "disposition": "BODY_UPDATED",
                 "intended_action": "SECTION_REMOVED"}]
        assert t.check(decision_rows=rows)[0] == []

    def test_body_updated_alone_does_not_explain(self, tmp_path):
        t = self._tree(tmp_path)
        rows = [{"page_path": self.REL, "disposition": "BODY_UPDATED",
                 "intended_action": "BODY_UPDATE"}]
        assert len(t.check(decision_rows=rows)[0]) == 1

    def test_manifest_authorization_explains(self, tmp_path):
        t = self._tree(tmp_path)
        assert t.check(authorized_paths={self.REL})[0] == []

    def test_explanation_matching_is_case_insensitive_on_path(self, tmp_path):
        t = self._tree(tmp_path)
        rows = [{"page_path": self.REL.upper(), "disposition": "RETIRED"}]
        assert t.check(decision_rows=rows)[0] == []


# ---------------------------------------------------------------------------
# Evidence-only restamps
# ---------------------------------------------------------------------------

class TestEvidenceOnlyRestamp:
    @pytest.mark.parametrize("prefix,n", [
        ("content/reference.aspose.org/en/pdf/java", 60),
        ("content/kb.aspose.org/en/cells/net", 25),
    ])
    def test_frontmatter_only_diffs_never_trip(self, tmp_path, prefix, n):
        t = Tree(tmp_path)
        for i in range(n):
            body = _words(200, f"p{i}_")
            t.add(f"{prefix}/page{i}.md",
                  _page(body, evidence="model_sha: old"),
                  # whole evidence block rewritten and much larger: still no body change
                  _page(body, evidence="model_sha: new\n  claims: [" +
                        ", ".join(f"CLM-{j}" for j in range(80)) + "]"))
        failures, notes = t.check()
        assert failures == []

    def test_crlf_only_difference_is_not_a_shrink(self, tmp_path):
        t = Tree(tmp_path)
        body = "\n".join(_words(10, f"l{i}_") for i in range(40))
        t.add("content/c.md", _page(body), _page(body).replace("\n", "\r\n"))
        assert t.check()[0] == []


# ---------------------------------------------------------------------------
# (b) run-wide share
# ---------------------------------------------------------------------------

def _runwide(failures: list[str]) -> bool:
    return any("run-wide" in f for f in failures)


class TestRunWideShare:
    def _populate(self, t: Tree, total: int, shrunk: int, prefix: str):
        for i in range(total):
            rel = f"{prefix}/p{i:03}.md"
            work = _words(20) if i < shrunk else _words(400)
            t.add(rel, _page(_words(400)), _page(work))

    @pytest.mark.parametrize("prefix", [
        "content/reference.aspose.org/en/slides/java",
        "content/docs.aspose.org/en/email/python",
    ])
    def test_share_boundaries(self, tmp_path, prefix):
        t = Tree(tmp_path)
        # 5 of 100 = exactly 5.0%: not > 5% -> per-page failures only.
        self._populate(t, 100, 5, prefix)
        failures, _ = t.check()
        assert len(failures) == 5 and not _runwide(failures)
        # 6 of 100 = 6% > 5% and >= 3 pages -> run-wide failure added.
        self._populate(t, 100, 6, prefix)
        failures, _ = t.check()
        assert _runwide(failures)
        assert "6 of 100" in [f for f in failures if "run-wide" in f][0]

    def test_page_floor_boundary(self, tmp_path):
        t = Tree(tmp_path)
        # 2 of 10 = 20% but only 2 pages (< 3): no run-wide failure.
        self._populate(t, 10, 2, "content/a")
        failures, _ = t.check()
        assert len(failures) == 2 and not _runwide(failures)
        # 3 of 10 = 30% and 3 pages: run-wide.
        self._populate(t, 10, 3, "content/a")
        assert _runwide(t.check()[0])

    def test_explained_pages_do_not_count_run_wide(self, tmp_path):
        t = Tree(tmp_path)
        self._populate(t, 10, 6, "content/a")
        rows = [{"page_path": f"content/a/p{i:03}.md", "disposition": "RETIRED"}
                for i in range(6)]
        assert t.check(decision_rows=rows)[0] == []

    def test_per_page_failures_are_capped_with_remainder_line(self, tmp_path):
        t = Tree(tmp_path)
        self._populate(t, 40, 12, "content/a")
        failures, _ = t.check()
        per_page = [f for f in failures if "body shrank" in f]
        assert len(per_page) == 5
        assert any("and 7 more page(s)" in f for f in failures)
        assert _runwide(failures)


# ---------------------------------------------------------------------------
# (c) knowledge-delta removed-claim share
# ---------------------------------------------------------------------------

def _delta(base: int, removed_net: int, reidentified: int, new_net: int = 0):
    """Return (current_claims_total, delta) for a base of `base` claims."""
    raw_removed = removed_net + reidentified
    raw_added = new_net + reidentified
    return base - raw_removed + raw_added, {
        "removed_claims": [f"OLD-{i}" for i in range(removed_net)],
        "new_claims": [f"NEW-{i}" for i in range(new_net)],
        "reidentified_claims": {f"RE-{i}": f"RN-{i}" for i in range(reidentified)},
    }


class TestRemovedClaimShare:
    @pytest.mark.parametrize("base", [100, 12000])
    def test_share_boundary(self, tmp_path, base):
        t = Tree(tmp_path)
        scale = base // 100
        cur, d = _delta(base, 30 * scale, 0)  # exactly 30%: allowed
        assert t.check([], claims_current_total=cur, knowledge_delta=d)[0] == []
        cur, d = _delta(base, 31 * scale, 0)  # 31%, nothing reconciled: fail
        failures, _ = t.check([], claims_current_total=cur, knowledge_delta=d)
        assert len(failures) == 1
        assert f"{31 * scale} of {base}" in failures[0] and "covers only 0.0%" in failures[0]

    def test_reidentified_coverage_boundary(self, tmp_path):
        t = Tree(tmp_path)
        # 40 raw removed of 100: 38 reidentified = 95.0% -> allowed.
        cur, d = _delta(100, 2, 38)
        assert t.check([], claims_current_total=cur, knowledge_delta=d)[0] == []
        # 37 reidentified = 92.5% -> fail.
        cur, d = _delta(100, 3, 37)
        failures, _ = t.check([], claims_current_total=cur, knowledge_delta=d)
        assert len(failures) == 1 and "92.5%" in failures[0]

    def test_incident_delta_fully_reconciled_passes_unreconciled_fails(self, tmp_path):
        t = Tree(tmp_path)
        # 11,945 base claims; 11,942 removed ids are text-identical re-IDs.
        cur, d = _delta(11945, 3, 11942)
        assert t.check([], claims_current_total=cur, knowledge_delta=d)[0] == []
        # Same storm WITHOUT the reidentified_claims reconciliation.
        d_raw = dict(d, removed_claims=d["removed_claims"] + [f"R{i}" for i in range(11942)],
                     reidentified_claims={})
        cur_raw = 11945 - 11945 + 11942  # the 11,942 re-IDed claims re-appear as new
        failures, _ = t.check([], claims_current_total=cur_raw,
                              knowledge_delta=dict(d_raw, new_claims=[f"N{i}" for i in range(11942)]))
        assert len(failures) == 1 and "11945 of 11945" in failures[0]

    def test_unknown_totals_skip_the_claim_check(self, tmp_path):
        t = Tree(tmp_path)
        _, d = _delta(100, 90, 0)
        assert t.check([], claims_current_total=None, knowledge_delta=d)[0] == []
        assert t.check([], claims_current_total=10, knowledge_delta=None)[0] == []


# ---------------------------------------------------------------------------
# R3-1: fail closed when the base cannot be read
# ---------------------------------------------------------------------------

class TestFailsClosedWhenBaseUnreadable:
    def test_reviewer_repro_unknown_base_ref(self, tmp_path):
        """check_mass_deletion([<real .md>], base_ref=deadbeef...) used to
        return ([], []) -- a silent PASS. Real git, unknown base ref."""
        repo = tmp_path / "repo"
        (repo / "content").mkdir(parents=True)
        (repo / "content/a.md").write_bytes(_page(_words(50)).encode("utf-8"))
        prv.configure(repo_root=repo)
        failures, notes, unknowns = prv.check_mass_deletion(
            ["content/a.md"], base_ref="deadbeefdeadbeef")
        assert failures == []
        assert len(unknowns) == 1
        assert "deadbeefdeadbeef" in unknowns[0] and "1 of 1" in unknowns[0]

    def test_partially_readable_base_floor(self, tmp_path):
        t = Tree(tmp_path)
        for i in range(4):
            t.add(f"content/p{i}.md", _page(_words(100)) if i < 1 else None, _page(_words(100)))
        paths = [f"content/p{i}.md" for i in range(4)]
        t.check(paths)  # 1 of 4 readable (25% < 50%)
        assert len(t.unknowns) == 1 and "3 of 4" in t.unknowns[0]
        t.add("content/p1.md", _page(_words(100)), _page(_words(100)))
        t.check(paths)  # 2 of 4 readable (exactly 50%): enough to look
        assert t.unknowns == []

    def test_all_readable_is_not_unknown(self, tmp_path):
        t = Tree(tmp_path)
        t.add("content/a.md", _page(_words(100)), _page(_words(100)))
        t.check()
        assert t.unknowns == []

    def test_generated_pages_are_excluded_from_the_denominator(self, tmp_path):
        t = Tree(tmp_path)
        t.add("content/old.md", _page(_words(100)), _page(_words(100)))
        for i in range(5):
            t.add(f"content/new{i}.md", None, _page(_words(100)))
        rows = [{"page_path": f"content/new{i}.md", "disposition": "GENERATED"} for i in range(5)]
        paths = ["content/old.md"] + [f"content/new{i}.md" for i in range(5)]
        t.check(paths, decision_rows=rows)
        assert t.unknowns == []
        t.check(paths)  # without the GENERATED rows only 1 of 6 is readable
        assert len(t.unknowns) == 1

    def test_threshold_is_configurable(self, tmp_path):
        t = Tree(tmp_path)
        t.add("content/a.md", _page(_words(100)), _page(_words(100)))
        t.add("content/b.md", None, _page(_words(100)))
        t.check(["content/a.md", "content/b.md"])
        assert t.unknowns == []  # 1 of 2 = 50%
        prv.configure(repo_root=tmp_path, git_base_blobs=t._blobs,
                      mass_deletion_thresholds={"min_comparable_fraction": 0.9})
        t.check(["content/a.md", "content/b.md"])
        assert len(t.unknowns) == 1

    def test_verify_reports_unknown_not_pass(self, tmp_path, capsys):
        t = Tree(tmp_path)
        _write_knowledge(tmp_path, "pdf", "java", [])
        # in-scope page exists in the working tree, no base version anywhere
        t.add("content/docs.aspose.org/en/pdf/java/a.md", None, _page(_words(50)))
        unknowns: list = []
        passed, failures = prv.verify("pdf", "java", base_ref=BASE, unknowns_out=unknowns)
        out = capsys.readouterr().out
        assert any("Check 12" in u for u in unknowns)
        assert "Check 12: UNKNOWN (RPR-J-06)" in out
        assert "Check 12: PASS" not in out


# ---------------------------------------------------------------------------
# Thresholds are configurable
# ---------------------------------------------------------------------------

class TestConfigurableThresholds:
    def test_override_per_page_thresholds(self, tmp_path):
        t = Tree(tmp_path)
        t.add("content/a.md", _page(_words(1000)), _page(_words(590)))
        assert len(t.check()[0]) == 1
        prv.configure(
            repo_root=tmp_path, git_base_blobs=t._blobs,
            mass_deletion_thresholds={"max_shrink_fraction": 0.5},
        )
        assert t.check()[0] == []

    def test_unknown_threshold_key_is_rejected(self):
        with pytest.raises(ValueError, match="unknown mass_deletion_thresholds"):
            prv.configure(mass_deletion_thresholds={"nope": 1})

    def test_configure_without_args_resets_defaults(self, tmp_path):
        prv.configure(mass_deletion_thresholds={"max_shrink_fraction": 0.9})
        prv.configure()
        assert prv._cfg_mass_deletion == prv.MASS_DELETION_DEFAULTS


# ---------------------------------------------------------------------------
# verify() integration: the incident fixture
# ---------------------------------------------------------------------------

def _write_knowledge(root: Path, family: str, platform: str, claims, delta=None):
    merged = root / "knowledge" / family / platform / "merged"
    merged.mkdir(parents=True)
    (merged / "model.yaml").write_text("stale_since: null\nversion: '1.0'\n", encoding="utf-8")
    (merged / "claims.json").write_text(json.dumps(claims), encoding="utf-8")
    (merged / "api_surface.json").write_text("[]", encoding="utf-8")
    if delta is not None:
        (merged / "knowledge_delta.json").write_text(json.dumps(delta), encoding="utf-8")


class TestVerifyIntegration:
    def _incident(self, tmp_path, family="pdf", platform="java"):
        """41 pages whose whole body was deleted (2,390 deletions, 0 additions)."""
        t = Tree(tmp_path)
        _write_knowledge(tmp_path, family, platform, [])
        for i in range(41):
            rel = f"content/reference.aspose.org/en/{family}/{platform}/Class{i:02}.md"
            body = "\n".join(f"- member {i}.{j} does thing number {j}" for j in range(58))
            t.add(rel, _page(body), _page(""))
        return t

    @pytest.mark.parametrize("family,platform", [("pdf", "java"), ("slides", "net")])
    def test_incident_trips_verify(self, tmp_path, family, platform):
        self._incident(tmp_path, family, platform)
        unknowns: list = []
        passed, failures = prv.verify(family, platform, base_ref=BASE, unknowns_out=unknowns)
        assert not passed
        c12 = [f for f in failures if "Check 12" in f]
        assert len(c12) == 7  # 5 capped per-page + remainder line + run-wide
        assert any("run-wide" in f and "41 of 41" in f for f in c12)
        assert any("lines -58/+0" in f for f in c12)
        assert any(f"Class" in f and "-100%" in f for f in c12)

    def test_allow_warn_demotes_to_warning(self, tmp_path, capsys):
        self._incident(tmp_path)
        passed, failures = prv.verify("pdf", "java", base_ref=BASE, allow_warn=True,
                                      unknowns_out=[])
        assert not [f for f in failures if "Check 12" in f]
        assert "Check 12: WARN (--allow-warn)" in capsys.readouterr().out

    def test_clean_run_and_restamp_run_pass(self, tmp_path, capsys):
        t = Tree(tmp_path)
        _write_knowledge(tmp_path, "email", "python", [])
        for i in range(12):
            body = _words(150, f"k{i}_")
            t.add(f"content/kb.aspose.org/en/email/python/faq{i}.md",
                  _page(body, evidence="model_sha: old"),
                  _page(body, evidence="model_sha: new"))
        unknowns: list = []
        passed, failures = prv.verify("email", "python", base_ref=BASE, unknowns_out=unknowns)
        assert not [f for f in failures if "Check 12" in f]
        assert "Check 12: PASS" in capsys.readouterr().out

    def test_verify_flags_unreconciled_claim_storm_from_delta_file(self, tmp_path):
        t = Tree(tmp_path)
        claims = [{"claim_id": f"CLM-{i}"} for i in range(100)]
        delta = {"removed_claims": [f"OLD-{i}" for i in range(60)],
                 "new_claims": [], "reidentified_claims": {}}
        # current claims.json holds 100 claims; delta says 60 net removed -> base 160.
        _write_knowledge(tmp_path, "cells", "python", claims, delta)
        t.add("content/docs.aspose.org/en/cells/python/a.md", _page(_words(50)), _page(_words(50)))
        passed, failures = prv.verify("cells", "python", base_ref=BASE, unknowns_out=[])
        assert any("knowledge delta" in f and "60 of 160" in f for f in failures)

    def test_page_with_no_base_blob_is_skipped_not_failed(self, tmp_path):
        t = Tree(tmp_path)
        _write_knowledge(tmp_path, "email", "python", [])
        t.add("content/docs.aspose.org/en/email/python/new.md", None, _page(_words(10)))
        passed, failures = prv.verify("email", "python", base_ref=BASE, unknowns_out=[])
        assert not [f for f in failures if "Check 12" in f]


# ---------------------------------------------------------------------------
# The real git reader (no seam), against a throwaway repository
# ---------------------------------------------------------------------------

def _git(cwd: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid",
         "-c", "commit.gpgsign=false", *args],
        cwd=str(cwd), check=True, capture_output=True,
    )


class TestRealGitReader:
    def test_cat_file_batch_reader_and_check_end_to_end(self, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()
        prv.configure(repo_root=repo, reports_root=repo / "refresh_state")
        _git(repo, "init", "-q")
        keep = "content/docs.aspose.org/en/tex/python/keep.md"
        wiped = "content/docs.aspose.org/en/tex/python/wiped.md"
        for rel, body in ((keep, _words(300)), (wiped, _words(300, "z"))):
            f = repo / rel
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_bytes(_page(body).encode("utf-8"))
        _git(repo, "add", "-A")
        _git(repo, "commit", "-q", "-m", "base")
        base = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(repo), check=True,
                              capture_output=True, text=True, encoding="utf-8").stdout.strip()
        (repo / wiped).write_bytes(_page("").encode("utf-8"))

        blobs = prv._read_base_blobs([keep, wiped, "content/missing.md"], base)
        assert blobs["content/missing.md"] is None
        assert blobs[keep] == _page(_words(300)).encode("utf-8")

        failures, _n, unknowns = prv.check_mass_deletion(
            [keep, wiped, "content/missing.md"], base_ref=base)
        assert len(failures) == 1 and wiped in failures[0] and "300 -> 0" in failures[0]
        assert unknowns == []  # 2 of 3 comparable is above the 50% floor

    def test_directory_path_mid_list_does_not_desync_the_stream(self, tmp_path):
        """R3-3: a tree object (directory path) in the middle of the list used to
        make every later read None and the last blob mismatch."""
        repo = tmp_path / "repo"
        repo.mkdir()
        prv.configure(repo_root=repo, reports_root=repo / "refresh_state")
        _git(repo, "init", "-q")
        rels = [f"content/d/p{i}.md" for i in range(6)]
        for i, rel in enumerate(rels):
            f = repo / rel
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_bytes(_page(_words(30, f"b{i}_")).encode("utf-8"))
        _git(repo, "add", "-A")
        _git(repo, "commit", "-q", "-m", "base")
        base = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(repo), check=True,
                              capture_output=True, text=True, encoding="utf-8").stdout.strip()
        paths = rels[:2] + ["content/d", "content/nope.md"] + rels[2:]
        blobs = prv._read_base_blobs(paths, base)
        assert blobs["content/d"] is None and blobs["content/nope.md"] is None
        for i, rel in enumerate(rels):
            assert blobs[rel] == _page(_words(30, f"b{i}_")).encode("utf-8"), rel

    def test_not_a_git_repo_yields_no_comparable_pages(self, tmp_path):
        prv.configure(repo_root=tmp_path / "nowhere-not-a-repo")
        (tmp_path / "nowhere-not-a-repo").mkdir()
        assert prv._read_base_blobs(["content/a.md"], "HEAD") == {"content/a.md": None}
        failures, _n, unknowns = prv.check_mass_deletion(["content/a.md"], base_ref="HEAD")
        assert failures == [] and len(unknowns) == 1  # fail-closed, never a silent pass
