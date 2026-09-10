"""Tests for locale_patch.py (PKGINSTALL-LOCALE-PATCH-MODULE)."""
from pathlib import Path

import pytest

import commands.content.locale_patch as sut
import lib.install_change_budget as icb
from lib.reconciliation_store import ReconciliationStore


@pytest.fixture(autouse=True)
def isolate_repo(tmp_path):
    sut.configure(repo_root=tmp_path)
    icb.configure(repo_root=tmp_path)
    yield
    sut.configure(repo_root=None)
    icb.configure()


def _write(tmp_path: Path, rel_path: str, content: str) -> Path:
    p = tmp_path / rel_path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


def _row(path: str, family: str, platform: str, representation: str, collision: "str | None" = None) -> dict:
    return {
        "path": path, "family": family, "platform": platform,
        "site": "docs.aspose.org", "locale": "en", "representation": representation,
        "collision_classification": collision, "sweep_run_id": "sweep-1",
        "recorded_at": "2026-09-10T00:00:00Z",
    }


# ---------------------------------------------------------------------------
# discover_locale_files
# ---------------------------------------------------------------------------

class TestDiscoverLocaleFiles:
    def test_docs_site_directory_convention(self, tmp_path):
        _write(tmp_path, "content/docs.aspose.org/en/slides/net/getting-started/installation.md", "en content")
        _write(tmp_path, "content/docs.aspose.org/fr/slides/net/getting-started/installation.md", "fr content")
        _write(tmp_path, "content/docs.aspose.org/de/slides/net/getting-started/installation.md", "de content")
        source = tmp_path / "content/docs.aspose.org/en/slides/net/getting-started/installation.md"
        found = sut.discover_locale_files(source, "slides")
        names = {str(f.relative_to(tmp_path)).replace("\\", "/") for f in found}
        assert names == {
            "content/docs.aspose.org/fr/slides/net/getting-started/installation.md",
            "content/docs.aspose.org/de/slides/net/getting-started/installation.md",
        }

    def test_blog_site_filename_suffix_convention(self, tmp_path):
        _write(tmp_path, "content/blog.aspose.org/slides/net/some-post/index.md", "en content")
        _write(tmp_path, "content/blog.aspose.org/slides/net/some-post/index.fr.md", "fr content")
        _write(tmp_path, "content/blog.aspose.org/slides/net/some-post/index.de.md", "de content")
        source = tmp_path / "content/blog.aspose.org/slides/net/some-post/index.md"
        found = sut.discover_locale_files(source, "slides")
        names = {f.name for f in found}
        assert names == {"index.fr.md", "index.de.md"}

    def test_no_locale_copies_returns_empty(self, tmp_path):
        source = _write(tmp_path, "content/docs.aspose.org/en/slides/net/getting-started/installation.md", "x")
        assert sut.discover_locale_files(source, "slides") == []


# ---------------------------------------------------------------------------
# apply_patch_to_file -- S-75's exact byte-identical match-or-skip algorithm
# ---------------------------------------------------------------------------

class TestApplyPatchToFile:
    def test_applies_when_old_text_present(self, tmp_path):
        p = _write(tmp_path, "f.md", "Run `dotnet add package Aspose.Slides.Foss`.\n")
        patch = sut.Patch(old_text="dotnet add package Aspose.Slides.Foss", new_text="{{< package-install-inline \"slides\" \"net\" >}}")
        result = sut.apply_patch_to_file(p, patch, dry_run=False)
        assert result.status == sut.PatchStatus.APPLIED
        assert "package-install-inline" in p.read_text(encoding="utf-8")

    def test_dry_run_does_not_write(self, tmp_path):
        p = _write(tmp_path, "f.md", "Run `dotnet add package Aspose.Slides.Foss`.\n")
        patch = sut.Patch(old_text="dotnet add package Aspose.Slides.Foss", new_text="REPLACED")
        result = sut.apply_patch_to_file(p, patch, dry_run=True)
        assert result.status == sut.PatchStatus.APPLIED
        assert "REPLACED" not in p.read_text(encoding="utf-8")

    def test_not_found_when_old_text_absent(self, tmp_path):
        """Regression pin for the real, live Danish precedent
        (content/docs.aspose.org/da/slides/net/_index.md): the translation
        translated the CLI command ITSELF ('dotnet add-pakke' instead of
        'dotnet add package'), so old_text never matches verbatim -- must
        be reported not_found and left completely untouched, never
        corrupted further."""
        original = "Run `dotnet add-pakke Aspose.Slides.Foss`.\n"
        p = _write(tmp_path, "f.md", original)
        patch = sut.Patch(old_text="dotnet add package Aspose.Slides.Foss", new_text="REPLACED")
        result = sut.apply_patch_to_file(p, patch, dry_run=False)
        assert result.status == sut.PatchStatus.NOT_FOUND
        assert p.read_text(encoding="utf-8") == original  # byte-identical, untouched

    def test_context_mismatch_is_skipped_not_applied(self, tmp_path):
        content = "Some unrelated text far away.\n" * 10 + "dotnet add package Aspose.Slides.Foss\n"
        p = _write(tmp_path, "f.md", content)
        patch = sut.Patch(
            old_text="dotnet add package Aspose.Slides.Foss", new_text="REPLACED",
            context="a context string that never appears anywhere",
        )
        result = sut.apply_patch_to_file(p, patch, dry_run=False)
        assert result.status == sut.PatchStatus.SKIPPED
        assert "REPLACED" not in p.read_text(encoding="utf-8")

    def test_context_match_within_5_lines_applies(self, tmp_path):
        content = "install context marker\ndotnet add package Aspose.Slides.Foss\n"
        p = _write(tmp_path, "f.md", content)
        patch = sut.Patch(
            old_text="dotnet add package Aspose.Slides.Foss", new_text="REPLACED",
            context="install context marker",
        )
        result = sut.apply_patch_to_file(p, patch, dry_run=False)
        assert result.status == sut.PatchStatus.APPLIED

    def test_read_error_is_not_found_not_a_crash(self, tmp_path):
        missing = tmp_path / "does-not-exist.md"
        patch = sut.Patch(old_text="x", new_text="y")
        result = sut.apply_patch_to_file(missing, patch)
        assert result.status == sut.PatchStatus.NOT_FOUND


