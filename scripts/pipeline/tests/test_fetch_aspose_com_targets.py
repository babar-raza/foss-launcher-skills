"""Regression test for TC-01/G-01 (MT009 SEED-16): --families must not
destroy other families already present in data/aspose_com_targets.json.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from commands.ops.fetch_aspose_com_targets import (  # noqa: E402
    merge_preserved_families, verify_url, _redirect_changed_path,
)
from unittest.mock import MagicMock


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


# ---------------------------------------------------------------------------
# _redirect_changed_path / verify_url resolved-URL tracking
#
# Found live (2026-08-01): a synthesized products.aspose.com/cells/go/ URL
# verified as "http_status: 200" -- but that 200 was reached only AFTER a 301
# redirect to the bundled products.aspose.com/cells/go-cpp/ page. verify_url()
# discarded the actual resolved URL, so the registry recorded the WRONG,
# never-canonical URL as if it were directly valid. Fixed by returning and
# comparing the resolved URL against the request.
# ---------------------------------------------------------------------------

def test_redirect_changed_path_true_for_different_path():
    assert _redirect_changed_path(
        "https://products.aspose.com/cells/go/",
        "https://products.aspose.com/cells/go-cpp/",
    ) is True


def test_redirect_changed_path_false_for_trailing_slash_only():
    assert _redirect_changed_path(
        "https://products.aspose.com/cells/go",
        "https://products.aspose.com/cells/go/",
    ) is False


def test_redirect_changed_path_false_for_scheme_upgrade():
    assert _redirect_changed_path(
        "http://products.aspose.com/cells/go/",
        "https://products.aspose.com/cells/go/",
    ) is False


def _mock_response(status_code, url, history=()):
    resp = MagicMock()
    resp.status_code = status_code
    resp.url = url
    resp.history = list(history)
    resp.raw.read.return_value = b""
    return resp


def test_verify_url_returns_resolved_url_on_redirect():
    """A HEAD request that redirects must surface the FINAL url, not just the
    originally-requested one -- this is what the caller compares against the
    request to detect a path-changing redirect."""
    original = "https://products.aspose.com/cells/go/"
    resolved = "https://products.aspose.com/cells/go-cpp/"
    hop = MagicMock()
    hop.url = original
    session = MagicMock()
    session.head.return_value = _mock_response(200, resolved, history=[hop])

    status, chain, resolved_url, via, retries = verify_url(original, session)

    assert status == 200
    assert resolved_url == resolved
    assert chain == [original]
    assert via == "head"


def test_verify_url_resolved_equals_request_when_no_redirect():
    original = "https://products.aspose.com/cells/java/"
    session = MagicMock()
    session.head.return_value = _mock_response(200, original, history=[])

    status, chain, resolved_url, via, retries = verify_url(original, session)

    assert status == 200
    assert resolved_url == original
    assert chain == []
