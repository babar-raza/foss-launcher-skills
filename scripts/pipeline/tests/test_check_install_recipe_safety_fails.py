"""Tests for scripts/ci/checks/check_install_recipe_safety_fails.py
(PKGINSTALL-GRADE-SAFETY-OVERRIDE stopgap).
"""
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
_LIB_DIR = _REPO_ROOT / "scripts" / "pipeline" / "lib"
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))
_CI_CHECKS_DIR = _REPO_ROOT / "scripts" / "ci" / "checks"
if str(_CI_CHECKS_DIR) not in sys.path:
    sys.path.insert(0, str(_CI_CHECKS_DIR))

import content_eval.evaluators.install_recipe as _ir_mod  # noqa: E402
import check_install_recipe_safety_fails as sut  # noqa: E402


_BARCODE_PYTHON_UNPUBLISHED = {
    "barcode": {"python": {
        "registry_type": "pypi",
        "candidate": {"name": "aspose-barcode-foss"},
        "candidate_owner": "asposefoss",
        "verification": {"published": False, "verified_at": "2026-08-01", "verified_owner": None,
                          "evidence_url": None, "method": None},
        "owner_match": None,
    }}
}


def _write_page(tmp_path: Path, rel_path: str, body: str) -> Path:
    path = tmp_path / "content" / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def teardown_function(_fn):
    _ir_mod.configure()


class TestCheckFiles:
    def test_no_files_given(self):
        assert sut.check_files([]) == []

    def test_clean_file_produces_no_findings(self, tmp_path):
        _ir_mod.configure(knowledge_root=tmp_path / "knowledge", registry=_BARCODE_PYTHON_UNPUBLISHED)
        path = _write_page(
            tmp_path, "docs.aspose.org/en/barcode/python/getting-started/installation.md",
            "---\ntitle: Installation\n---\n\n## Installation\n\ngit clone https://github.com/aspose-barcode-foss/example.git\n",
        )
        findings = sut.check_files([str(path)])
        assert findings == []

    def test_publish_claim_contradiction_is_caught_independent_of_grade(self, tmp_path):
        """The whole point of this stopgap: it never consults any stored
        grade at all -- it just re-runs the 2 real checks fresh."""
        _ir_mod.configure(knowledge_root=tmp_path / "knowledge", registry=_BARCODE_PYTHON_UNPUBLISHED)
        path = _write_page(
            tmp_path, "docs.aspose.org/en/barcode/python/getting-started/installation.md",
            "---\ntitle: Installation\ngrade: A\n---\n\n"
            "## Installation\n\nInstall from PyPI: `pip install aspose-barcode-foss`\n",
        )
        findings = sut.check_files([str(path)])
        assert len(findings) >= 1
        assert findings[0]["category"] == "IR_PUBLISH_CLAIM"

    def test_unpublished_disclosure_is_caught(self, tmp_path):
        _ir_mod.configure(knowledge_root=tmp_path / "knowledge", registry=_BARCODE_PYTHON_UNPUBLISHED)
        path = _write_page(
            tmp_path, "docs.aspose.org/en/barcode/python/getting-started/installation.md",
            "---\ntitle: Installation\n---\n\n"
            "## Installation\n\nAspose.BarCode FOSS for Python is not yet published on PyPI.\n",
        )
        findings = sut.check_files([str(path)])
        assert len(findings) >= 1
        assert findings[0]["category"] == "IR_UNPUBLISHED_DISCLOSURE"

    def test_install_accuracy_findings_are_never_included(self, tmp_path):
        """This stopgap only ever runs the 2 safety checks -- a wrong-
        package-name H-16 finding (category 'IR', untouched) must not
        appear here at all."""
        registry = {
            "3d": {"net": {
                "registry_type": "nuget",
                "candidate": {"name": "Aspose.3D.FOSS"},
                "candidate_owner": "asposefoss",
                "verification": {"published": True, "verified_at": None, "verified_owner": None,
                                  "evidence_url": None, "method": None},
                "owner_match": None,
            }}
        }
        _ir_mod.configure(knowledge_root=tmp_path / "knowledge", registry=registry)
        path = _write_page(
            tmp_path, "docs.aspose.org/en/3d/net/getting-started/installation.md",
            "---\ntitle: Installation\n---\n\n"
            "## Installation\n\n```\ndotnet add package Aspose.3D.Converter\n```\n",
        )
        findings = sut.check_files([str(path)])
        assert findings == [], f"H-16 accuracy findings (category IR) must never appear here: {findings}"


