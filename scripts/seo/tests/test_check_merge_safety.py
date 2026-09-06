"""SEO-SCHEMA-A-WORKFLOW-UPDATE: real-git regression tests for the auto-merge
safety gates (check_merge_safety.py).

Per this mission's own self-audit (v8): a gate that looks correct in a
taskcard's acceptance_checks list can still have an implementation bug that
lets a bad run through silently. Each gate is proven here against a REAL
scratch git repo with a REAL failing diff, not just asserted correct on
paper -- untested claims of "the gate works" are not accepted as closure
evidence for SEO-SCHEMA-A-WORKFLOW-UPDATE.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parents[2]
_PIPELINE = _SCRIPTS / "pipeline"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))
if str(_PIPELINE) not in sys.path:
    sys.path.insert(0, str(_PIPELINE))

import seo.pipeline.check_merge_safety as check_merge_safety  # noqa: E402


def _git(args, cwd):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True,
                   encoding="utf-8", errors="replace")


def _rev_parse_head(cwd):
    result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=cwd, capture_output=True, text=True,
                            encoding="utf-8", errors="replace", check=True)
    return result.stdout.strip()


def _init_repo(tmp_path):
    _git(["init", "-q"], tmp_path)
    _git(["config", "user.email", "test@example.com"], tmp_path)
    _git(["config", "user.name", "Test"], tmp_path)
    return tmp_path


def _commit_all(cwd, message):
    _git(["add", "-A"], cwd)
    _git(["commit", "-q", "-m", message], cwd)


def test_passes_when_diff_scoped_shape_correct_and_no_regression(tmp_path):
    repo = _init_repo(tmp_path)
    (repo / "keywords").mkdir()
    (repo / "keywords" / "tex.json").write_text(
        json.dumps([{"pageTitle": "A", "keywords": ["x"]}]), encoding="utf-8"
    )
    _commit_all(repo, "base")
    base_sha = _rev_parse_head(repo)

    (repo / "keywords" / "tex.json").write_text(
        json.dumps([
            {"pageTitle": "A", "keywords": ["x"]},
            {"pageTitle": "B", "sourcePath": "content/x.md", "keywords": ["y"]},
        ]),
        encoding="utf-8",
    )
    _commit_all(repo, "add entry")

    passed, messages = check_merge_safety.run_checks(base_sha, repo_root=repo)
    assert passed, messages


def test_fails_when_non_keywords_path_changed(tmp_path):
    """Real failing case for Gate 2: a run that also touched a non-keywords
    path must not pass, even if the keywords/ content itself is fine."""
    repo = _init_repo(tmp_path)
    (repo / "keywords").mkdir()
    (repo / "keywords" / "tex.json").write_text(json.dumps([]), encoding="utf-8")
    (repo / "scripts").mkdir()
    (repo / "scripts" / "other.py").write_text("x = 1\n", encoding="utf-8")
    _commit_all(repo, "base")
    base_sha = _rev_parse_head(repo)

    (repo / "scripts" / "other.py").write_text("x = 2\n", encoding="utf-8")
    _commit_all(repo, "touch non-keywords path")

    passed, messages = check_merge_safety.run_checks(base_sha, repo_root=repo)
    assert not passed
    assert any("GATE 2 FAILED" in m for m in messages)


def test_passes_when_migration_state_file_changed_alongside_keywords(tmp_path):
    """SEO-SCHEMA-A-WORKFLOW-UPDATE Migration Plan v2: the migration state
    file is a deliberate, narrow exception to Gate 2 -- a run that updates
    both keywords/*.json and exactly this one file must still pass."""
    repo = _init_repo(tmp_path)
    (repo / "keywords").mkdir()
    (repo / "keywords" / "tex.json").write_text(json.dumps([]), encoding="utf-8")
    (repo / "data").mkdir()
    (repo / "data" / "seo_schema_a_migration_state.json").write_text(json.dumps({"families": {}}), encoding="utf-8")
    _commit_all(repo, "base")
    base_sha = _rev_parse_head(repo)

    (repo / "keywords" / "tex.json").write_text(
        json.dumps([{"pageTitle": "A", "keywords": ["x"]}]), encoding="utf-8"
    )
    (repo / "data" / "seo_schema_a_migration_state.json").write_text(
        json.dumps({"families": {"tex": {"status": "done"}}}), encoding="utf-8"
    )
    _commit_all(repo, "migration progress")

    passed, messages = check_merge_safety.run_checks(base_sha, repo_root=repo)
    assert passed, messages


def test_fails_when_a_different_non_keywords_path_changed_alongside_migration_state(tmp_path):
    """The Gate 2 exception is exactly one path, not a broader allowance --
    a run touching some OTHER non-keywords path must still fail, even if
    the migration state file is also present in the diff."""
    repo = _init_repo(tmp_path)
    (repo / "keywords").mkdir()
    (repo / "keywords" / "tex.json").write_text(json.dumps([]), encoding="utf-8")
    (repo / "data").mkdir()
    (repo / "data" / "seo_schema_a_migration_state.json").write_text(json.dumps({}), encoding="utf-8")
    (repo / "scripts").mkdir()
    (repo / "scripts" / "other.py").write_text("x = 1\n", encoding="utf-8")
    _commit_all(repo, "base")
    base_sha = _rev_parse_head(repo)

    (repo / "data" / "seo_schema_a_migration_state.json").write_text(json.dumps({"a": 1}), encoding="utf-8")
    (repo / "scripts" / "other.py").write_text("x = 2\n", encoding="utf-8")
    _commit_all(repo, "migration state + unrelated script change")

    passed, messages = check_merge_safety.run_checks(base_sha, repo_root=repo)
    assert not passed
    assert any("GATE 2 FAILED" in m for m in messages)


def test_fails_on_unexpected_entry_keys(tmp_path):
    """Real failing case for Gate 3: reproduces the 2026-03-27 contamination
    shape (a stray 'tags' key) -- must not pass."""
    repo = _init_repo(tmp_path)
    (repo / "keywords").mkdir()
    (repo / "keywords" / "tex.json").write_text(json.dumps([]), encoding="utf-8")
    _commit_all(repo, "base")
    base_sha = _rev_parse_head(repo)

    (repo / "keywords" / "tex.json").write_text(
        json.dumps([{"pageTitle": "A", "keywords": ["x"], "tags": ["contaminated"]}]),
        encoding="utf-8",
    )
    _commit_all(repo, "contaminate")

    passed, messages = check_merge_safety.run_checks(base_sha, repo_root=repo)
    assert not passed
    assert any("GATE 3 FAILED" in m for m in messages)


def test_passes_with_title_ready_variants_and_schema_version_keys(tmp_path):
    """SEO-SCHEMA-A-DUAL-FIELD-GENERATION: the two new, optional, additive
    keys must not trip Gate 3 -- otherwise the very next scheduled Schema A
    refresh PR that regenerates any entry loses its auto-merge eligibility."""
    repo = _init_repo(tmp_path)
    (repo / "keywords").mkdir()
    (repo / "keywords" / "tex.json").write_text(json.dumps([]), encoding="utf-8")
    _commit_all(repo, "base")
    base_sha = _rev_parse_head(repo)

    (repo / "keywords" / "tex.json").write_text(
        json.dumps([{
            "pageTitle": "A",
            "sourcePath": "content/x.md",
            "keywords": ["x"],
            "title_ready_variants": {"x": "X Title"},
            "schema_version": 2,
        }]),
        encoding="utf-8",
    )
    _commit_all(repo, "dual-field entry")

    passed, messages = check_merge_safety.run_checks(base_sha, repo_root=repo)
    assert passed, messages


def test_fails_when_title_ready_variant_exceeds_word_limit(tmp_path):
    """SEO-DUAL-FIELD-VARIANT-LENGTH-GATE-RESOLVER-1: Gate 3 previously
    checked entry KEYS only, never title_ready_variants VALUES -- confirmed
    live to have let a real refresh PR (#81) merge 254 over-length variants
    (up to 8 words) into keywords/{cells,slides}.json. This real-git repro
    uses the exact shape of one of those real entries."""
    repo = _init_repo(tmp_path)
    (repo / "keywords").mkdir()
    (repo / "keywords" / "cells.json").write_text(json.dumps([]), encoding="utf-8")
    _commit_all(repo, "base")
    base_sha = _rev_parse_head(repo)

    (repo / "keywords" / "cells.json").write_text(
        json.dumps([{
            "pageTitle": "A",
            "sourcePath": "content/x.md",
            "keywords": ["write excel in c++ open source"],
            "title_ready_variants": {
                "write excel in c++ open source": "Open Source Library To Write Excel In C++",
            },
            "schema_version": 2,
        }]),
        encoding="utf-8",
    )
    _commit_all(repo, "over-length variant")

    passed, messages = check_merge_safety.run_checks(base_sha, repo_root=repo)
    assert not passed
    assert any("GATE 3 FAILED" in m for m in messages)
    assert any("exceeds" in m and "words" in m for m in messages)


def test_passes_when_title_ready_variant_is_exactly_at_the_word_limit(tmp_path):
    repo = _init_repo(tmp_path)
    (repo / "keywords").mkdir()
    (repo / "keywords" / "tex.json").write_text(json.dumps([]), encoding="utf-8")
    _commit_all(repo, "base")
    base_sha = _rev_parse_head(repo)

    (repo / "keywords" / "tex.json").write_text(
        json.dumps([{
            "pageTitle": "A",
            "sourcePath": "content/x.md",
            "keywords": ["x"],
            "title_ready_variants": {"x": "One Two Three Four Five Six"},
            "schema_version": 2,
        }]),
        encoding="utf-8",
    )
    _commit_all(repo, "boundary-length variant")

    passed, messages = check_merge_safety.run_checks(base_sha, repo_root=repo)
    assert passed, messages


def test_fails_on_entry_count_regression(tmp_path):
    """Real failing case for Gate 4: a run that silently drops an entry
    (e.g. a rename that fails a lookup) must not pass."""
    repo = _init_repo(tmp_path)
    (repo / "keywords").mkdir()
    (repo / "keywords" / "tex.json").write_text(
        json.dumps([{"pageTitle": "A", "keywords": ["x"]}, {"pageTitle": "B", "keywords": ["y"]}]),
        encoding="utf-8",
    )
    _commit_all(repo, "base")
    base_sha = _rev_parse_head(repo)

    (repo / "keywords" / "tex.json").write_text(
        json.dumps([{"pageTitle": "A", "keywords": ["x"]}]), encoding="utf-8"
    )
    _commit_all(repo, "drop an entry")

    passed, messages = check_merge_safety.run_checks(base_sha, repo_root=repo)
    assert not passed
    assert any("GATE 4 FAILED" in m for m in messages)


def test_new_family_file_is_not_a_regression(tmp_path):
    """A brand-new family file (no prior version at base_ref) must not be
    misread as a 0-entry regression -- it has nothing to regress from."""
    repo = _init_repo(tmp_path)
    (repo / "keywords").mkdir()
    (repo / "keywords" / "tex.json").write_text(json.dumps([]), encoding="utf-8")
    _commit_all(repo, "base")
    base_sha = _rev_parse_head(repo)

    (repo / "keywords" / "newfam.json").write_text(
        json.dumps([{"pageTitle": "A", "keywords": ["x"]}]), encoding="utf-8"
    )
    _commit_all(repo, "add new family file")

    passed, messages = check_merge_safety.run_checks(base_sha, repo_root=repo)
    assert passed, messages


def test_fails_gate5_when_family_change_volume_exceeds_static_cap(tmp_path, monkeypatch):
    """Real failing case for Gate 5 (Contract G): a run that regenerates more
    entries in one family than change_budgets.yaml's max_pages_per_run
    permits must not pass, even though Gates 2-4 are clean."""
    import seo.pipeline.change_budget as change_budget
    monkeypatch.setattr(
        change_budget, "load_budgets",
        lambda path=None: {
            "max_pages_per_run": 2, "max_pages_per_site_per_run": 2,
            "max_title_changes_per_run": 100, "max_description_changes_per_run": 100,
            "max_total_metadata_changes_per_run": 100, "anomaly_multiplier": 3.0,
            "warmup_runs": 3, "max_cross_mechanism_changes_per_family_per_week": 100,
        },
    )
    repo = _init_repo(tmp_path)
    (repo / "keywords").mkdir()
    (repo / "keywords" / "tex.json").write_text(
        json.dumps([
            {"pageTitle": "A", "sourcePath": "a.md", "keywords": ["x"]},
            {"pageTitle": "B", "sourcePath": "b.md", "keywords": ["y"]},
            {"pageTitle": "C", "sourcePath": "c.md", "keywords": ["z"]},
        ]),
        encoding="utf-8",
    )
    _commit_all(repo, "base")
    base_sha = _rev_parse_head(repo)

    # Regenerate all 3 entries in one run -- 3 changed entries > cap of 2.
    (repo / "keywords" / "tex.json").write_text(
        json.dumps([
            {"pageTitle": "A2", "sourcePath": "a.md", "keywords": ["x2"]},
            {"pageTitle": "B2", "sourcePath": "b.md", "keywords": ["y2"]},
            {"pageTitle": "C2", "sourcePath": "c.md", "keywords": ["z2"]},
        ]),
        encoding="utf-8",
    )
    _commit_all(repo, "regenerate all 3")

    passed, messages = check_merge_safety.run_checks(base_sha, repo_root=repo)
    assert not passed
    assert any("GATE 5 FAILED" in m for m in messages)


def test_passes_gate5_when_family_change_volume_within_caps(tmp_path, monkeypatch):
    import seo.pipeline.change_budget as change_budget
    monkeypatch.setattr(
        change_budget, "load_budgets",
        lambda path=None: {
            "max_pages_per_run": 15, "max_pages_per_site_per_run": 10,
            "max_title_changes_per_run": 10, "max_description_changes_per_run": 15,
            "max_total_metadata_changes_per_run": 20, "anomaly_multiplier": 3.0,
            "warmup_runs": 3, "max_cross_mechanism_changes_per_family_per_week": 20,
        },
    )
    repo = _init_repo(tmp_path)
    (repo / "keywords").mkdir()
    (repo / "keywords" / "tex.json").write_text(
        json.dumps([{"pageTitle": "A", "sourcePath": "a.md", "keywords": ["x"]}]),
        encoding="utf-8",
    )
    _commit_all(repo, "base")
    base_sha = _rev_parse_head(repo)

    (repo / "keywords" / "tex.json").write_text(
        json.dumps([
            {"pageTitle": "A", "sourcePath": "a.md", "keywords": ["x"]},
            {"pageTitle": "B", "sourcePath": "b.md", "keywords": ["y"]},
        ]),
        encoding="utf-8",
    )
    _commit_all(repo, "add one entry")

    passed, messages = check_merge_safety.run_checks(base_sha, repo_root=repo)
    assert passed, messages
    assert any("GATE 5 passed" in m for m in messages)


def test_gate5_counts_regenerated_entries_with_unchanged_count_as_changed(tmp_path, monkeypatch):
    """A regenerated entry that keeps the same sourcePath and the same total
    count (so Gate 4 sees no regression) must still count as a real change
    for the budget check -- proves _count_changed_entries doesn't just diff
    len(before) vs len(after)."""
    import seo.pipeline.change_budget as change_budget
    monkeypatch.setattr(
        change_budget, "load_budgets",
        lambda path=None: {
            "max_pages_per_run": 0, "max_pages_per_site_per_run": 0,
            "max_title_changes_per_run": 100, "max_description_changes_per_run": 100,
            "max_total_metadata_changes_per_run": 100, "anomaly_multiplier": 3.0,
            "warmup_runs": 3, "max_cross_mechanism_changes_per_family_per_week": 100,
        },
    )
    repo = _init_repo(tmp_path)
    (repo / "keywords").mkdir()
    (repo / "keywords" / "tex.json").write_text(
        json.dumps([{"pageTitle": "A", "sourcePath": "a.md", "keywords": ["x"]}]),
        encoding="utf-8",
    )
    _commit_all(repo, "base")
    base_sha = _rev_parse_head(repo)

    # Same sourcePath, same count, different content -- a real regeneration.
    (repo / "keywords" / "tex.json").write_text(
        json.dumps([{"pageTitle": "A-regenerated", "sourcePath": "a.md", "keywords": ["x-new"]}]),
        encoding="utf-8",
    )
    _commit_all(repo, "regenerate in place")

    passed, messages = check_merge_safety.run_checks(base_sha, repo_root=repo)
    assert not passed
    assert any("GATE 5 FAILED" in m and "changed_entries=1" in m for m in messages)


def test_no_diff_passes_trivially(tmp_path):
    repo = _init_repo(tmp_path)
    (repo / "keywords").mkdir()
    (repo / "keywords" / "tex.json").write_text(json.dumps([]), encoding="utf-8")
    _commit_all(repo, "base")
    base_sha = _rev_parse_head(repo)

    passed, messages = check_merge_safety.run_checks(base_sha, repo_root=repo)
    assert passed, messages