# ---------------------------------------------------------------------------
# is_english_source_ready
# ---------------------------------------------------------------------------

class TestIsEnglishSourceReady:
    def test_no_record_refuses_fail_closed(self, tmp_path):
        store = ReconciliationStore(repo_root=tmp_path)
        ready, reason = sut.is_english_source_ready("slides", "net", "content/docs.aspose.org/en/slides/net/installation.md", store=store)
        assert ready is False
        assert "no reconciliation record" in reason

    def test_literal_representation_refuses(self, tmp_path):
        store = ReconciliationStore(repo_root=tmp_path)
        store.append_batch([_row("content/a.md", "slides", "net", "literal")])
        ready, reason = sut.is_english_source_ready("slides", "net", "content/a.md", store=store)
        assert ready is False
        assert "literal" in reason

    def test_collision_risk_structural_refuses(self, tmp_path):
        store = ReconciliationStore(repo_root=tmp_path)
        store.append_batch([_row("content/a.md", "cells", "net", "shortcode_block", "COLLISION_RISK_STRUCTURAL")])
        ready, reason = sut.is_english_source_ready("cells", "net", "content/a.md", store=store)
        assert ready is False
        assert "COLLISION_RISK_STRUCTURAL" in reason

    def test_shortcode_and_safe_classification_is_ready(self, tmp_path):
        store = ReconciliationStore(repo_root=tmp_path)
        store.append_batch([_row("content/a.md", "slides", "net", "shortcode_block", "SAFE_FOR_MECHANICAL_MIGRATION")])
        ready, reason = sut.is_english_source_ready("slides", "net", "content/a.md", store=store)
        assert ready is True


# ---------------------------------------------------------------------------
# run_locale_patch -- integration
# ---------------------------------------------------------------------------