class TestMain:
    def test_no_files_exits_zero(self, capsys):
        assert sut.main([]) == 0

    def test_clean_files_exit_zero(self, tmp_path, capsys):
        _ir_mod.configure(knowledge_root=tmp_path / "knowledge", registry=_BARCODE_PYTHON_UNPUBLISHED)
        path = _write_page(
            tmp_path, "docs.aspose.org/en/barcode/python/getting-started/installation.md",
            "---\ntitle: Installation\n---\n\n## Installation\n\ngit clone https://example.com/repo.git\n",
        )
        assert sut.main([str(path)]) == 0

    def test_finding_exits_one_and_prints_to_stderr(self, tmp_path, capsys):
        _ir_mod.configure(knowledge_root=tmp_path / "knowledge", registry=_BARCODE_PYTHON_UNPUBLISHED)
        path = _write_page(
            tmp_path, "docs.aspose.org/en/barcode/python/getting-started/installation.md",
            "---\ntitle: Installation\n---\n\n## Installation\n\nInstall from PyPI: `pip install aspose-barcode-foss`\n",
        )
        exit_code = sut.main([str(path)])
        assert exit_code == 1
        captured = capsys.readouterr()
        assert "BLOCKED" in captured.err
        assert "IR_PUBLISH_CLAIM" in captured.err


# ---------------------------------------------------------------------------
# PKGINSTALL-GRADE-SAFETY-OVERRIDE-FIX D1a: the script must never REPORT clean
# for a path it did not evaluate. The review reproduced, on real fixtures: a
# nonexistent path -> exit 0 "OK ... across 1 file(s) checked"; a flat
# locale-suffix file (index.de.md) carrying a claim -> exit 0; an OK line that
# counted the paths it was given rather than the pages it evaluated.
# ---------------------------------------------------------------------------

import os  # noqa: E402
import subprocess  # noqa: E402

import pytest  # noqa: E402

_DOCS_PAGE = "docs.aspose.org/en/barcode/python/getting-started/installation.md"
_CLAIM_BODY = (
    "---\ntitle: Installation\n---\n\n## Installation\n\n"
    "Install from PyPI: `pip install aspose-barcode-foss`\n"
)
_CLEAN_BODY = (
    "---\ntitle: Installation\n---\n\n## Installation\n\n"
    "git clone https://example.com/repo.git\n"
)
_GERMAN_CLAIM_BODY = (
    "---\ntitle: Installation\n---\n\n## Installation\n\n"
    "Installieren Sie das Paket von PyPI: `pip install aspose-barcode-foss`\n"
)


class _ExplodingRegistry(dict):
    """A registry whose lookup raises, to prove an evaluation crash is an error."""

    def get(self, *_args, **_kwargs):
        raise RuntimeError("registry boom")


@pytest.fixture
def unpublished(tmp_path):
    _ir_mod.configure(knowledge_root=tmp_path / "knowledge", registry=_BARCODE_PYTHON_UNPUBLISHED)
    yield
    _ir_mod.configure()


