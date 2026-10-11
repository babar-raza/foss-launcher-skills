"""Regression tests for TC-PSD-HRD-9N-6 — a single-product `index.py
{family} {platform}` invocation must never rewrite a BYSTANDER product's
own `merged/index.json` file.

Found live during MT076 (psd/net launch) while re-running `/truth-index
psd net`: running `index.py psd net` also silently rewrote
`knowledge/barcode/python/merged/index.json` (wiping its class_graph) and
`knowledge/pdf/typescript/merged/index.json` (flipping `vectors_available`
true -> false), as a side effect of the HARDEN-words-net fix (2026-07-22)
looping over every discovered product to rebuild the cross-product
`_index.json` summary — that loop calls the full `build_index()`, which
has the side effect of writing `merged/index.json` for whichever
family/platform it's given (`index.py` line ~440), for every bystander
product too, not just the one explicitly requested.

Root cause: `main()`'s single-product branch (`index.py` line ~578) does
`e = entry if (fam, plat) == (family, platform) else build_index(fam, plat)`
for every product `discover_products()` yields, to get each one's summary
entry for `_index.json` — but `build_index()` is not a read-only summary
function; it unconditionally writes that product's own `merged/index.json`
to disk (and `.pipeline_state.json`) as a side effect, recomputing
environment-dependent fields (`class_graph` from a possibly-absent
`class_graph.json`, `vectors_available` from a possibly-absent local
`_vectors/` directory) that can legitimately differ between the local
checkout currently running `index.py` and whatever environment last
produced the committed, correct `merged/index.json` for that bystander
product.
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from index import build_index  # noqa: E402
import index as _index_module  # noqa: E402

from test_index import _make_merged_dir  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_index():
    yield
    _index_module.configure()


def _seed_committed_index_json(merged_dir: Path, *, class_graph: dict, vectors_available: bool) -> None:
    """Simulate a prior, correct, already-committed merged/index.json for
    a bystander product -- the state build_index() must not destroy when
    that product is NOT the one explicitly requested."""
    (merged_dir / "index.json").write_text(
        json.dumps({
            "schema_version": 2,
            "family": "cells",
            "platform": "python",
            "class_graph": class_graph,
            "vectors_available": vectors_available,
            "classes": ["Workbook", "Worksheet"],
        }),
        encoding="utf-8",
    )


class TestSingleProductInvocationDoesNotRewriteBystanderProducts:
    def test_bystander_class_graph_not_wiped(self, tmp_path, monkeypatch):
        words_merged = _make_merged_dir(tmp_path, "words", "net")
        cells_merged = _make_merged_dir(tmp_path, "cells", "python")
        # cells/python has NO class_graph.json in this checkout (matching
        # the real-world case: the bug was found on barcode/python, which
        # had no class_graph.json locally but DID have a real, rich
        # class_graph already committed in its own merged/index.json from
        # an earlier run/environment where it was available).
        rich_class_graph = {"Workbook": ["Workbench"], "Worksheet": ["Workbook"]}
        _seed_committed_index_json(cells_merged, class_graph=rich_class_graph, vectors_available=True)
        _index_module.configure(knowledge_root=tmp_path / "knowledge")

        monkeypatch.setattr(sys, "argv", ["index.py", "words", "net"])
        _index_module.main()

        cells_index = json.loads((cells_merged / "index.json").read_text(encoding="utf-8"))
        assert cells_index["class_graph"] == rich_class_graph, (
            "a single-product invocation for words/net must not destroy "
            "cells/python's own, already-committed class_graph -- this is "
            "the exact live regression found on barcode/python (338-line "
            "class_graph wiped to {})"
        )

    def test_bystander_vectors_available_not_flipped(self, tmp_path, monkeypatch):
        words_merged = _make_merged_dir(tmp_path, "words", "net")
        cells_merged = _make_merged_dir(tmp_path, "cells", "python")
        # No knowledge/_vectors/cells/python/ dir in this checkout, but the
        # bystander's own already-committed index.json correctly recorded
        # vectors_available: true from whatever environment last built it.
        _seed_committed_index_json(cells_merged, class_graph={}, vectors_available=True)
        _index_module.configure(knowledge_root=tmp_path / "knowledge")

        monkeypatch.setattr(sys, "argv", ["index.py", "words", "net"])
        _index_module.main()

        cells_index = json.loads((cells_merged / "index.json").read_text(encoding="utf-8"))
        assert cells_index["vectors_available"] is True, (
            "a single-product invocation for words/net must not flip "
            "cells/python's own vectors_available from true to false -- "
            "this is the exact live regression found on pdf/typescript"
        )

    def test_negative_control_full_rebuild_legitimately_touches_every_product(self, tmp_path, monkeypatch):
        """`index.py all` is SUPPOSED to recompute every product's own
        merged/index.json from current local environment state -- this is
        correct, intentional behavior, not the bug. Confirms the fix for
        the single-product case does not accidentally disable the
        legitimate full-rebuild path too."""
        _make_merged_dir(tmp_path, "words", "net")
        cells_merged = _make_merged_dir(tmp_path, "cells", "python")
        _seed_committed_index_json(cells_merged, class_graph={"Stale": ["Graph"]}, vectors_available=True)
        _index_module.configure(knowledge_root=tmp_path / "knowledge")

        monkeypatch.setattr(sys, "argv", ["index.py", "all"])
        _index_module.main()

        cells_index = json.loads((cells_merged / "index.json").read_text(encoding="utf-8"))
        # No class_graph.json exists in this checkout for cells/python, so
        # a legitimate full rebuild correctly recomputes it as empty --
        # this is NOT the bug (the bug is doing this during a
        # SINGLE-product invocation for a DIFFERENT product).
        assert cells_index["class_graph"] == {}

    def test_bystander_display_name_keeps_platform_suffix(self, tmp_path, monkeypatch):
        """Found live while verifying the fix against the real repo (not
        just the unit fixtures above): the first fix attempt read
        `display_name` straight off the bystander's own merged/index.json
        file -- but that file stores just the bare family name (e.g.
        "Aspose.Cells"), never the " for {Platform}" suffix _index.json's
        OWN summary entries need (e.g. "Aspose.Cells for Python"). Confirms
        the corrected version recomputes this one pure, deterministic,
        environment-independent field instead of reading either file."""
        words_merged = _make_merged_dir(tmp_path, "words", "net")
        cells_merged = _make_merged_dir(tmp_path, "cells", "python")
        _seed_committed_index_json(cells_merged, class_graph={}, vectors_available=True)
        _index_module.configure(knowledge_root=tmp_path / "knowledge")

        monkeypatch.setattr(sys, "argv", ["index.py", "words", "net"])
        _index_module.main()

        index_path = tmp_path / "knowledge" / "_index.json"
        after = json.loads(index_path.read_text(encoding="utf-8"))
        cells_entry = next(p for p in after["products"] if p["family"] == "cells")
        assert cells_entry["display_name"] == "Aspose.Cells for Python"

    def test_bystander_vectors_summary_fields_preserved_from_prior_index(self, tmp_path, monkeypatch):
        """Found live while verifying the fix against the real repo:
        vectors_current/vectors_status/vectors_generated_at are NEVER
        persisted into merged/index.json at all (only computed fresh for
        _index.json's own summary) -- the first fix attempt had no source
        to recover them from for a bystander, so they silently defaulted
        to missing/null on every single-product run, discarding real
        prior values across the WHOLE portfolio (confirmed live: a real
        run flipped 30+ already-launched products' vectors_status from
        "current"/"stale" with real timestamps to "missing"/null). The
        fix must read these 3 fields from the PRIOR _index.json's own
        entry for that bystander instead."""
        _make_merged_dir(tmp_path, "words", "net")
        _make_merged_dir(tmp_path, "cells", "python")
        _index_module.configure(knowledge_root=tmp_path / "knowledge")

        # Seed a prior _index.json (as a real earlier full/partial run
        # would have produced) recording cells/python as vectors-current
        # with a real timestamp.
        index_path = tmp_path / "knowledge" / "_index.json"
        index_path.write_text(json.dumps({"products": [
            {"family": "cells", "platform": "python", "display_name": "Aspose.Cells for Python",
             "api_confidence": "high", "stale": False, "class_count": 2, "claim_count": 2,
             "vectors_current": True, "vectors_status": "current",
             "vectors_generated_at": "2026-09-10T10:57:32.658162Z"},
        ]}), encoding="utf-8")
        # cells/python's own merged/index.json must also exist (mirroring
        # a real prior build) so the bystander path is taken at all.
        _seed_committed_index_json(
            tmp_path / "knowledge" / "cells" / "python" / "merged",
            class_graph={}, vectors_available=True,
        )

        monkeypatch.setattr(sys, "argv", ["index.py", "words", "net"])
        _index_module.main()

        after = json.loads(index_path.read_text(encoding="utf-8"))
        cells_entry = next(p for p in after["products"] if p["family"] == "cells")
        assert cells_entry["vectors_current"] is True
        assert cells_entry["vectors_status"] == "current"
        assert cells_entry["vectors_generated_at"] == "2026-09-10T10:57:32.658162Z"

    def test_requested_products_own_index_json_still_freshly_written(self, tmp_path, monkeypatch):
        """The fix must not go too far and stop writing the EXPLICITLY
        requested product's own merged/index.json."""
        words_merged = _make_merged_dir(tmp_path, "words", "net")
        _make_merged_dir(tmp_path, "cells", "python")
        _index_module.configure(knowledge_root=tmp_path / "knowledge")

        monkeypatch.setattr(sys, "argv", ["index.py", "words", "net"])
        _index_module.main()

        words_index = json.loads((words_merged / "index.json").read_text(encoding="utf-8"))
        assert words_index["family"] == "words"
        assert words_index["platform"] == "net"
