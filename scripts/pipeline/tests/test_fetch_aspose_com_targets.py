"""Regression test for TC-01/G-01 (MT009 SEED-16): --families must not
destroy other families already present in data/aspose_com_targets.json.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from commands.ops.fetch_aspose_com_targets import merge_preserved_families  # noqa: E402


def _write_existing_registry(data_dir: Path, families: list[str]) -> None:
    targets = {"products.aspose.com": {"families": {}, "platforms": {}}}
    all_urls = {}
    for fam in families:
        url = f"https://products.aspose.com/{fam}/"
        targets["products.aspose.com"]["families"][fam] = {
            "url": url, "http_status": 200, "redirect_chain": [],
        }
        all_urls[url] = {
            "http_status": 200, "type": "family-products",
            "family": fam, "platform": None, "redirect_chain": [],
        }
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "aspose_com_targets.json").write_text(
        json.dumps({
            "schema_version": "1.0",
            "provenance": {"generated_at": "2026-01-01T00:00:00Z", "total_targets": len(families)},
            "targets": targets,
            "all_urls": all_urls,
            "unavailable_sources": [],
            "family_platform_matrix": {},
        }, indent=2),
        encoding="utf-8",
    )


def test_scoped_run_preserves_other_families(tmp_path):
    """A --families html run must keep pre-existing cells/pdf entries."""
    _write_existing_registry(tmp_path / "data", ["cells", "pdf"])

    targets = {
        "products.aspose.com": {
            "families": {
                "html": {"url": "https://products.aspose.com/html/",
                          "http_status": 200, "redirect_chain": []},
            },
            "platforms": {},
        }
    }
    all_urls_flat = {
        "https://products.aspose.com/html/": {
            "http_status": 200, "type": "family-products",
            "family": "html", "platform": None, "redirect_chain": [],
        }
    }

    merge_preserved_families(targets, all_urls_flat, {"html"}, tmp_path)

    result_families = set(targets["products.aspose.com"]["families"].keys())
    assert result_families == {"html", "cells", "pdf"}, (
        f"Expected html (freshly scanned) + cells/pdf (preserved) but got {result_families}"
    )
    # Freshly-scanned family's data must not be clobbered by the merge.
    assert targets["products.aspose.com"]["families"]["html"]["url"] == "https://products.aspose.com/html/"
    # Preserved families' URLs must survive in all_urls_flat too.
    assert "https://products.aspose.com/cells/" in all_urls_flat
    assert "https://products.aspose.com/pdf/" in all_urls_flat


def test_scoped_run_no_existing_file_is_noop(tmp_path):
    """No pre-existing registry -> merge is a no-op, no crash."""
    targets = {"products.aspose.com": {"families": {"html": {}}, "platforms": {}}}
    all_urls_flat = {}
    merge_preserved_families(targets, all_urls_flat, {"html"}, tmp_path)
    assert set(targets["products.aspose.com"]["families"].keys()) == {"html"}


def test_scoped_run_never_overwrites_freshly_scanned_family(tmp_path):
    """If a family is both freshly-scanned and on disk, the fresh scan wins."""
    _write_existing_registry(tmp_path / "data", ["html"])
    # On-disk html entry has a stale/different URL than the fresh scan.
    stale = json.loads((tmp_path / "data" / "aspose_com_targets.json").read_text(encoding="utf-8"))
    stale["targets"]["products.aspose.com"]["families"]["html"]["url"] = "https://products.aspose.com/html/STALE/"
    (tmp_path / "data" / "aspose_com_targets.json").write_text(json.dumps(stale), encoding="utf-8")

    targets = {
        "products.aspose.com": {
            "families": {
                "html": {"url": "https://products.aspose.com/html/python-net/",
                          "http_status": 200, "redirect_chain": []},
            },
            "platforms": {},
        }
    }
    all_urls_flat = {}
    merge_preserved_families(targets, all_urls_flat, {"html"}, tmp_path)

    assert targets["products.aspose.com"]["families"]["html"]["url"] == "https://products.aspose.com/html/python-net/"