class TestReportingAccountsForEveryPath:
    def test_nonexistent_path_is_an_error_not_ok(self, tmp_path, unpublished, capsys):
        missing = tmp_path / "content" / _DOCS_PAGE
        assert sut.main([str(missing)]) == sut.EXIT_ERROR
        captured = capsys.readouterr()
        assert "ERROR" in captured.err
        assert "does not exist" in captured.err
        assert str(missing) in captured.err
        assert "OK" not in captured.out

    def test_directory_path_is_an_error(self, tmp_path, unpublished):
        report = sut.run_check([str(tmp_path)])
        assert report.errors and "not a regular file" in report.errors[0][1]
        assert report.evaluated == []

    def test_non_markdown_file_is_skipped_and_listed_not_hidden(self, tmp_path, unpublished, capsys):
        other = tmp_path / "notes.txt"
        other.write_text("hello", encoding="utf-8")
        assert sut.main([str(other)]) == sut.EXIT_OK
        out = capsys.readouterr().out
        assert "evaluated 0 of 1" in out
        assert "skipped 1" in out
        assert f"SKIPPED {other}" in out
        assert "not a markdown file" in out

    def test_page_without_family_platform_is_skipped_not_clean(self, tmp_path, unpublished, capsys):
        """content/<site>/en/_index.md has no registry key: 'evaluated 0 of 1', with the
        reason printed -- never 'OK ... 1 file checked'."""
        page = _write_page(tmp_path, "docs.aspose.org/en/_index.md", _CLEAN_BODY)
        assert sut.main([str(page)]) == sut.EXIT_OK
        out = capsys.readouterr().out
        assert "evaluated 0 of 1" in out
        assert "no family/platform inferable" in out

    def test_summary_says_evaluated_n_of_m_and_lists_every_skip(self, tmp_path, unpublished, capsys):
        clean = _write_page(tmp_path, _DOCS_PAGE, _CLEAN_BODY)
        txt = tmp_path / "a.txt"
        txt.write_text("x", encoding="utf-8")
        site_root = _write_page(tmp_path, "kb.aspose.org/en/_index.md", _CLEAN_BODY)
        assert sut.main([str(clean), str(txt), str(site_root)]) == sut.EXIT_OK
        out = capsys.readouterr().out
        assert "OK: 0 install_recipe safety FAIL(s); evaluated 1 of 3 path(s), skipped 2" in out
        assert f"SKIPPED {txt}" in out and f"SKIPPED {site_root}" in out

    def test_every_input_path_lands_in_exactly_one_bucket(self, tmp_path, unpublished):
        clean = _write_page(tmp_path, _DOCS_PAGE, _CLEAN_BODY)
        claim = _write_page(tmp_path, "kb.aspose.org/en/barcode/python/how-to-install.md", _CLAIM_BODY)
        txt = tmp_path / "a.txt"
        txt.write_text("x", encoding="utf-8")
        missing = tmp_path / "nope.md"
        paths = [str(clean), str(claim), str(txt), str(missing)]
        report = sut.run_check(paths)
        assert report.total == 4
        assert len(report.evaluated) + len(report.skipped) + len(report.errors) == report.total
        assert set(report.evaluated) == {str(clean), str(claim)}
        assert [p for p, _ in report.skipped] == [str(txt)]
        assert [p for p, _ in report.errors] == [str(missing)]

    def test_findings_and_errors_together_exit_two_and_show_both(self, tmp_path, unpublished, capsys):
        claim = _write_page(tmp_path, _DOCS_PAGE, _CLAIM_BODY)
        missing = tmp_path / "nope.md"
        assert sut.main([str(claim), str(missing)]) == sut.EXIT_ERROR
        err = capsys.readouterr().err
        assert "IR_PUBLISH_CLAIM" in err and "does not exist" in err

    def test_duplicate_paths_are_counted_once(self, tmp_path, unpublished):
        clean = _write_page(tmp_path, _DOCS_PAGE, _CLEAN_BODY)
        report = sut.run_check([str(clean), str(clean)])
        assert report.total == 1 and report.evaluated == [str(clean)]

    def test_undecodable_file_is_an_error_not_a_traceback(self, tmp_path, unpublished, capsys):
        page = tmp_path / "content" / _DOCS_PAGE
        page.parent.mkdir(parents=True, exist_ok=True)
        page.write_bytes(b"---\ntitle: \xff\xfe\n---\n\nbody\n")
        assert sut.main([str(page)]) == sut.EXIT_ERROR
        assert "cannot load page" in capsys.readouterr().err

    def test_evaluation_crash_is_an_error_not_ok(self, tmp_path, capsys):
        _ir_mod.configure(knowledge_root=tmp_path / "knowledge", registry=_ExplodingRegistry())
        page = _write_page(tmp_path, _DOCS_PAGE, _CLEAN_BODY)
        assert sut.main([str(page)]) == sut.EXIT_ERROR
        err = capsys.readouterr().err
        assert "evaluation crashed" in err and "registry boom" in err

    def test_check_files_compat_wrapper_still_returns_findings(self, tmp_path, unpublished):
        page = _write_page(tmp_path, _DOCS_PAGE, _CLAIM_BODY)
        findings = sut.check_files([str(page)])
        assert [f["category"] for f in findings][:1] == ["IR_PUBLISH_CLAIM"]


