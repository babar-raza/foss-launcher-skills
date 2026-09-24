"""Tests for commands/governance/locale_tag_mistranslation_fixer.py (TC-02/
TC-03, MT073-2026-09-24-LOCALE-CODE-BLOCK-DEFECT-REMEDIATION).
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent.parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))
_LIB_DIR = str(_HERE / "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
_GOV_DIR = str(_HERE / "commands" / "governance")
if _GOV_DIR not in sys.path:
    sys.path.insert(0, _GOV_DIR)

import locale_tag_mistranslation_fixer as fixer  # noqa: E402


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="")


def _init_repo(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "-c", "user.email=t@example.com", "-c", "user.name=T", "commit", "-q", "-m", "init"],
        cwd=tmp_path, check=True,
    )


def test_is_locale_page():
    assert fixer._is_locale_page("content/docs.aspose.org/ar/pdf/net/x.md")
    assert not fixer._is_locale_page("content/docs.aspose.org/en/pdf/net/x.md")
    assert fixer._is_locale_page("content/blog.aspose.org/pdf/net/post/index.ar.md")
    assert not fixer._is_locale_page("content/blog.aspose.org/pdf/net/post/index.md")


def test_en_counterpart():
    assert fixer._en_counterpart("content/docs.aspose.org/ar/pdf/net/x.md") == "content/docs.aspose.org/en/pdf/net/x.md"
    assert fixer._en_counterpart("content/blog.aspose.org/pdf/net/post/index.ar.md") == "content/blog.aspose.org/pdf/net/post/index.md"


def test_find_candidates_detects_real_tag_mistranslation(tmp_path):
    """The exact live shape TC-19 confirmed: English tags a bare signature
    `text` (non-code); the locale copy tags the same block `typescript`,
    producing a genuine SYNTAX-ERROR."""
    (tmp_path / "content/docs.aspose.org/en/3d/typescript").mkdir(parents=True)
    (tmp_path / "content/docs.aspose.org/ar/3d/typescript").mkdir(parents=True)
    _write(
        tmp_path / "content/docs.aspose.org/en/3d/typescript/x.md",
        "---\ntitle: x\n---\n\n```text\nsetIndices(data: number[]): void\n```\n",
    )
    _write(
        tmp_path / "content/docs.aspose.org/ar/3d/typescript/x.md",
        "---\ntitle: x\n---\n\n```typescript\nsetIndices(data: number[]): void\n```\n",
    )
    _init_repo(tmp_path)

    candidates = fixer.find_candidates(repo_root=tmp_path)
    assert len(candidates) == 1
    c = candidates[0]
    assert c.old_tag == "typescript"
    assert c.new_tag == "text"
    assert c.match_method == "position"


def test_find_candidates_skips_when_no_syntax_error(tmp_path):
    """A tag difference alone, with valid content under the locale's own
    tag, must NOT be flagged -- only genuine SYNTAX-ERROR is this defect."""
    (tmp_path / "content/docs.aspose.org/en/3d/typescript").mkdir(parents=True)
    (tmp_path / "content/docs.aspose.org/ar/3d/typescript").mkdir(parents=True)
    _write(
        tmp_path / "content/docs.aspose.org/en/3d/typescript/x.md",
        "---\ntitle: x\n---\n\n```text\nsome plain text\n```\n",
    )
    _write(
        tmp_path / "content/docs.aspose.org/ar/3d/typescript/x.md",
        "---\ntitle: x\n---\n\n```typescript\nconst x = 1;\n```\n",
    )
    _init_repo(tmp_path)

    candidates = fixer.find_candidates(repo_root=tmp_path)
    assert candidates == []


def test_find_candidates_skips_when_english_is_not_text(tmp_path):
    """Both sides already agree on a real language -- not this defect."""
    (tmp_path / "content/docs.aspose.org/en/3d/typescript").mkdir(parents=True)
    (tmp_path / "content/docs.aspose.org/ar/3d/typescript").mkdir(parents=True)
    body = "---\ntitle: x\n---\n\n```typescript\nsetIndices(data: number[]): void\n```\n"
    _write(tmp_path / "content/docs.aspose.org/en/3d/typescript/x.md", body)
    _write(tmp_path / "content/docs.aspose.org/ar/3d/typescript/x.md", body)
    _init_repo(tmp_path)

    candidates = fixer.find_candidates(repo_root=tmp_path)
    assert candidates == []


def test_apply_fix_rewrites_only_the_fence_line(tmp_path):
    (tmp_path / "content/docs.aspose.org/en/3d/typescript").mkdir(parents=True)
    (tmp_path / "content/docs.aspose.org/ar/3d/typescript").mkdir(parents=True)
    en_path = tmp_path / "content/docs.aspose.org/en/3d/typescript/x.md"
    ar_path = tmp_path / "content/docs.aspose.org/ar/3d/typescript/x.md"
    _write(en_path, "---\ntitle: x\n---\n\n```text\nsetIndices(data: number[]): void\n```\n")
    _write(ar_path, "---\ntitle: x\n---\n\nمرحبا\n\n```typescript\nsetIndices(data: number[]): void\n```\n")
    _init_repo(tmp_path)

    candidates = fixer.find_candidates(repo_root=tmp_path)
    assert len(candidates) == 1
    before = ar_path.read_text(encoding="utf-8")
    applied = fixer.apply_fix(candidates[0], repo_root=tmp_path)
    assert applied is True
    after = ar_path.read_text(encoding="utf-8")

    before_lines = before.split("\n")
    after_lines = after.split("\n")
    diff_lines = [i for i in range(len(before_lines)) if before_lines[i] != after_lines[i]]
    assert len(diff_lines) == 1
    assert after_lines[diff_lines[0]] == "```text"
    assert "مرحبا" in after  # untouched prose survives byte-for-byte


def test_apply_fix_returns_false_when_line_no_longer_matches(tmp_path):
    (tmp_path / "content/docs.aspose.org/en/3d/typescript").mkdir(parents=True)
    (tmp_path / "content/docs.aspose.org/ar/3d/typescript").mkdir(parents=True)
    ar_path = tmp_path / "content/docs.aspose.org/ar/3d/typescript/x.md"
    _write(tmp_path / "content/docs.aspose.org/en/3d/typescript/x.md", "---\ntitle: x\n---\n\n```text\nclear(): void\n```\n")
    _write(ar_path, "---\ntitle: x\n---\n\n```typescript\nclear(): void\n```\n")
    _init_repo(tmp_path)
    candidates = fixer.find_candidates(repo_root=tmp_path)
    assert len(candidates) == 1

    # Simulate the file changing on disk between scan and apply.
    ar_path.write_text("---\ntitle: x\n---\n\ncompletely different now\n", encoding="utf-8")
    assert fixer.apply_fix(candidates[0], repo_root=tmp_path) is False


def test_main_dry_run_does_not_write(tmp_path):
    """main()'s default mode is dry-run: candidates are found and reported
    but nothing is written to disk."""
    (tmp_path / "content/docs.aspose.org/en/3d/typescript").mkdir(parents=True)
    (tmp_path / "content/docs.aspose.org/ar/3d/typescript").mkdir(parents=True)
    ar_path = tmp_path / "content/docs.aspose.org/ar/3d/typescript/x.md"
    _write(tmp_path / "content/docs.aspose.org/en/3d/typescript/x.md", "---\ntitle: x\n---\n\n```text\nclear(): void\n```\n")
    _write(ar_path, "---\ntitle: x\n---\n\n```typescript\nclear(): void\n```\n")
    _init_repo(tmp_path)

    report_path = tmp_path / "report.json"
    rc = fixer.main(["--repo-root", str(tmp_path), "--report", str(report_path)])
    assert rc == 0
    assert "```typescript" in ar_path.read_text(encoding="utf-8")  # unchanged -- dry-run
    assert report_path.exists()


def test_main_apply_writes_the_fix(tmp_path):
    (tmp_path / "content/docs.aspose.org/en/3d/typescript").mkdir(parents=True)
    (tmp_path / "content/docs.aspose.org/ar/3d/typescript").mkdir(parents=True)
    ar_path = tmp_path / "content/docs.aspose.org/ar/3d/typescript/x.md"
    _write(tmp_path / "content/docs.aspose.org/en/3d/typescript/x.md", "---\ntitle: x\n---\n\n```text\nclear(): void\n```\n")
    _write(ar_path, "---\ntitle: x\n---\n\n```typescript\nclear(): void\n```\n")
    _init_repo(tmp_path)

    rc = fixer.main(["--repo-root", str(tmp_path), "--apply"])
    assert rc == 0
    assert "```text" in ar_path.read_text(encoding="utf-8")
    assert "```typescript" not in ar_path.read_text(encoding="utf-8")


def test_apply_fix_preserves_lf_line_endings_no_crlf_widening(tmp_path):
    """Regression test for a real bug found while building this: writing
    without newline="" would let Python's platform-default translation
    convert the WHOLE file from LF to CRLF on Windows, not just the one
    fixed line."""
    (tmp_path / "content/docs.aspose.org/en/3d/typescript").mkdir(parents=True)
    (tmp_path / "content/docs.aspose.org/ar/3d/typescript").mkdir(parents=True)
    ar_path = tmp_path / "content/docs.aspose.org/ar/3d/typescript/x.md"
    _write(tmp_path / "content/docs.aspose.org/en/3d/typescript/x.md", "---\ntitle: x\n---\n\n```text\nclear(): void\n```\n")
    _write(ar_path, "---\ntitle: x\n---\n\nprose line one\nprose line two\n\n```typescript\nclear(): void\n```\n")
    _init_repo(tmp_path)

    candidates = fixer.find_candidates(repo_root=tmp_path)
    assert len(candidates) == 1
    fixer.apply_fix(candidates[0], repo_root=tmp_path)

    raw = ar_path.read_bytes()
    assert b"\r\n" not in raw
    assert raw.count(b"\r") == 0
