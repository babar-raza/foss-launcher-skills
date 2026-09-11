"""Tests for check_governance_doc_links.py — H6 (2026-09-11) regression guard
for the governance-hook remediation-doc-link-integrity gap
(reports/skill-gaps/2026-09-11-imaging-net-pipeline-hardening-prerequisites.md).
"""
from __future__ import annotations

import sys
from pathlib import Path

_CI_ROOT = Path(__file__).resolve().parent.parent / "checks"
if str(_CI_ROOT) not in sys.path:
    sys.path.insert(0, str(_CI_ROOT))

import pytest
import check_governance_doc_links as gdl  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_gdl():
    yield
    gdl.configure()


def _write_hook(hooks_dir: Path, name: str, body: str) -> Path:
    hooks_dir.mkdir(parents=True, exist_ok=True)
    path = hooks_dir / name
    path.write_text(body, encoding="utf-8")
    return path


class TestFindDocReferences:
    def test_finds_single_doc_reference(self, tmp_path):
        hooks_dir = tmp_path / "scripts" / "ci" / "hooks"
        _write_hook(hooks_dir, "check_example_hook.sh", '_gov_block "x" "y" "z" "SKIP=1" "docs/EXAMPLE.md"\n')
        refs = gdl.find_doc_references(hooks_dir)
        assert refs == {"check_example_hook.sh": ["docs/EXAMPLE.md"]}

    def test_finds_multi_doc_comma_separated_reference(self, tmp_path):
        """The one real call site (check_write_path_hook.sh:178) cites two
        docs in a single comma-separated argument -- both must be extracted."""
        hooks_dir = tmp_path / "scripts" / "ci" / "hooks"
        _write_hook(
            hooks_dir, "check_example_hook.sh",
            '_gov_block "x" "y" "z" "SKIP=1" "docs/A.md, docs/B.md"\n',
        )
        refs = gdl.find_doc_references(hooks_dir)
        assert refs == {"check_example_hook.sh": ["docs/A.md", "docs/B.md"]}

    def test_deduplicates_repeated_references_within_one_hook(self, tmp_path):
        hooks_dir = tmp_path / "scripts" / "ci" / "hooks"
        _write_hook(
            hooks_dir, "check_example_hook.sh",
            '_gov_block "a" "b" "c" "d" "docs/EXAMPLE.md"\n'
            '_gov_block "e" "f" "g" "h" "docs/EXAMPLE.md"\n',
        )
        refs = gdl.find_doc_references(hooks_dir)
        assert refs == {"check_example_hook.sh": ["docs/EXAMPLE.md"]}

    def test_ignores_the_gov_block_helper_definition_itself(self, tmp_path):
        """_gov_block.sh is the function DEFINITION, never a caller -- must
        not be scanned for doc citations even if its own docstring/comments
        happen to mention a docs/*.md path."""
        hooks_dir = tmp_path / "scripts" / "ci" / "hooks"
        _write_hook(hooks_dir, "_gov_block.sh", '# see docs/GOVERNANCE_QUICKSTART.md\n_gov_block() { :; }\n')
        refs = gdl.find_doc_references(hooks_dir)
        assert refs == {}

    def test_no_hooks_dir_returns_empty(self, tmp_path):
        assert gdl.find_doc_references(tmp_path / "nope") == {}

    def test_hook_with_no_doc_reference_is_omitted(self, tmp_path):
        hooks_dir = tmp_path / "scripts" / "ci" / "hooks"
        _write_hook(hooks_dir, "check_no_doc_hook.sh", 'echo "nothing governance-shaped here"\n')
        assert gdl.find_doc_references(hooks_dir) == {}


class TestFindBrokenLinks:
    def test_missing_doc_is_reported_broken(self, tmp_path):
        gdl.configure(repo_root=tmp_path)
        hooks_dir = tmp_path / "scripts" / "ci" / "hooks"
        _write_hook(hooks_dir, "check_example_hook.sh", '_gov_block "a" "b" "c" "d" "docs/MISSING.md"\n')
        broken = gdl.find_broken_links(hooks_dir)
        assert broken == {"check_example_hook.sh": ["docs/MISSING.md"]}

    def test_existing_doc_is_not_reported_broken(self, tmp_path):
        gdl.configure(repo_root=tmp_path)
        (tmp_path / "docs").mkdir()
        (tmp_path / "docs" / "REAL.md").write_text("# real\n", encoding="utf-8")
        hooks_dir = tmp_path / "scripts" / "ci" / "hooks"
        _write_hook(hooks_dir, "check_example_hook.sh", '_gov_block "a" "b" "c" "d" "docs/REAL.md"\n')
        assert gdl.find_broken_links(hooks_dir) == {}

    def test_this_repos_real_hooks_have_zero_broken_links(self):
        """The real regression proof: with H6's docs/GOVERNANCE_QUICKSTART.md
        and docs/BYPASS_REGISTRY.md now created, this repo's own real hooks
        must resolve cleanly -- confirmed broken (9 references, 7 hooks) via
        this exact check before those two docs existed."""
        broken = gdl.find_broken_links()
        assert broken == {}
        refs = gdl.find_doc_references()
        assert len(refs) > 0  # sanity: the scan actually found real references


class TestMain:
    def test_main_exits_0_when_all_links_resolve(self, tmp_path, capsys):
        gdl.configure(repo_root=tmp_path)
        (tmp_path / "docs").mkdir()
        (tmp_path / "docs" / "REAL.md").write_text("# real\n", encoding="utf-8")
        hooks_dir = tmp_path / "scripts" / "ci" / "hooks"
        _write_hook(hooks_dir, "check_example_hook.sh", '_gov_block "a" "b" "c" "d" "docs/REAL.md"\n')

        import unittest.mock as mock
        with mock.patch.object(gdl, "find_doc_references", lambda hooks_dir=None: {"check_example_hook.sh": ["docs/REAL.md"]}):
            with mock.patch.object(gdl, "find_broken_links", lambda hooks_dir=None: {}):
                exit_code = gdl.main([])
        assert exit_code == 0
        assert "OK:" in capsys.readouterr().out

    def test_main_exits_1_when_a_link_is_broken(self, tmp_path, capsys):
        import unittest.mock as mock
        with mock.patch.object(gdl, "find_broken_links", lambda hooks_dir=None: {"check_example_hook.sh": ["docs/MISSING.md"]}):
            with mock.patch.object(gdl, "find_doc_references", lambda hooks_dir=None: {"check_example_hook.sh": ["docs/MISSING.md"]}):
                exit_code = gdl.main([])
        assert exit_code == 1
        out = capsys.readouterr().out
        assert "BROKEN" in out
        assert "docs/MISSING.md" in out

    def test_main_json_mode(self, tmp_path, capsys):
        import json
        import unittest.mock as mock
        with mock.patch.object(gdl, "find_broken_links", lambda hooks_dir=None: {}):
            with mock.patch.object(gdl, "find_doc_references", lambda hooks_dir=None: {}):
                exit_code = gdl.main(["--json"])
        assert exit_code == 0
        parsed = json.loads(capsys.readouterr().out)
        assert parsed == {"references": {}, "broken": {}}