class TestFlatLocaleSuffixFilesAreEvaluated:
    _FLAT_DE = "blog.aspose.org/barcode/python/some-post/index.de.md"

    def test_flat_locale_suffix_file_with_a_claim_is_blocked(self, tmp_path, unpublished, capsys):
        """The exact defect: index.de.md used to exit 0 because load_files() skips
        LOCALE_RE names. It must now be evaluated and BLOCKED."""
        page = _write_page(tmp_path, self._FLAT_DE, _GERMAN_CLAIM_BODY)
        assert sut.main([str(page)]) == sut.EXIT_FINDINGS
        err = capsys.readouterr().err
        assert "BLOCKED" in err and "IR_PUBLISH_CLAIM" in err and "evaluated 1 of 1" in err

    def test_flat_locale_suffix_file_is_counted_separately_when_clean(self, tmp_path, unpublished, capsys):
        page = _write_page(tmp_path, self._FLAT_DE, _CLEAN_BODY)
        assert sut.main([str(page)]) == sut.EXIT_OK
        out = capsys.readouterr().out
        assert "evaluated 1 of 1" in out
        assert "1 flat locale-suffix file(s) included" in out

    def test_english_flat_file_is_not_counted_as_locale_suffix(self, tmp_path, unpublished):
        page = _write_page(tmp_path, "blog.aspose.org/barcode/python/some-post/index.md", _CLEAN_BODY)
        report = sut.run_check([str(page)])
        assert report.evaluated == [str(page)] and report.locale_suffix_evaluated == []

    def test_directory_locale_page_with_a_claim_is_blocked(self, tmp_path, unpublished):
        page = _write_page(
            tmp_path, "docs.aspose.org/de/barcode/python/getting-started/installation.md",
            _GERMAN_CLAIM_BODY)
        assert sut.main([str(page)]) == sut.EXIT_FINDINGS

    def test_disclosure_detection_is_english_only_a_known_limit(self, tmp_path, unpublished):
        """Documents a known limit rather than hiding it: the disclosure regex is
        English, so an English disclosure sentence on a de-suffixed page is caught,
        a German one is not (owned by TC-PKG-07-06/07, not by this script)."""
        english = _write_page(
            tmp_path, self._FLAT_DE.replace("some-post", "en-sentence"),
            "---\ntitle: T\n---\n\nThis package is not yet published on any registry.\n")
        german = _write_page(
            tmp_path, self._FLAT_DE.replace("some-post", "de-sentence"),
            "---\ntitle: T\n---\n\nDas Paket ist noch nicht veroeffentlicht.\n")
        assert [f["category"] for f in sut.run_check([str(english)]).findings] == ["IR_UNPUBLISHED_DISCLOSURE"]
        assert sut.run_check([str(german)]).findings == []


class TestFilesFrom:
    def test_files_from_reads_paths_and_tolerates_blank_lines_and_crlf(self, tmp_path, unpublished, capsys):
        claim = _write_page(tmp_path, _DOCS_PAGE, _CLAIM_BODY)
        clean = _write_page(tmp_path, "kb.aspose.org/en/barcode/python/how-to-x.md", _CLEAN_BODY)
        listing = tmp_path / "staged.txt"
        listing.write_bytes(f"{claim}\r\n\r\n{clean}\r\n".encode("utf-8"))
        assert sut.main(["--files-from", str(listing)]) == sut.EXIT_FINDINGS
        assert "evaluated 2 of 2" in capsys.readouterr().err

    def test_files_from_combines_with_positional_paths_and_dedupes(self, tmp_path, unpublished, capsys):
        clean = _write_page(tmp_path, _DOCS_PAGE, _CLEAN_BODY)
        other = _write_page(tmp_path, "kb.aspose.org/en/barcode/python/how-to-x.md", _CLEAN_BODY)
        listing = tmp_path / "staged.txt"
        listing.write_text(f"{clean}\n{other}\n", encoding="utf-8")
        assert sut.main([str(clean), "--files-from", str(listing)]) == sut.EXIT_OK
        # the same path given both ways is one path: 2 evaluated of 2, not of 3
        assert "evaluated 2 of 2" in capsys.readouterr().out

    def test_unreadable_files_from_is_an_error(self, tmp_path, capsys):
        assert sut.main(["--files-from", str(tmp_path / "missing.txt")]) == sut.EXIT_ERROR
        assert "cannot read --files-from" in capsys.readouterr().err

    def test_empty_files_from_reports_zero_of_zero(self, tmp_path, capsys):
        listing = tmp_path / "empty.txt"
        listing.write_text("\n", encoding="utf-8")
        assert sut.main(["--files-from", str(listing)]) == sut.EXIT_OK
        assert "evaluated 0 of 0" in capsys.readouterr().out

    def test_many_paths_via_files_from_are_all_accounted_for(self, tmp_path, unpublished):
        """The reason the option exists: a list far longer than a Windows command
        line can carry still works and every path is accounted for."""
        pages = [_write_page(tmp_path, f"kb.aspose.org/en/barcode/python/how-to-{i:04d}.md", _CLEAN_BODY)
                 for i in range(60)]
        listing = tmp_path / "many.txt"
        listing.write_text("\n".join(str(p) for p in pages), encoding="utf-8")
        report = sut.run_check(sut._read_files_from(str(listing)))
        assert report.total == 60 and len(report.evaluated) == 60


