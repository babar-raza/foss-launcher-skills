"""Tests for skill_provenance_audit.py (MT074 card A11, AC-5).

Offline: real git in tmp repos with synthetic commits and synthetic skill-run
JSON records. The fixture matrix is deliberately unrelated to this repo's real
matrix (generality: the audit's mapping is data, not code); one extra test
sanity-loads the real seeded matrix.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

import skill_provenance_audit as spa

FIXTURE_MATRIX = """
version: 1
gap_markers: ["OVERRIDE"]
gap_dir: gaps
default: {id: misc, exempt: true, warn: true}
classes:
  - id: engine_special
    patterns: ["src/engine/gen/**"]
    skills: [Q-9]
  - id: engine
    patterns: ["src/**"]
    skills: [X-1, X-2]
    allow_gap_markers: true
  - id: writing
    patterns: ["docs/**/*.md", "README.md"]
    skills: [Y-2, Y-3]
    token_required: true
  - id: scratch
    patterns: ["tmp/**"]
    exempt: true
  - id: look
    patterns: ["themes/**"]
    no_skill: true
"""


def _git(repo: Path, *args: str) -> str:
    r = subprocess.run(["git", *args], cwd=str(repo), capture_output=True, text=True,
                       encoding="utf-8", check=True)
    return r.stdout.strip()


@pytest.fixture(autouse=True)
def _reset_cfg():
    spa.configure()
    yield
    spa.configure()


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "repo"
    r.mkdir()
    _git(r, "init", "-q", "-b", "main")
    _git(r, "config", "user.email", "t@example.com")
    _git(r, "config", "user.name", "T")
    _git(r, "config", "commit.gpgsign", "false")
    # keep fixtures (records, gap registry) out of the synthetic commits
    (r / ".git" / "info" / "exclude").write_text("reports/\ngaps/\n", encoding="utf-8")
    (r / "seed.txt").write_text("seed", encoding="utf-8")
    _git(r, "add", "-A")
    _git(r, "commit", "-q", "-m", "seed")
    return r


@pytest.fixture
def matrix(tmp_path):
    p = tmp_path / "matrix.yaml"
    p.write_text(FIXTURE_MATRIX, encoding="utf-8")
    return spa.load_matrix(p)


def _commit(repo: Path, files: dict[str, str], msg: str) -> str:
    for rel, text in files.items():
        f = repo / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(text, encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", msg)
    return _git(repo, "rev-parse", "HEAD")


def _record(repo: Path, name: str, sha: str, skills: list[str], **extra) -> None:
    d = repo / "reports" / "skill-runs"
    d.mkdir(parents=True, exist_ok=True)
    rec = {"run_id": name, "skills_invoked": skills, "skill_details": [],
           "outcome": "success", "commit_sha": sha, "retroactive": True,
           "run_type": "targeted"}
    rec.update(extra)
    (d / f"{name}.json").write_text(json.dumps(rec), encoding="utf-8")


def _audit(repo, matrix, base="main~0"):
    spa.configure(repo_root=repo)  # records dir + gap dir resolve under the tmp repo
    return spa.audit_range(base, "HEAD", matrix, git=spa.SubprocessGitReader(repo))


def _base(repo) -> str:
    return _git(repo, "rev-parse", "HEAD")


def _one(report) -> dict:
    assert len(report["commits"]) == 1
    return report["commits"][0]


# ---- verdicts ---------------------------------------------------------------

def test_pass_with_sanctioned_skill_record(repo, matrix):
    base = _base(repo)
    sha = _commit(repo, {"src/a.py": "x"}, "add a")
    _record(repo, "r1", sha, ["X-2"])
    c = _one(_audit(repo, matrix, base))
    assert c["verdict"] == "PASS" and c["classes"] == ["engine"]
    assert c["declared_source"] == "record" and c["declared_skills"] == ["X-2"]


def test_violation_when_only_unsanctioned_skill(repo, matrix):
    base = _base(repo)
    sha = _commit(repo, {"docs/guide.md": "x"}, "add doc")
    _record(repo, "r1", sha, ["X-1"])  # code skill, not a writing skill
    c = _one(_audit(repo, matrix, base))
    assert c["verdict"] == "VIOLATION" and c["uncovered_classes"] == ["writing"]
    assert any("token required" in n for n in c["notes"])  # informational only


def test_no_record_and_no_trailer(repo, matrix):
    base = _base(repo)
    _commit(repo, {"src/a.py": "x"}, "add a")
    c = _one(_audit(repo, matrix, base))
    assert c["verdict"] == "NO_RECORD" and c["declared_source"] == "none"


def test_trailer_fallback_pass_and_violation(repo, matrix):
    base = _base(repo)
    _commit(repo, {"src/a.py": "x"}, "add a\n\nSkills invoked: [X-1, Y-2]")
    _commit(repo, {"docs/b.md": "x"}, "add b\n\nSkills invoked: X-1")
    c1, c2 = _audit(repo, matrix, base)["commits"]
    assert c1["verdict"] == "PASS" and c1["declared_source"] == "trailer"
    assert c2["verdict"] == "VIOLATION" and c2["declared_skills"] == ["X-1"]


def test_record_takes_precedence_over_trailer(repo, matrix):
    base = _base(repo)
    sha = _commit(repo, {"docs/b.md": "x"}, "add b\n\nSkills invoked: Y-2")
    _record(repo, "r1", sha, ["X-1"])
    c = _one(_audit(repo, matrix, base))
    assert c["declared_source"] == "record" and c["verdict"] == "VIOLATION"


def test_multi_class_commit_needs_skill_for_each(repo, matrix):
    base = _base(repo)
    sha = _commit(repo, {"src/a.py": "x", "docs/b.md": "x"}, "both")
    _record(repo, "r1", sha, ["X-1"])
    c = _one(_audit(repo, matrix, base))
    assert c["verdict"] == "VIOLATION" and c["uncovered_classes"] == ["writing"]
    _record(repo, "r2", sha, ["Y-3"])  # second record for the same sha -> unioned
    c = _one(_audit(repo, matrix, base))
    assert c["verdict"] == "PASS" and c["run_ids"] == ["r1", "r2"]


def test_first_match_wins(repo, matrix):
    base = _base(repo)
    sha = _commit(repo, {"src/engine/gen/z.py": "x"}, "gen")
    _record(repo, "r1", sha, ["X-1"])  # sanctioned for src/** but not the special class
    c = _one(_audit(repo, matrix, base))
    assert c["classes"] == ["engine_special"] and c["verdict"] == "VIOLATION"


def test_exempt_only_and_unclassified_warn(repo, matrix):
    base = _base(repo)
    _commit(repo, {"tmp/x.txt": "x", "other/y.txt": "y"}, "misc")
    c = _one(_audit(repo, matrix, base))
    assert c["verdict"] == "PASS" and c["classes"] == ["misc", "scratch"]
    assert any(n.startswith("WARN") for n in c["notes"])


def test_retroactive_record_matched_by_short_sha_prefix(repo, matrix):
    base = _base(repo)
    sha = _commit(repo, {"src/a.py": "x"}, "add a")
    _record(repo, "r1", sha[:10], ["X-1"], retroactive=True)
    assert _one(_audit(repo, matrix, base))["verdict"] == "PASS"


def test_record_for_other_sha_and_failed_outcome_ignored(repo, matrix):
    base = _base(repo)
    sha = _commit(repo, {"src/a.py": "x"}, "add a")
    _record(repo, "other", "0" * 40, ["X-1"])
    _record(repo, "bad", sha, ["X-1"], outcome="failure")
    assert _one(_audit(repo, matrix, base))["verdict"] == "NO_RECORD"


def test_merge_commit_is_not_diffed(repo, matrix):
    base = _base(repo)
    _git(repo, "checkout", "-q", "-b", "feat")
    s1 = _commit(repo, {"src/f.py": "f"}, "feature")
    _git(repo, "checkout", "-q", "main")
    s2 = _commit(repo, {"docs/m.md": "m"}, "mainline")
    _git(repo, "merge", "-q", "--no-ff", "-m", "merge feat", "feat")
    _record(repo, "r1", s1, ["X-1"])
    _record(repo, "r2", s2, ["Y-2"])
    report = _audit(repo, matrix, base)
    merges = [c for c in report["commits"] if c["merge"]]
    assert len(merges) == 1 and merges[0]["verdict"] == "PASS" and merges[0]["classes"] == []
    assert report["summary"] == {"total": 3, "PASS": 3, "VIOLATION": 0, "NO_RECORD": 0, "GAP": 0,
                                 "unclassified_files": 0, "unclassified_commits": 0,
                                 "clean": True}


def test_empty_range(repo, matrix):
    report = _audit(repo, matrix, _base(repo))
    assert report["commits"] == [] and report["summary"]["clean"] is True


def test_injected_readers_no_git(matrix):
    class FakeGit:
        def commits(self, base, head):
            return [spa.CommitInfo("a" * 40, ("b" * 40,), "do thing")]

        def changed_files(self, sha):
            return ["src/q.py"]

    spa.configure(git_reader=FakeGit(),
                  record_reader=lambda d: [{"commit_sha": "a" * 40, "skills_invoked": ["X-2"]}])
    report = spa.audit_range("b", "h", matrix, records_dir="unused")
    assert _one(report)["verdict"] == "PASS"


# ---- matrix -----------------------------------------------------------------

@pytest.mark.parametrize("data, needle", [
    ([], "top level must be a mapping"),
    ({"version": 2, "classes": []}, "'version' must be 1"),
    ({"version": 1}, "'classes' must be a non-empty list"),
    ({"version": 1, "classes": [{"id": "a", "patterns": ["x"]}]}, "needs a non-empty 'skills'"),
    ({"version": 1, "classes": [{"id": "a", "skills": ["S"]}]}, "'patterns' is required"),
    ({"version": 1, "classes": [{"id": "a", "patterns": [], "skills": ["S"]}]}, "must not be empty"),
    ({"version": 1, "classes": [{"id": "a", "patterns": ["x"], "skills": ["S"]},
                                {"id": "a", "patterns": ["y"], "skills": ["S"]}]}, "duplicate class id"),
    ({"version": 1, "classes": [{"id": "a", "patterns": ["x"], "skills": ["S"], "bogus": 1}]},
     "unknown key"),
    ({"version": 1, "extra": 1, "classes": [{"id": "a", "patterns": ["x"], "skills": ["S"]}]},
     "unknown top-level key"),
    ({"version": 1, "gap_markers": "GAP",
      "classes": [{"id": "a", "patterns": ["x"], "skills": ["S"]}]}, "gap_markers"),
    ({"version": 1, "gap_dir": 3,
      "classes": [{"id": "a", "patterns": ["x"], "skills": ["S"]}]}, "gap_dir"),
    ({"version": 1, "classes": [{"id": "a", "patterns": ["x"], "no_skill": True, "skills": ["S"]}]},
     "no_skill"),
    ({"version": 1, "classes": [{"id": "a", "patterns": ["x"], "no_skill": True, "exempt": True}]},
     "no_skill"),
    ({"version": 1, "classes": [{"id": "a", "patterns": ["x"], "skills": ["S"], "exempt": "yes"}]},
     "true or false"),
])
def test_matrix_validation_errors(data, needle):
    with pytest.raises(spa.MatrixError) as ei:
        spa.parse_matrix(data, "m.yaml")
    assert needle in str(ei.value) and "m.yaml" in str(ei.value)


def test_load_matrix_missing_and_bad_yaml(tmp_path):
    with pytest.raises(spa.MatrixError, match="not found"):
        spa.load_matrix(tmp_path / "nope.yaml")
    bad = tmp_path / "bad.yaml"
    bad.write_text("a: [unclosed", encoding="utf-8")
    with pytest.raises(spa.MatrixError, match="invalid YAML"):
        spa.load_matrix(bad)


def test_glob_semantics(matrix):
    assert matrix.classify("docs/a/b/c.md").id == "writing"
    assert matrix.classify("docs/c.md").id == "writing"
    assert matrix.classify("docs/c.txt").id == "misc"
    assert matrix.classify("README.md").id == "writing"
    assert matrix.classify("sub/README.md").id == "misc"
    assert matrix.classify("src\\x.py").id == "engine"
    assert matrix.classify("./src/x.py").id == "engine"


def test_real_matrix_loads_and_classifies():
    m = spa.load_matrix(spa.DEFAULT_MATRIX)
    assert m.classify("scripts/ci/deployed-workflows/a.yml").id == "deployed_workflows"
    assert m.classify("scripts/pipeline/x.py").id == "pipeline_code"
    assert m.classify("data/knowledge_state.json").id == "derived_knowledge_projection"
    assert m.classify("data/other.json").id == "data_other"
    assert m.classify("content/kb.aspose.org/en/x.md").id == "content_kb"
    assert m.classify("docs/governance/a.md").token_required
    assert m.classify("README.md").id == "unclassified"
    # R4-1: translation/locale writers are sanctioned for every content class
    for cls in m.classes:
        if cls.patterns[0].startswith("content/"):
            assert {"S-HT-01", "S-HT-02", "S-109", "S-75"} <= cls.skills, cls.id
    wf = m.classify("data/workflow_deploy_baselines.json")
    assert wf.id != "data_other" and wf.skills == frozenset({"S-115"})
    # R4-3b: governance / CI / theme files are gated, not exempt
    assert m.classify(".github/workflows/x.yml").id == "github_ci"
    assert m.classify("AGENTS.md").id == "root_governance_docs"
    assert m.classify("CLAUDE.md").id == "root_governance_docs"
    assert m.classify("scripts/pre-commit-audit.sh").id == "git_hook_scripts"
    assert m.classify("scripts/githooks/pre-commit").id == "git_hook_scripts"
    assert m.classify("keywords/a.json").id == "seo_keywords"
    for path in ("layouts/a.html", "themes/t/a.html", "configs/a.toml"):
        c = m.classify(path)
        assert c.no_skill and not c.exempt and not c.skills, path


# ---- determinism and CLI -----------------------------------------------------

def test_deterministic_output(repo, matrix):
    base = _base(repo)
    sha = _commit(repo, {"src/a.py": "x", "docs/b.md": "x"}, "both")
    _record(repo, "r1", sha, ["X-1", "Y-2"])
    a = json.dumps(_audit(repo, matrix, base), sort_keys=True)
    b = json.dumps(_audit(repo, matrix, base), sort_keys=True)
    assert a == b
    r = _audit(repo, matrix, base)
    assert spa.render_markdown(r) == spa.render_markdown(r)


def _cli(repo, tmp_path, base, *extra):
    mpath = tmp_path / "matrix.yaml"
    mpath.write_text(FIXTURE_MATRIX, encoding="utf-8")
    spa.configure(repo_root=repo)
    return spa.main(["--base", base, "--head", "HEAD", "--matrix", str(mpath), *extra])


def test_cli_exit_codes_and_outputs(repo, tmp_path, capsys):
    base = _base(repo)
    _commit(repo, {"src/a.py": "x"}, "no record here")
    assert _cli(repo, tmp_path, base) == 0  # advisory by default
    assert _cli(repo, tmp_path, base, "--fail-on-violation") == 1
    jp, mp = tmp_path / "out" / "r.json", tmp_path / "out" / "r.md"
    _cli(repo, tmp_path, base, "--json-out", str(jp), "--md-out", str(mp))
    data = json.loads(jp.read_text(encoding="utf-8"))
    assert data["summary"]["NO_RECORD"] == 1
    assert "NO_RECORD" in mp.read_text(encoding="utf-8")
    assert "| sha | subject |" in capsys.readouterr().out


def test_cli_clean_range_exits_zero_with_fail_flag(repo, tmp_path):
    base = _base(repo)
    sha = _commit(repo, {"src/a.py": "x"}, "ok")
    _record(repo, "r1", sha, ["X-1"])
    assert _cli(repo, tmp_path, base, "--fail-on-violation") == 0


def test_cli_errors_exit_2(repo, tmp_path, capsys):
    spa.configure(repo_root=repo)
    assert spa.main(["--base", "main", "--head", "HEAD",
                     "--matrix", str(tmp_path / "missing.yaml")]) == 2
    mpath = tmp_path / "matrix.yaml"
    mpath.write_text(FIXTURE_MATRIX, encoding="utf-8")
    assert spa.main(["--base", "no-such-rev", "--head", "HEAD", "--matrix", str(mpath)]) == 2
    assert "ERROR" in capsys.readouterr().err


# ---- R4-1: real matrix pins ---------------------------------------------------

def test_real_matrix_s62_on_pipeline_code_is_a_true_positive(repo):
    """S-62 is batch-reference, not a code skill: must stay VIOLATION (MT075 commits)."""
    real = spa.load_matrix(spa.DEFAULT_MATRIX)
    base = _base(repo)
    sha = _commit(repo, {"scripts/pipeline/new_tool.py": "x"}, "pipeline code under S-62")
    _record(repo, "r1", sha, ["S-62"])
    c = _one(_audit(repo, real, base))
    assert c["verdict"] == "VIOLATION" and c["uncovered_classes"] == ["pipeline_code"]
    _record(repo, "r2", sha, ["S-99"])
    assert _one(_audit(repo, real, base))["verdict"] == "PASS"


def test_real_matrix_translation_skill_and_workflow_baselines_pass(repo):
    real = spa.load_matrix(spa.DEFAULT_MATRIX)
    base = _base(repo)
    s1 = _commit(repo, {"content/kb.aspose.org/de/a/b/x.md": "x"}, "translation")
    s2 = _commit(repo, {"data/workflow_deploy_baselines.json": "{}"}, "baselines")
    _record(repo, "r1", s1, ["S-76", "S-HT-02"])
    _record(repo, "r2", s2, ["S-115"])
    assert [c["verdict"] for c in _audit(repo, real, base)["commits"]] == ["PASS", "PASS"]


# ---- R4-2: gap markers need a resolvable id --------------------------------------

def _gap_registry(repo: Path) -> None:
    g = repo / "gaps"
    g.mkdir(exist_ok=True)
    (g / "index.yaml").write_text("entries:\n  - id: GAP-ROW-1\n    report: x.md\n",
                                  encoding="utf-8")
    (g / "2026-01-01-some-report.md").write_text("# report", encoding="utf-8")


@pytest.mark.parametrize("token, verdict, reason", [
    ("OVERRIDE", "VIOLATION", "gap marker without id"),
    ("OVERRIDE:GAP-ROW-1", "PASS", None),                 # index.yaml row id
    ("OVERRIDE:2026-01-01-some-report", "PASS", None),    # report filename stem
    ("OVERRIDE:nope", "VIOLATION", "gap id not found: nope"),
    ("OVERRIDE:index", "VIOLATION", "gap id not found: index"),
    ("OVERRIDE:../escape", "VIOLATION", "gap id not found: ../escape"),
])
def test_gap_marker_requires_resolvable_id(repo, matrix, token, verdict, reason):
    _gap_registry(repo)
    base = _base(repo)
    sha = _commit(repo, {"src/a.py": "x"}, "code under gap")
    _record(repo, "r1", sha, [token])
    c = _one(_audit(repo, matrix, base))
    assert c["verdict"] == verdict
    if reason:
        assert reason in c["reasons"]


def test_gap_marker_via_trailer_and_not_for_ordinary_skill_classes(repo, matrix):
    _gap_registry(repo)
    base = _base(repo)
    _commit(repo, {"src/a.py": "x"}, "code\n\nSkills invoked: OVERRIDE:GAP-ROW-1")
    _commit(repo, {"docs/b.md": "x"}, "doc\n\nSkills invoked: OVERRIDE:GAP-ROW-1")
    c1, c2 = _audit(repo, matrix, base)["commits"]
    assert c1["verdict"] == "PASS" and c1["declared_source"] == "trailer"
    assert c2["verdict"] == "VIOLATION"  # 'writing' does not allow gap markers


def test_gap_resolver_without_gap_dir_never_resolves(tmp_path):
    assert spa.build_gap_resolver(tmp_path / "missing")("anything") is False


# ---- R4-3: no_skill classes -> GAP; unclassified counted; header ---------------------

def test_no_skill_class_is_gap_until_gap_approved(repo, matrix):
    _gap_registry(repo)
    base = _base(repo)
    s1 = _commit(repo, {"themes/t/a.html": "x"}, "theme")
    s2 = _commit(repo, {"themes/t/b.html": "x"}, "theme 2")
    s3 = _commit(repo, {"themes/t/c.html": "x"}, "theme 3")
    _record(repo, "r1", s1, ["X-1"])
    _record(repo, "r2", s2, ["OVERRIDE:GAP-ROW-1"])
    _record(repo, "r3", s3, ["OVERRIDE:nope"])
    c1, c2, c3 = _audit(repo, matrix, base)["commits"]
    assert (c1["verdict"], c1["uncovered_classes"]) == ("GAP", ["look"])
    assert c2["verdict"] == "PASS"
    assert c3["verdict"] == "GAP" and "gap id not found: nope" in c3["reasons"]


def test_skill_violation_outranks_gap(repo, matrix):
    base = _base(repo)
    sha = _commit(repo, {"themes/t/a.html": "x", "docs/z.md": "x"}, "both")
    _record(repo, "r1", sha, ["X-1"])
    assert _one(_audit(repo, matrix, base))["verdict"] == "VIOLATION"


def test_gap_only_commit_fails_cli_gate(repo, matrix, tmp_path):
    base = _base(repo)
    sha = _commit(repo, {"themes/t/a.html": "x"}, "theme")
    _record(repo, "r1", sha, ["X-1"])
    spa.configure(repo_root=repo)
    mp = tmp_path / "m.yaml"
    mp.write_text(FIXTURE_MATRIX, encoding="utf-8")
    assert spa.main(["--base", base, "--head", "HEAD", "--matrix", str(mp),
                     "--fail-on-violation"]) == 1


def test_unclassified_reported_in_summary(repo, matrix):
    base = _base(repo)
    _commit(repo, {"other/y.txt": "y", "other/z.txt": "z"}, "unknown")
    _commit(repo, {"tmp/q": "q"}, "scratch only")
    s = _audit(repo, matrix, base)["summary"]
    assert s["unclassified_files"] == 2 and s["unclassified_commits"] == 1
    assert s["PASS"] == 2  # still exempt-with-warning


def test_report_header_states_record_source_and_count(repo, matrix):
    base = _base(repo)
    sha = _commit(repo, {"src/a.py": "x"}, "a")
    _record(repo, "r1", sha, ["X-1"])
    _record(repo, "r2", "f" * 40, ["X-1"])
    report = _audit(repo, matrix, base)
    assert report["records_source"] == "local-gitignored" and report["records_read"] == 2
    md = spa.render_markdown(report)
    assert "records_source: local-gitignored" in md and "records_read: 2" in md
    assert "not tamper-proof" in md


def test_injected_record_reader_is_labelled(matrix):
    class FakeGit:
        def commits(self, base, head):
            return []

        def changed_files(self, sha):
            return []

    spa.configure(git_reader=FakeGit(), record_reader=lambda d: [])
    assert spa.audit_range("b", "h", matrix, records_dir="x")["records_source"] == "injected"


# ---- R4-mut: mutation survivors -----------------------------------------------------

def test_merge_commit_never_diffed_even_if_reader_would_list_files(matrix):
    """Kills 'merge commit audited as a non-merge': a diffed merge would be NO_RECORD."""
    class FakeGit:
        def commits(self, base, head):
            return [spa.CommitInfo("a" * 40, ("b" * 40, "c" * 40), "Merge branch 'x'")]

        def changed_files(self, sha):
            return ["src/q.py", "docs/r.md"]

    spa.configure(git_reader=FakeGit(), record_reader=lambda d: [])
    c = _one(spa.audit_range("b", "h", matrix, records_dir="x"))
    assert c["merge"] is True and c["verdict"] == "PASS" and c["classes"] == []
    assert any("merge commit" in n for n in c["notes"])


def test_rename_across_classes_judged_by_both_paths(repo, matrix):
    """Kills enabling rename detection (-M): the old path's class must be audited too."""
    _commit(repo, {"src/keep.py": "same content\n" * 20}, "add")
    mid = _base(repo)
    (repo / "docs").mkdir()
    _git(repo, "mv", "src/keep.py", "docs/keep.md")
    _git(repo, "commit", "-q", "-m", "move code to docs")
    sha = _base(repo)
    _record(repo, "r1", sha, ["Y-2"])
    c = _one(_audit(repo, matrix, mid))
    assert c["classes"] == ["engine", "writing"]
    assert c["verdict"] == "VIOLATION" and c["uncovered_classes"] == ["engine"]
    _record(repo, "r2", sha, ["X-1"])
    assert _one(_audit(repo, matrix, mid))["verdict"] == "PASS"
