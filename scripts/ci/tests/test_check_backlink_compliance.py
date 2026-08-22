"""Tests for scripts/ci/checks/check_backlink_compliance.py (TC14).

Covers:
  - diff_touches_aspose_com_link(): the scoping heuristic that keeps this
    gate from blocking on pre-existing, unrelated backlink debt.
  - End-to-end (subprocess): a genuinely new/newly-edited bad anchor on a
    staged file blocks; an untouched pre-existing bad anchor does not;
    --scan mode checks regardless of diff content.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
CHECKER = REPO_ROOT / "scripts" / "ci" / "checks" / "check_backlink_compliance.py"

sys.path.insert(0, str(CHECKER.parent))
import check_backlink_compliance as cbc  # noqa: E402


def _run_checker(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(CHECKER), *args, "--repo-root", str(cwd)],
        capture_output=True, text=True, cwd=str(cwd),
    )


def _init_repo(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True)


def _write_fixture_data(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "families.json").write_text(json.dumps({"pdf": "Aspose.PDF"}), encoding="utf-8")
    # _load_display_maps() reads platforms from metrics_taxonomy.yaml, NOT
    # data/platforms.json -- a real file this fixture must mirror the shape
    # of, discovered live when this test initially failed with a spurious
    # WRONG_ANCHOR_TEXT (platforms_map silently fell back to {} and "cpp"
    # rendered as "Cpp" instead of "C++").
    taxonomy_dir = tmp_path / "scripts" / "pipeline" / "config"
    taxonomy_dir.mkdir(parents=True, exist_ok=True)
    (taxonomy_dir / "metrics_taxonomy.yaml").write_text(
        "platforms:\n  cpp: \"C++\"\n", encoding="utf-8",
    )
    (data_dir / "aspose_com_targets.json").write_text(json.dumps({
        "schema_version": "1.0",
        "provenance": {"generated_at": "2026-01-01T00:00:00Z"},
        "targets": {
            "kb.aspose.com": {
                "families": {"pdf": {"url": "https://kb.aspose.com/pdf/", "http_status": 200}},
                "platforms": {"pdf/cpp": {"url": "https://kb.aspose.com/pdf/cpp/", "http_status": 200}},
            },
        },
        "all_urls": {},
        "unavailable_sources": [],
        "family_platform_matrix": {},
    }), encoding="utf-8")


def _write_kb_page(tmp_path: Path, rel: str, body: str) -> Path:
    fp = tmp_path / rel
    fp.parent.mkdir(parents=True, exist_ok=True)
    fp.write_text(f"---\ntitle: Test\n---\n\n{body}\n", encoding="utf-8")
    return fp


class TestDiffTouchesAsposeComLink:
    def test_staged_new_file_with_link_is_touched(self, tmp_path):
        _init_repo(tmp_path)
        fp = _write_kb_page(tmp_path, "page.md", "- [x](https://kb.aspose.com/pdf/)")
        subprocess.run(["git", "add", "page.md"], cwd=tmp_path, check=True)
        assert cbc.diff_touches_aspose_com_link(fp, tmp_path) is True

    def test_staged_file_unrelated_change_not_touched(self, tmp_path):
        _init_repo(tmp_path)
        fp = _write_kb_page(tmp_path, "page.md", "- [x](https://kb.aspose.com/pdf/)\n\nSome text.")
        subprocess.run(["git", "add", "page.md"], cwd=tmp_path, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "baseline"], cwd=tmp_path, check=True)

        fp.write_text(fp.read_text(encoding="utf-8") + "\nMore unrelated text.\n", encoding="utf-8")
        subprocess.run(["git", "add", "page.md"], cwd=tmp_path, check=True)
        assert cbc.diff_touches_aspose_com_link(fp, tmp_path) is False

    def test_staged_file_edited_link_is_touched(self, tmp_path):
        _init_repo(tmp_path)
        fp = _write_kb_page(tmp_path, "page.md", "- [x](https://kb.aspose.com/pdf/)")
        subprocess.run(["git", "add", "page.md"], cwd=tmp_path, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "baseline"], cwd=tmp_path, check=True)

        fp.write_text("- [x](https://kb.aspose.com/pdf/cpp/)\n", encoding="utf-8")
        subprocess.run(["git", "add", "page.md"], cwd=tmp_path, check=True)
        assert cbc.diff_touches_aspose_com_link(fp, tmp_path) is True


class TestCheckerEndToEnd:
    def test_newly_staged_wrong_anchor_blocks(self, tmp_path):
        _init_repo(tmp_path)
        _write_fixture_data(tmp_path)
        rel = "content/kb.aspose.org/en/pdf/cpp/faq.md"
        fp = _write_kb_page(tmp_path, rel, "## See Also\n\n- [wrong wording](https://kb.aspose.com/pdf/cpp/)\n")
        subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)

        result = _run_checker([rel], tmp_path)
        assert result.returncode == 1
        assert "WRONG_ANCHOR_TEXT" in result.stdout

    def test_pre_existing_bad_anchor_untouched_by_diff_passes(self, tmp_path):
        """The core safety property: a page with an ALREADY-bad anchor,
        edited elsewhere (not touching the link), must not block."""
        _init_repo(tmp_path)
        _write_fixture_data(tmp_path)
        rel = "content/kb.aspose.org/en/pdf/cpp/faq.md"
        fp = _write_kb_page(
            tmp_path, rel,
            "## See Also\n\n- [wrong wording](https://kb.aspose.com/pdf/cpp/)\n\nSome prose.\n",
        )
        subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "baseline (already has the defect)"], cwd=tmp_path, check=True)

        fp.write_text(fp.read_text(encoding="utf-8") + "\nAn unrelated fix.\n", encoding="utf-8")
        subprocess.run(["git", "add", rel], cwd=tmp_path, check=True)

        result = _run_checker([rel], tmp_path)
        assert result.returncode == 0

    def test_scan_mode_checks_regardless_of_diff(self, tmp_path):
        """--scan mode must catch the same pre-existing defect the
        diff-scoped mode above correctly skips -- for full-repo CI reporting."""
        _init_repo(tmp_path)
        _write_fixture_data(tmp_path)
        rel = "content/kb.aspose.org/en/pdf/cpp/faq.md"
        _write_kb_page(tmp_path, rel, "## See Also\n\n- [wrong wording](https://kb.aspose.com/pdf/cpp/)\n")
        subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "baseline"], cwd=tmp_path, check=True)

        result = _run_checker(["--scan", rel], tmp_path)
        assert result.returncode == 1
        assert "WRONG_ANCHOR_TEXT" in result.stdout

    def test_compliant_page_passes(self, tmp_path):
        _init_repo(tmp_path)
        _write_fixture_data(tmp_path)
        rel = "content/kb.aspose.org/en/pdf/cpp/faq.md"
        _write_kb_page(
            tmp_path, rel,
            "## See Also\n\n- [Aspose.PDF for C++ — Enterprise Knowledge Base](https://kb.aspose.com/pdf/cpp/)\n",
        )
        subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)

        result = _run_checker([rel], tmp_path)
        assert result.returncode == 0

    def test_non_content_files_ignored(self, tmp_path):
        _init_repo(tmp_path)
        _write_fixture_data(tmp_path)
        (tmp_path / "README.md").write_text("hello", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)

        result = _run_checker(["README.md"], tmp_path)
        assert result.returncode == 0

    def test_no_files_prints_help_and_exits_2(self, tmp_path):
        result = _run_checker([], tmp_path)
        assert result.returncode == 2

    def test_files_from_flag_reads_file_list(self, tmp_path):
        """Matches audit.py's own --files-from convention, used for large
        commits to avoid OS argument-list-too-long errors."""
        _init_repo(tmp_path)
        _write_fixture_data(tmp_path)
        rel = "content/kb.aspose.org/en/pdf/cpp/faq.md"
        _write_kb_page(tmp_path, rel, "## See Also\n\n- [wrong wording](https://kb.aspose.com/pdf/cpp/)\n")
        subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)

        list_file = tmp_path / "files.txt"
        list_file.write_text(rel + "\n", encoding="utf-8")

        result = _run_checker(["--files-from", str(list_file)], tmp_path)
        assert result.returncode == 1
        assert "WRONG_ANCHOR_TEXT" in result.stdout
