"""Full-chain integration test for TC-PKG-02-READINESS-GATE-FIX
(mission MT066-2026-09-09-PACKAGE-INSTALL-RECONCILIATION).

Proves the real, previously-broken chain end to end:

    install_defect_sweep.run_combined_sweep()
        -> writes a REAL per-file reconciliation row for the English source
           content file (not just the pre-existing product-level aggregate)
    -> locale_patch.is_english_source_ready()
        -> reads that real row and correctly allows/refuses
    -> locale_patch.run_locale_patch()
        -> actually propagates the fix to locale copies, or correctly
           refuses, based on that real signal -- never a hand-supplied
           workaround row.

This is the exact gap 3 independent taskcards hit live: TC-PKG-02-05
(cells/go, worked around it by hand-writing a row), TC-PKG-02-07
(cells/typescript) and TC-PKG-02-18 (tex/python) both confirmed, via
read_history() on the real inventory.jsonl, that 0 of the sweep's own rows
ever carried a content/-prefixed path -- so is_english_source_ready() could
never pass through the normal, reviewed sweep pipeline for any product. See
reports/plan_state/MT066-2026-09-09-PACKAGE-INSTALL-RECONCILIATION/taskcards.jsonl
for their full evidence_refs.
"""
import sys
from pathlib import Path

import pytest

_PIPELINE_ROOT = Path(__file__).resolve().parent.parent
if str(_PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_ROOT))

import commands.ops.install_defect_sweep as sweep  # noqa: E402
import commands.content.locale_patch as locale_patch  # noqa: E402
import lib.install_change_budget as icb  # noqa: E402
from lib.reconciliation_store import ReconciliationStore  # noqa: E402


@pytest.fixture(autouse=True)
def isolate(tmp_path):
    sweep.configure(repo_root=tmp_path)
    locale_patch.configure(repo_root=tmp_path)
    icb.configure(repo_root=tmp_path)
    yield
    sweep.configure(repo_root=None)
    locale_patch.configure(repo_root=None)
    icb.configure()


def _write(tmp_path: Path, rel: str, text: str) -> Path:
    p = tmp_path / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


_NUGET_REGISTRY = {
    "words": {"net": {"registry_type": "nuget", "candidate": {"name": "Aspose.Words.FOSS"},
                        "verification": {"published": True}}},
}


class TestFullReadinessGateChain:
    def test_sweep_written_row_lets_a_genuinely_clean_source_propagate(self, tmp_path):
        source_rel = "content/docs.aspose.org/en/words/net/installation.md"
        source_abs = _write(tmp_path, source_rel, '{{< package-install-inline "words" "net" >}}\n')
        _write(tmp_path, "content/docs.aspose.org/fr/words/net/installation.md",
               "dotnet add package Aspose.Words.FOSS\n")
        store = ReconciliationStore(repo_root=tmp_path)

        result = sweep.run_combined_sweep(registry=_NUGET_REGISTRY, products={}, store=store)
        assert result["english_source_file_rows_written"] == 1

        ready, reason = locale_patch.is_english_source_ready("words", "net", source_abs, store=store)
        assert ready is True, reason

        summary = locale_patch.run_locale_patch(
            "words", "net", "docs.aspose.org", source_abs,
            [locale_patch.Patch(old_text="dotnet add package Aspose.Words.FOSS",
                                  new_text='{{< package-install-inline "words" "net" >}}')],
            store=store, dry_run=False,
        )
        assert summary["readiness_blocked"] is False
        assert summary["budget_blocked"] is False
        assert summary["files_modified"] == 1

        fr_text = (tmp_path / "content/docs.aspose.org/fr/words/net/installation.md").read_text(encoding="utf-8")
        assert "package-install-inline" in fr_text

    def test_sweep_written_row_correctly_refuses_when_source_still_literal(self, tmp_path):
        source_rel = "content/docs.aspose.org/en/words/net/installation.md"
        source_abs = _write(tmp_path, source_rel, "dotnet add package Aspose.Words.FOSS\n")
        _write(tmp_path, "content/docs.aspose.org/fr/words/net/installation.md",
               "dotnet add package Aspose.Words.FOSS\n")
        store = ReconciliationStore(repo_root=tmp_path)

        result = sweep.run_combined_sweep(registry=_NUGET_REGISTRY, products={}, store=store)
        assert result["english_source_file_rows_written"] == 1

        ready, reason = locale_patch.is_english_source_ready("words", "net", source_abs, store=store)
        assert ready is False
        assert "literal" in reason

        summary = locale_patch.run_locale_patch(
            "words", "net", "docs.aspose.org", source_abs,
            [locale_patch.Patch(old_text="dotnet add package Aspose.Words.FOSS", new_text="REPLACED")],
            store=store, dry_run=False,
        )
        assert summary["readiness_blocked"] is True

        fr_text = (tmp_path / "content/docs.aspose.org/fr/words/net/installation.md").read_text(encoding="utf-8")
        assert "REPLACED" not in fr_text  # never touched -- gate correctly refused

    def test_no_manual_workaround_row_needed_anymore(self, tmp_path):
        """The exact gap TC-PKG-02-05/07/18 hit: before this fix, 0 of the
        sweep's own rows had a content/ path, so is_english_source_ready()
        could never pass through the normal pipeline for ANY file -- only a
        hand-written row (like TC-PKG-02-05's workaround) could satisfy it.
        Prove a plain run_combined_sweep() call alone (no manual row
        insertion anywhere in this test) is now sufficient."""
        source_rel = "content/docs.aspose.org/en/cells/go/installation.md"
        source_abs = _write(tmp_path, source_rel, '{{< package-install "cells" "go" >}}\n')
        registry = {
            "cells": {"go": {"registry_type": "go_modules", "candidate": {"name": "aspose-cells-foss"},
                               "verification": {"published": True}}},
        }
        store = ReconciliationStore(repo_root=tmp_path)
        sweep.run_combined_sweep(registry=registry, products={}, store=store)

        # The exact live check TC-PKG-02-18's evidence ran ("0 of the real
        # inventory.jsonl's rows have a content/ path field") must now find >=1.
        history = store.read_history()
        content_paths = [r["path"] for r in history if r["path"].startswith("content/")]
        assert len(content_paths) >= 1

        ready, reason = locale_patch.is_english_source_ready("cells", "go", source_abs, store=store)
        assert ready is True, reason
