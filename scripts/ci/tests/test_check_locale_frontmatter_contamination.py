"""Tests for check_locale_frontmatter_contamination.py (TC-ALIAS-005 / TC-URL-005
recurrence guard, ASPOSE-BLOG-DEPLOY-ALIAS-RECURRENCE-001, 2026-09-17).

Mirrors the coverage rigor already proven in hugo-translator's
tests/unit/translation_engine/test_write_gate_45_ignore_mode_field_leak.py, plus one
case specific to this script's own behavior: the English/default-locale file is
exempt (verify_no_non_english_aliases infers language from the path/filename and
skips "en"), unlike hugo-translator's Gate 45 which is simply never invoked for the
English file at all.
"""
from __future__ import annotations

import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent.parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from checks import check_locale_frontmatter_contamination as check_module  # noqa: E402


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_leaked_aliases_field_is_flagged(tmp_path, capsys):
    f = _write(
        tmp_path / "content" / "blog.aspose.org" / "slides" / "cpp" / "post" / "index.ja.md",
        "---\ntitle: Test\naliases: [/slides/cpp/slides-key-features-cpp/]\ndraft: false\n---\nBody.\n",
    )
    exit_code = check_module.main([str(f)])
    out = capsys.readouterr().out
    assert exit_code == 1
    assert "aliases" in out
    assert "BLOCKED" in out


def test_leaked_url_field_is_flagged(tmp_path, capsys):
    f = _write(
        tmp_path / "content" / "blog.aspose.org" / "pdf" / "go" / "post" / "index.de.md",
        "---\ntitle: Test\nurl: /pdf/go/introducing-pdf-foss-go/\ndraft: false\n---\nBody.\n",
    )
    exit_code = check_module.main([str(f)])
    out = capsys.readouterr().out
    assert exit_code == 1
    assert "url" in out


def test_both_leaked_fields_across_files_are_both_counted(tmp_path, capsys):
    f1 = _write(
        tmp_path / "a" / "index.fr.md",
        "---\ntitle: A\naliases: [/old-a/]\n---\nBody.\n",
    )
    f2 = _write(
        tmp_path / "b" / "index.fr.md",
        "---\ntitle: B\nurl: /old-b/\n---\nBody.\n",
    )
    exit_code = check_module.main([str(f1), str(f2)])
    out = capsys.readouterr().out
    assert exit_code == 1
    assert "2 locale frontmatter contamination finding" in out


def test_correctly_stripped_output_is_silent(tmp_path, capsys):
    f = _write(
        tmp_path / "content" / "blog.aspose.org" / "slides" / "cpp" / "post" / "index.ja.md",
        "---\ntitle: Test\ndraft: false\n---\nBody.\n",
    )
    exit_code = check_module.main([str(f)])
    out = capsys.readouterr().out
    assert exit_code == 0
    assert "0 FAIL" in out


def test_english_default_locale_with_legitimate_aliases_is_not_flagged(tmp_path, capsys):
    """The bare index.md (no locale suffix) is the default/English copy -- its
    aliases: is a legitimate redirect-preservation mechanism and must never be
    flagged, unlike every translated sibling."""
    f = _write(
        tmp_path / "content" / "blog.aspose.org" / "slides" / "cpp" / "post" / "index.md",
        "---\ntitle: Test\naliases: [/slides/cpp/slides-key-features-cpp/]\ndraft: false\n---\nBody.\n",
    )
    exit_code = check_module.main([str(f)])
    out = capsys.readouterr().out
    assert exit_code == 0
    assert "0 FAIL" in out


def test_files_from_mode_reads_a_real_list_file(tmp_path, capsys):
    bad = _write(tmp_path / "post" / "index.ja.md", "---\naliases: [/old/]\n---\nBody.\n")
    listfile = tmp_path / "files.txt"
    listfile.write_text(f"{bad}\n", encoding="utf-8")

    exit_code = check_module.main(["--files-from", str(listfile)])

    assert exit_code == 1


def test_empty_file_list_is_a_no_op(capsys):
    exit_code = check_module.main([])
    out = capsys.readouterr().out
    assert exit_code == 0
    assert "no .md files to check" in out


def test_non_markdown_paths_are_ignored(tmp_path, capsys):
    f = _write(tmp_path / "notes.txt", "aliases: [/old/]\n")
    exit_code = check_module.main([str(f)])
    out = capsys.readouterr().out
    assert exit_code == 0
    assert "no .md files to check" in out


def test_corpus_root_mode_walks_recursively(tmp_path, capsys):
    """SCAN-01 (2026-09-17): --corpus-root must recursively discover .md
    files across nested locale-folder subdomains (docs/kb/products/
    reference layout: content/<site>/<lang>/<family>/<platform>/...), not
    just a flat directory."""
    _write(
        tmp_path / "content" / "docs.aspose.org" / "en" / "pdf" / "net" / "page.md",
        "---\ntitle: T\n---\nBody.\n",
    )
    _write(
        tmp_path / "content" / "docs.aspose.org" / "de" / "pdf" / "net" / "page.md",
        "---\ntitle: T\naliases: [/old/]\n---\nBody.\n",
    )
    exit_code = check_module.main(["--corpus-root", str(tmp_path)])
    out = capsys.readouterr().out
    assert exit_code == 1
    assert "aliases" in out


def test_append_log_writes_one_json_line_per_finding(tmp_path, capsys):
    f = _write(tmp_path / "post" / "index.ja.md", "---\naliases: [/old/]\nurl: /old2/\n---\nBody.\n")
    log = tmp_path / "log.jsonl"

    exit_code = check_module.main(["--append-log", str(log), str(f)])

    assert exit_code == 1
    lines = log.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    import json
    for line in lines:
        row = json.loads(line)
        assert set(row) == {"timestamp", "git_sha", "file", "message"}
        assert row["file"] == str(f)


def test_append_log_appends_not_overwrites_across_runs(tmp_path):
    f = _write(tmp_path / "post" / "index.ja.md", "---\naliases: [/old/]\n---\nBody.\n")
    log = tmp_path / "log.jsonl"

    check_module.main(["--append-log", str(log), str(f)])
    check_module.main(["--append-log", str(log), str(f)])

    assert len(log.read_text(encoding="utf-8").splitlines()) == 2


def test_append_log_writes_nothing_on_a_clean_run(tmp_path, capsys):
    f = _write(tmp_path / "post" / "index.ja.md", "---\ntitle: T\n---\nBody.\n")
    log = tmp_path / "log.jsonl"

    exit_code = check_module.main(["--append-log", str(log), str(f)])

    assert exit_code == 0
    assert not log.exists()


def test_missing_file_does_not_crash(tmp_path, capsys):
    missing = tmp_path / "does-not-exist" / "index.ja.md"
    exit_code = check_module.main([str(missing)])
    out = capsys.readouterr().out
    assert exit_code == 0
    assert "0 FAIL" in out