class TestRunLocalePatch:
    def _make_ready_store(self, tmp_path, source_rel: str, family: str, platform: str) -> ReconciliationStore:
        store = ReconciliationStore(repo_root=tmp_path)
        store.append_batch([_row(source_rel, family, platform, "shortcode_inline", "SAFE_FOR_MECHANICAL_MIGRATION")])
        return store

    def test_refuses_when_english_source_not_ready(self, tmp_path):
        store = ReconciliationStore(repo_root=tmp_path)  # empty -- no record
        summary = sut.run_locale_patch(
            "slides", "net", "docs.aspose.org",
            "content/docs.aspose.org/en/slides/net/getting-started/installation.md",
            [sut.Patch(old_text="x", new_text="y")],
            store=store,
        )
        assert summary["readiness_blocked"] is True

    def test_force_bypasses_readiness_gate(self, tmp_path):
        source_rel = "content/docs.aspose.org/en/slides/net/getting-started/installation.md"
        _write(tmp_path, source_rel, "dotnet add package Aspose.Slides.Foss\n")
        _write(tmp_path, "content/docs.aspose.org/fr/slides/net/getting-started/installation.md",
               "dotnet add package Aspose.Slides.Foss\n")
        store = ReconciliationStore(repo_root=tmp_path)  # empty
        summary = sut.run_locale_patch(
            "slides", "net", "docs.aspose.org", tmp_path / source_rel,
            [sut.Patch(old_text="dotnet add package Aspose.Slides.Foss", new_text="REPLACED")],
            store=store, force=True, dry_run=False,
        )
        assert summary["readiness_blocked"] is False
        assert summary["files_modified"] == 1

    def test_real_propagation_end_to_end(self, tmp_path):
        source_rel = "content/docs.aspose.org/en/slides/net/getting-started/installation.md"
        source_abs = _write(tmp_path, source_rel, "dotnet add package Aspose.Slides.Foss\n")
        _write(tmp_path, "content/docs.aspose.org/fr/slides/net/getting-started/installation.md",
               "dotnet add package Aspose.Slides.Foss\n")
        _write(tmp_path, "content/docs.aspose.org/da/slides/net/getting-started/installation.md",
               "dotnet add-pakke Aspose.Slides.Foss\n")  # diverged translation, must stay untouched

        store = self._make_ready_store(tmp_path, source_rel, "slides", "net")
        summary = sut.run_locale_patch(
            "slides", "net", "docs.aspose.org", source_abs,
            [sut.Patch(old_text="dotnet add package Aspose.Slides.Foss", new_text="{{< package-install-inline \"slides\" \"net\" >}}")],
            store=store, dry_run=False,
        )
        assert summary["readiness_blocked"] is False
        assert summary["budget_blocked"] is False
        assert summary["files_modified"] == 1  # only fr, not da
        assert summary["patches_not_found"] == 1  # da

        fr_content = (tmp_path / "content/docs.aspose.org/fr/slides/net/getting-started/installation.md").read_text(encoding="utf-8")
        assert "package-install-inline" in fr_content
        da_content = (tmp_path / "content/docs.aspose.org/da/slides/net/getting-started/installation.md").read_text(encoding="utf-8")
        assert da_content == "dotnet add-pakke Aspose.Slides.Foss\n"  # byte-identical, untouched

        history = icb.load_history()
        assert history["slides/locale_propagation"] == [1]

    def test_dry_run_writes_nothing(self, tmp_path):
        source_rel = "content/docs.aspose.org/en/slides/net/getting-started/installation.md"
        source_abs = _write(tmp_path, source_rel, "dotnet add package Aspose.Slides.Foss\n")
        fr_path = _write(tmp_path, "content/docs.aspose.org/fr/slides/net/getting-started/installation.md",
                          "dotnet add package Aspose.Slides.Foss\n")
        store = self._make_ready_store(tmp_path, source_rel, "slides", "net")
        summary = sut.run_locale_patch(
            "slides", "net", "docs.aspose.org", source_abs,
            [sut.Patch(old_text="dotnet add package Aspose.Slides.Foss", new_text="REPLACED")],
            store=store, dry_run=True,
        )
        assert summary["files_modified"] == 1  # would-modify count, from the probe
        assert "REPLACED" not in fr_path.read_text(encoding="utf-8")
        assert icb.load_history() == {}  # record_run never called on a dry run

    def test_budget_blocks_an_oversized_propagation(self, tmp_path):
        source_rel = "content/docs.aspose.org/en/slides/net/getting-started/installation.md"
        source_abs = _write(tmp_path, source_rel, "dotnet add package Aspose.Slides.Foss\n")
        _write(tmp_path, "content/docs.aspose.org/fr/slides/net/getting-started/installation.md",
               "dotnet add package Aspose.Slides.Foss\n")
        zero_budget = tmp_path / "zero.yaml"
        zero_budget.write_text(
            "max_files_per_run: 0\nmax_files_per_locale_per_run: 0\nanomaly_multiplier: 3.0\nwarmup_runs: 3\n",
            encoding="utf-8",
        )
        icb.configure(repo_root=tmp_path, config_path=zero_budget)
        store = self._make_ready_store(tmp_path, source_rel, "slides", "net")
        summary = sut.run_locale_patch(
            "slides", "net", "docs.aspose.org", source_abs,
            [sut.Patch(old_text="dotnet add package Aspose.Slides.Foss", new_text="REPLACED")],
            store=store, dry_run=False,
        )
        assert summary["budget_blocked"] is True
        fr_content = (tmp_path / "content/docs.aspose.org/fr/slides/net/getting-started/installation.md").read_text(encoding="utf-8")
        assert "REPLACED" not in fr_content

    def test_report_is_written(self, tmp_path):
        source_rel = "content/docs.aspose.org/en/slides/net/getting-started/installation.md"
        source_abs = _write(tmp_path, source_rel, "dotnet add package Aspose.Slides.Foss\n")
        _write(tmp_path, "content/docs.aspose.org/fr/slides/net/getting-started/installation.md",
               "dotnet add package Aspose.Slides.Foss\n")
        store = self._make_ready_store(tmp_path, source_rel, "slides", "net")
        summary = sut.run_locale_patch(
            "slides", "net", "docs.aspose.org", source_abs,
            [sut.Patch(old_text="dotnet add package Aspose.Slides.Foss", new_text="REPLACED")],
            store=store, dry_run=False,
        )
        report_path = Path(summary["report_path"])
        assert report_path.exists()
        assert "package-reconciliation" not in str(report_path)
        assert str(report_path).replace("\\", "/").count("reports/agents/locale-patch/") == 1
        text = report_path.read_text(encoding="utf-8")
        assert "Locale Patch Report" in text
        assert "Files modified: 1" in text
