"""Tests for seo_stability_check.py (RPR-F-05)."""
import subprocess
import sys
from pathlib import Path

import pytest

_CONTENT = Path(__file__).resolve().parents[1] / "commands" / "content"
if str(_CONTENT) not in sys.path:
    sys.path.insert(0, str(_CONTENT))

import seo_stability_check as seo  # noqa: E402


# ── pure comparison logic ─────────────────────────────────────────────────

def test_extract_seo_fields_from_text():
    text = (
        "---\n"
        "title: Convert PDF to Image\n"
        "slug: convert-pdf-to-image\n"
        "canonical: https://docs.aspose.org/pdf/net/convert/\n"
        "---\n"
        "# Convert PDF to Image\n\nBody text.\n"
    )
    fields = seo.extract_from_text(text)
    assert fields["title"] == "Convert PDF to Image"
    assert fields["slug"] == "convert-pdf-to-image"
    assert fields["canonical"] == "https://docs.aspose.org/pdf/net/convert/"
    assert fields["h1"] == "Convert PDF to Image"


def test_compare_seo_detects_each_field():
    before = {"title": "A", "slug": "a", "canonical": "c", "h1": "A"}
    assert seo.compare_seo(before, before) == []
    assert seo.compare_seo(before, {**before, "slug": "a-new"}) == ["slug"]
    assert seo.compare_seo(before, {**before, "canonical": "c2"}) == ["canonical"]
    assert set(seo.compare_seo(before, {"title": "B", "slug": "b", "canonical": "c", "h1": "B"})) == {
        "title", "slug", "h1"
    }


def test_compare_seo_none_vs_none_not_changed():
    before = {"title": "T", "slug": None, "canonical": None, "h1": "T"}
    assert seo.compare_seo(before, dict(before)) == []


# ── git-based detection ───────────────────────────────────────────────────

def _make_repo(tmp_path):
    repo = tmp_path / "repo"
    (repo / "content").mkdir(parents=True)

    def git(*args, check=True):
        return subprocess.run(["git", "-C", str(repo), *args], check=check,
                              capture_output=True, text=True)

    try:
        git("init", "-q")
        git("config", "user.email", "t@t")
        git("config", "user.name", "t")
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("git not available")
    return repo, git


_PAGE = (
    "---\ntitle: {title}\nslug: {slug}\ncanonical: {canon}\n---\n# {h1}\n\nBody.\n"
)


def test_undeclared_slug_change_is_violation(tmp_path):
    repo, git = _make_repo(tmp_path)
    page = "content/p.md"
    (repo / page).write_text(_PAGE.format(title="T", slug="old-slug", canon="c", h1="T"), encoding="utf-8")
    git("add", "-A")
    git("commit", "-q", "-m", "base")
    # Working-tree change: slug drifts.
    (repo / page).write_text(_PAGE.format(title="T", slug="new-slug", canon="c", h1="T"), encoding="utf-8")

    violations = seo.detect_seo_violations([page], base_ref="HEAD", repo_root=repo)
    assert len(violations) == 1
    assert violations[0]["changed_fields"] == ["slug"]
    assert violations[0]["before"]["slug"] == "old-slug"
    assert violations[0]["after"]["slug"] == "new-slug"


def test_unexpected_canonical_change_blocks(tmp_path):
    repo, git = _make_repo(tmp_path)
    page = "content/p.md"
    (repo / page).write_text(_PAGE.format(title="T", slug="s", canon="c-old", h1="T"), encoding="utf-8")
    git("add", "-A")
    git("commit", "-q", "-m", "base")
    (repo / page).write_text(_PAGE.format(title="T", slug="s", canon="c-new", h1="T"), encoding="utf-8")
    violations = seo.detect_seo_violations([page], base_ref="HEAD", repo_root=repo)
    assert any("canonical" in v["changed_fields"] for v in violations)


def test_declared_intentional_rename_passes(tmp_path):
    repo, git = _make_repo(tmp_path)
    page = "content/p.md"
    (repo / page).write_text(_PAGE.format(title="Old", slug="old", canon="c", h1="Old"), encoding="utf-8")
    git("add", "-A")
    git("commit", "-q", "-m", "base")
    (repo / page).write_text(_PAGE.format(title="New", slug="new", canon="c", h1="New"), encoding="utf-8")
    # Declared as an intentional rename -> allowed.
    violations = seo.detect_seo_violations(
        [page], base_ref="HEAD", intentional_renames={page}, repo_root=repo
    )
    assert violations == []


def test_body_only_change_is_not_seo_violation(tmp_path):
    repo, git = _make_repo(tmp_path)
    page = "content/p.md"
    (repo / page).write_text(_PAGE.format(title="T", slug="s", canon="c", h1="T"), encoding="utf-8")
    git("add", "-A")
    git("commit", "-q", "-m", "base")
    # Body prose changes; all SEO fields stable.
    (repo / page).write_text(
        "---\ntitle: T\nslug: s\ncanonical: c\n---\n# T\n\nCompletely rewritten body.\n",
        encoding="utf-8",
    )
    assert seo.detect_seo_violations([page], base_ref="HEAD", repo_root=repo) == []


def test_new_page_absent_at_base_is_skipped(tmp_path):
    repo, git = _make_repo(tmp_path)
    git("commit", "-q", "--allow-empty", "-m", "empty base")
    page = "content/brand-new.md"
    (repo / page).write_text(_PAGE.format(title="T", slug="s", canon="c", h1="T"), encoding="utf-8")
    # Page did not exist at HEAD -> no prior SEO state to protect -> no violation.
    assert seo.detect_seo_violations([page], base_ref="HEAD", repo_root=repo) == []


def test_main_exit_code(tmp_path):
    repo, git = _make_repo(tmp_path)
    page = "content/p.md"
    (repo / page).write_text(_PAGE.format(title="T", slug="old", canon="c", h1="T"), encoding="utf-8")
    git("add", "-A")
    git("commit", "-q", "-m", "base")
    (repo / page).write_text(_PAGE.format(title="T", slug="new", canon="c", h1="T"), encoding="utf-8")
    assert seo.main([page, "--repo-root", str(repo), "--base", "HEAD"]) == 1
    assert seo.main([page, "--repo-root", str(repo), "--base", "HEAD",
                     "--intentional-renames", page]) == 0