class TestBlockedFilesOut:
    def test_lists_only_paths_with_findings_on_exit_one(self, tmp_path, unpublished):
        claim = _write_page(tmp_path, _DOCS_PAGE, _CLAIM_BODY)
        clean = _write_page(tmp_path, "kb.aspose.org/en/barcode/python/how-to-x.md", _CLEAN_BODY)
        out = tmp_path / "blocked.txt"
        assert sut.main([str(claim), str(clean), "--blocked-files-out", str(out)]) == sut.EXIT_FINDINGS
        assert out.read_text(encoding="utf-8").splitlines() == [str(claim)]

    def test_paths_are_reported_exactly_as_given(self, tmp_path, unpublished):
        """A hook passes git's forward-slash paths; the list that feeds per-file
        override-token validation must carry that same string, not a normalised one."""
        claim = _write_page(tmp_path, _DOCS_PAGE, _CLAIM_BODY)
        given = str(claim).replace("\\", "/")
        out = tmp_path / "blocked.txt"
        assert sut.main([given, "--blocked-files-out", str(out)]) == sut.EXIT_FINDINGS
        assert out.read_text(encoding="utf-8").splitlines() == [given]

    def test_is_empty_on_exit_zero(self, tmp_path, unpublished):
        clean = _write_page(tmp_path, _DOCS_PAGE, _CLEAN_BODY)
        out = tmp_path / "blocked.txt"
        out.write_text("stale\n", encoding="utf-8")
        assert sut.main([str(clean), "--blocked-files-out", str(out)]) == sut.EXIT_OK
        assert out.read_text(encoding="utf-8") == ""

    def test_is_empty_on_exit_two_even_with_findings_so_errors_are_never_overridable(self, tmp_path, unpublished):
        """A caller applying the 'non-zero exit + empty list = unverifiable = blocked'
        rule then cannot let an override token cover an ERROR."""
        claim = _write_page(tmp_path, _DOCS_PAGE, _CLAIM_BODY)
        out = tmp_path / "blocked.txt"
        assert sut.main([str(claim), str(tmp_path / "nope.md"),
                         "--blocked-files-out", str(out)]) == sut.EXIT_ERROR
        assert out.read_text(encoding="utf-8") == ""


class TestRealCliProcess:
    """The __main__ entry point as a real process (registry-independent fixtures
    only: the CLI cannot take an injected registry)."""

    _SCRIPT = str(Path(sut.__file__).resolve())

    def _run(self, *args):
        env = {**os.environ, "PYTHONPATH": str(_REPO_ROOT / "scripts" / "pipeline")}
        return subprocess.run([sys.executable, self._SCRIPT, *args], capture_output=True,
                              encoding="utf-8", errors="replace", env=env, timeout=180)

    def test_nonexistent_path_exits_two(self, tmp_path):
        proc = self._run(str(tmp_path / "nope.md"))
        assert proc.returncode == 2, proc.stdout + proc.stderr
        assert "does not exist" in proc.stderr

    def test_unreadable_files_from_exits_two(self, tmp_path):
        proc = self._run("--files-from", str(tmp_path / "missing.txt"))
        assert proc.returncode == 2, proc.stdout + proc.stderr

    def test_non_markdown_only_exits_zero_and_lists_the_skip(self, tmp_path):
        txt = tmp_path / "a.txt"
        txt.write_text("x", encoding="utf-8")
        proc = self._run(str(txt))
        assert proc.returncode == 0, proc.stdout + proc.stderr
        assert "evaluated 0 of 1" in proc.stdout and "SKIPPED" in proc.stdout
