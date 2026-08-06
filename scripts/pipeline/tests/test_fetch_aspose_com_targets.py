"""Regression test for TC-01/G-01 (MT009 SEED-16): --families must not
destroy other families already present in data/aspose_com_targets.json.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from commands.ops.fetch_aspose_com_targets import (  # noqa: E402
    merge_preserved_families, verify_url, _redirect_changed_path,
    configure, _read_output_hash, main,
)
import commands.ops.fetch_aspose_com_targets as fetch_targets_mod  # noqa: E402
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


# ---------------------------------------------------------------------------
# Retry-on-transient-status hardening (TC-01, MT022-2026-08-06)
#
# Found live (2026-08-06, re-reading verify_url() while investigating the
# untracked "5 status regressions" finding from commit e40ed6b509): the retry
# loop only fired on network EXCEPTIONS (Timeout/ConnError/RequestException) --
# a *successful* HTTP response carrying 429/500/502/503/504 returned
# immediately on the first attempt, indistinguishable from a confirmed-dead
# page. A single CDN gateway hiccup (502) or rate-limit (429) got recorded as
# permanent fact with zero retry. Fixed: these statuses now retry through the
# same backoff loop as network exceptions; 404 remains terminal on first
# observation (a real "not found" signal, not transient).
#
# configure(sleep_fn=...) is the seam used here instead of monkeypatching
# time.sleep directly (AGENTS.md 16 -- avoids a T1/T2 monkeypatch-lint hit).
# ---------------------------------------------------------------------------

def setup_function(_fn):
    # Reset the module-level sleep seam before every test in this file so a
    # prior test's injected fake never leaks into an unrelated one.
    configure()


def teardown_function(_fn):
    configure()


def test_verify_url_retries_on_transient_502_then_succeeds():
    url = "https://docs.aspose.com/cad/net/"
    session = MagicMock()
    session.head.side_effect = [
        _mock_response(502, url, history=[]),
        _mock_response(200, url, history=[]),
    ]
    sleeps = []
    configure(sleep_fn=lambda seconds: sleeps.append(seconds))

    status, chain, resolved_url, via, attempt = verify_url(url, session)

    assert status == 200
    assert via == "head"
    assert session.head.call_count == 2
    assert session.get.call_count == 0, "a HEAD-level transient retry must not fall through to GET"
    assert sleeps == [2], "must sleep once between the two attempts, via the injected seam not real time.sleep"


def test_verify_url_404_is_terminal_no_retry():
    url = "https://docs.aspose.com/cells/typescript/"
    session = MagicMock()
    session.head.return_value = _mock_response(404, url, history=[])
    sleeps = []
    configure(sleep_fn=lambda seconds: sleeps.append(seconds))

    status, chain, resolved_url, via, attempt = verify_url(url, session)

    assert status == 404
    assert attempt == 0
    assert session.head.call_count == 1
    assert sleeps == [], "404 must not trigger any retry sleep"


def test_verify_url_exhausts_retries_on_persistent_502():
    url = "https://docs.aspose.com/page/python/"
    session = MagicMock()
    session.head.return_value = _mock_response(502, url, history=[])
    sleeps = []
    configure(sleep_fn=lambda seconds: sleeps.append(seconds))

    status, chain, resolved_url, via, attempt = verify_url(url, session, max_retries=3)

    assert status == 502, "a persistently-failing endpoint must still end up correctly recorded as 502"
    assert session.head.call_count == 3
    assert session.get.call_count == 0
    assert sleeps == [2, 4], "2 sleeps between 3 attempts, using the real backoff schedule"


def test_verify_url_transient_status_via_get_fallback_also_retries():
    """403 triggers the existing GET fallback; if GET itself then returns a
    transient status, the outer retry loop must still fire (not just the
    HEAD-side transient branch)."""
    url = "https://docs.aspose.com/email/python/"
    session = MagicMock()
    session.head.return_value = _mock_response(403, url, history=[])
    session.get.side_effect = [
        _mock_response(503, url, history=[]),
        _mock_response(200, url, history=[]),
    ]
    sleeps = []
    configure(sleep_fn=lambda seconds: sleeps.append(seconds))

    status, chain, resolved_url, via, attempt = verify_url(url, session)

    assert status == 200
    assert via == "get"
    assert session.get.call_count == 2
    assert sleeps == [2]


def test_configure_resets_to_real_time_sleep_by_default():
    configure(sleep_fn=lambda seconds: None)
    configure()  # no args -> resets to time.sleep
    assert fetch_targets_mod._sleep_fn is fetch_targets_mod.time.sleep


# ---------------------------------------------------------------------------
# Write-path concurrency guard (TC-01, MT022-2026-08-06)
#
# main()'s write step used to be a bare write_text() with no check that the
# on-disk file was unchanged since this run started -- exactly the class of
# bug that already let commit d2dce37de5 silently clobber commit e40ed6b509's
# fix (backlog G-49/TC-MT018-06). _read_output_hash() is the pure comparison
# primitive both the pre-run capture and the pre-write check now share.
# ---------------------------------------------------------------------------

def test_read_output_hash_returns_none_for_missing_file(tmp_path):
    assert _read_output_hash(tmp_path / "does_not_exist.json") is None


def test_read_output_hash_returns_none_for_corrupt_json(tmp_path):
    p = tmp_path / "corrupt.json"
    p.write_text("{not valid json", encoding="utf-8")
    assert _read_output_hash(p) is None


def test_read_output_hash_reads_real_value(tmp_path):
    p = tmp_path / "aspose_com_targets.json"
    p.write_text(json.dumps({"provenance": {"output_hash": "sha256:abc123"}}), encoding="utf-8")
    assert _read_output_hash(p) == "sha256:abc123"


def test_main_aborts_when_registry_changed_underneath_it(tmp_path):
    """Simulates: this run captured a starting hash, then -- while the run was
    doing its (mocked) work -- another session wrote a different hash to disk.
    main() must abort (return 1) rather than silently overwrite it, and must
    NOT write when it aborts."""
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True)
    json_path = data_dir / "aspose_com_targets.json"
    json_path.write_text(json.dumps({
        "schema_version": "1.0",
        "provenance": {"generated_at": "2026-01-01T00:00:00Z", "output_hash": "sha256:original", "total_targets": 0},
        "targets": {}, "all_urls": {}, "unavailable_sources": [], "family_platform_matrix": {},
    }), encoding="utf-8")

    def fake_build_target_map(args, session):
        # Simulate a concurrent session writing a DIFFERENT hash while this
        # (mocked, instantaneous-in-test) run was "in flight".
        json_path.write_text(json.dumps({
            "schema_version": "1.0",
            "provenance": {"generated_at": "2026-01-01T00:05:00Z", "output_hash": "sha256:concurrent-write", "total_targets": 1},
            "targets": {}, "all_urls": {}, "unavailable_sources": [], "family_platform_matrix": {},
        }), encoding="utf-8")
        return (
            {"schema_version": "1.0",
             "provenance": {"generated_at": "2026-01-01T00:10:00Z", "output_hash": "sha256:this-run-result", "total_targets": 0},
             "targets": {}, "all_urls": {}, "unavailable_sources": [], "family_platform_matrix": {}},
            [],
        )

    exit_code = main(["--repo-root", str(tmp_path), "--skip-http-verify"], build_fn=fake_build_target_map)

    assert exit_code == 1
    on_disk = json.loads(json_path.read_text(encoding="utf-8"))
    assert on_disk["provenance"]["output_hash"] == "sha256:concurrent-write", (
        "the concurrent session's write must survive -- this run's result must NOT be written"
    )


def test_main_force_overwrites_despite_concurrent_change(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True)
    json_path = data_dir / "aspose_com_targets.json"
    json_path.write_text(json.dumps({
        "schema_version": "1.0",
        "provenance": {"generated_at": "2026-01-01T00:00:00Z", "output_hash": "sha256:original", "total_targets": 0},
        "targets": {}, "all_urls": {}, "unavailable_sources": [], "family_platform_matrix": {},
    }), encoding="utf-8")

    def fake_build_target_map(args, session):
        json_path.write_text(json.dumps({
            "schema_version": "1.0",
            "provenance": {"generated_at": "2026-01-01T00:05:00Z", "output_hash": "sha256:concurrent-write", "total_targets": 1},
            "targets": {}, "all_urls": {}, "unavailable_sources": [], "family_platform_matrix": {},
        }), encoding="utf-8")
        return (
            {"schema_version": "1.0",
             "provenance": {"generated_at": "2026-01-01T00:10:00Z", "output_hash": "sha256:this-run-result", "total_targets": 0},
             "targets": {}, "all_urls": {}, "unavailable_sources": [], "family_platform_matrix": {}},
            [],
        )

    exit_code = main(["--repo-root", str(tmp_path), "--skip-http-verify", "--force"], build_fn=fake_build_target_map)

    assert exit_code == 0
    on_disk = json.loads(json_path.read_text(encoding="utf-8"))
    assert on_disk["provenance"]["output_hash"] == "sha256:this-run-result"
