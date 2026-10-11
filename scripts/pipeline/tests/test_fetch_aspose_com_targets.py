"""Regression test for TC-01/G-01 (MT009 SEED-16): --families must not
destroy other families already present in data/aspose_com_targets.json.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from commands.ops.fetch_aspose_com_targets import (  # noqa: E402
    merge_preserved_families, verify_url, _redirect_changed_path,
    configure, _read_output_hash, main, classify_url,
    PLATFORM_ALIASES as _FETCHER_PLATFORM_ALIASES,
    load_synthesis_override_candidates, synthesize_urls_for_subdomain,
)
import commands.ops.fetch_aspose_com_targets as fetch_targets_mod  # noqa: E402
from lib.backlink_targets import PLATFORM_ALIASES as _RESOLVER_PLATFORM_ALIASES  # noqa: E402
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


# ---------------------------------------------------------------------------
# TC17 (2026-08-21, MT009 SEED-15): fetch_sitemap_urls() must urljoin a
# sitemap-index child <loc> against the parent sitemap's own URL before
# recursing -- sitemap.org's spec requires <loc> to be absolute, but not
# every real-world generator complies, and a relative child <loc> previously
# broke the recursive fetch outright (session.get cannot resolve a bare
# relative path with no base).
# ---------------------------------------------------------------------------

from commands.ops.fetch_aspose_com_targets import fetch_sitemap_urls, TargetEntry  # noqa: E402


def _xml_response(text):
    resp = MagicMock()
    resp.status_code = 200
    resp.text = text
    return resp


def test_fetch_sitemap_urls_joins_relative_child_loc_against_parent():
    """A sitemap-index whose child <loc> is a relative path must still be
    fetched correctly -- the recursive call must receive the absolute URL."""
    index_xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        '<sitemap><loc>/sitemap-products.xml</loc></sitemap>'
        '</sitemapindex>'
    )
    urlset_xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        '<url><loc>https://products.aspose.com/cells/</loc></url>'
        '</urlset>'
    )
    session = MagicMock()
    session.get.side_effect = [_xml_response(index_xml), _xml_response(urlset_xml)]

    urls, _source_hash, http_status = fetch_sitemap_urls(
        "https://products.aspose.com/sitemap.xml", session
    )

    assert http_status == 200
    assert urls == ["https://products.aspose.com/cells/"]
    # The recursive call must have been made against the JOINED absolute URL,
    # not the raw relative "/sitemap-products.xml" (which would 404/fail).
    second_call_url = session.get.call_args_list[1].args[0]
    assert second_call_url == "https://products.aspose.com/sitemap-products.xml"


def test_fetch_sitemap_urls_absolute_child_loc_unaffected():
    """Negative control: an already-absolute child <loc> (the compliant,
    common case) must be used exactly as-is -- urljoin must be a no-op here."""
    index_xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        '<sitemap><loc>https://products.aspose.com/sitemap-products.xml</loc></sitemap>'
        '</sitemapindex>'
    )
    urlset_xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        '<url><loc>https://products.aspose.com/words/</loc></url>'
        '</urlset>'
    )
    session = MagicMock()
    session.get.side_effect = [_xml_response(index_xml), _xml_response(urlset_xml)]

    urls, _source_hash, http_status = fetch_sitemap_urls(
        "https://products.aspose.com/sitemap.xml", session
    )

    assert http_status == 200
    assert urls == ["https://products.aspose.com/words/"]
    second_call_url = session.get.call_args_list[1].args[0]
    assert second_call_url == "https://products.aspose.com/sitemap-products.xml"


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


# ---------------------------------------------------------------------------
# TC5 (2026-08-21): PLATFORM_ALIASES unification regression tests.
#
# Before this fix, fetch_aspose_com_targets.py maintained its own, independent
# PLATFORM_ALIASES dict that had drifted from lib/backlink_targets.py's richer
# table -- missing python-cpp/go-cpp/nodejs-cpp/javascript-cpp/php/php-java/
# jasperreports/rust-cpp. Any of those platforms, though live and HTTP-200 on
# aspose.com, classified as "unknown" here and were silently dropped from the
# structured target map (confirmed live: reference.aspose.com/pdf/python-cpp/).
# ---------------------------------------------------------------------------

def test_platform_aliases_is_the_single_canonical_definition():
    """The fetcher must import, not redefine, the alias table -- if this ever
    fails, someone reintroduced a second, divergable copy."""
    assert _FETCHER_PLATFORM_ALIASES is _RESOLVER_PLATFORM_ALIASES


def test_previously_dropped_platform_aliases_now_classify_correctly():
    """Every alias that used to be missing from the fetcher's local table
    (and therefore silently dropped as "unknown") must now resolve."""
    previously_missing = {
        "python-cpp": "python",
        "go-cpp": "go",
        "nodejs-cpp": "nodejs",
        "javascript-cpp": "nodejs",
        "php": "php",
        "php-java": "php",
        "jasperreports": "jasperreports",
        "rust-cpp": "rust",
    }
    for alias, expected_canonical in previously_missing.items():
        assert _FETCHER_PLATFORM_ALIASES.get(alias) == expected_canonical, (
            f"{alias!r} must classify as {expected_canonical!r}, not silently drop to unknown"
        )


def test_real_world_previously_broken_url_now_classifies_as_known_platform():
    """The exact live case found during the backlink-governance-redesign
    investigation: reference.aspose.com/pdf/python-cpp/ is a real, verified
    HTTP-200 page that was invisible to the resolver purely because of the
    alias-table gap, not because the data didn't exist."""
    url_type, family, platform = classify_url(
        "https://reference.aspose.com/pdf/python-cpp/", "reference.aspose.com"
    )
    assert family == "pdf"
    assert platform == "python"
    assert url_type != "unknown"


def test_rust_short_alias_still_works_after_unification():
    """fetch_aspose_com_targets.py's table had "rs" -> "rust" that
    lib/backlink_targets.py's table lacked before this fix -- confirm the
    union preserved it in both directions, not just the fetcher's superset."""
    assert _FETCHER_PLATFORM_ALIASES.get("rs") == "rust"


def test_alias_not_in_table_still_classifies_unknown():
    """Negative control: unification must not over-match -- a genuinely
    unrecognized alias must still classify as unknown, not silently match."""
    assert _FETCHER_PLATFORM_ALIASES.get("totally-made-up-platform-xyz") is None


# ---------------------------------------------------------------------------
# TC17 (2026-08-21): inventory_completeness provenance marker.
#
# Confirmed live (2026-08-21): products.aspose.com's and docs.aspose.com's
# real sitemaps are minimal (3 and 2 URLs respectively -- homepage/search/
# categories only, no per-product pages) -- an external fact about those
# sites, not a fetcher bug. "synthesized" is the only viable inventory
# method for those two subdomains, and every entry must say so explicitly
# rather than leaving "was this independently discovered, or just guessed
# and HTTP-verified" ambiguous.
# ---------------------------------------------------------------------------

def test_target_entry_defaults_to_crawled():
    """The real-sitemap-crawl path is the default -- entries built without
    an explicit value must not silently claim to be synthesized."""
    entry = TargetEntry(
        url="https://reference.aspose.com/pdf/net/", http_status=200,
        redirect_chain=[], validated_via="head", retry_count=0,
        subdomain="reference.aspose.com", url_type="platform-reference-root",
        family="pdf", platform="net",
    )
    assert entry.inventory_completeness == "crawled"


def test_target_entry_explicit_synthesized_marker():
    entry = TargetEntry(
        url="https://products.aspose.com/cells/", http_status=200,
        redirect_chain=[], validated_via="head", retry_count=0,
        subdomain="products.aspose.com", url_type="family-products",
        family="cells", platform=None, inventory_completeness="synthesized",
    )
    assert entry.inventory_completeness == "synthesized"


# ---------------------------------------------------------------------------
# TC6 (2026-08-21): synthesis must also try a verified override's target
# slug, not just the local aspose.org platform slug. Confirmed live
# (2026-08-21, curl): docs.aspose.com/3d/python-net/ -> HTTP 200,
# docs.aspose.com/3d/python/ -> HTTP 404; docs.aspose.com/pdf/go-cpp/ ->
# HTTP 200, docs.aspose.com/pdf/go/ -> HTTP 404. Before this fix, synthesis
# for docs.aspose.com (a synthesis-only subdomain per TC17) could only ever
# guess the local slug ("python", "go") and had no way to discover the real
# bridge page -- even though resolve_backlink() already applies the exact
# same override at lookup time and expects the override's slug to already
# be present in the target map.
# ---------------------------------------------------------------------------

def _write_overrides_file(data_dir: Path, overrides: dict) -> Path:
    backlinks_dir = data_dir / "backlinks"
    backlinks_dir.mkdir(parents=True, exist_ok=True)
    path = backlinks_dir / "platform_canonical_overrides.yaml"
    lines = ["overrides:"]
    for key, entry in overrides.items():
        lines.append(f'  "{key}":')
        for field_name, value in entry.items():
            if isinstance(value, bool):
                lines.append(f"    {field_name}: {'true' if value else 'false'}")
            else:
                lines.append(f'    {field_name}: "{value}"')
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def test_load_synthesis_override_candidates_reads_verified_entries(tmp_path):
    _write_overrides_file(tmp_path / "data", {
        "3d/python": {"target_platform": "python-net", "http_verified": True},
        "pdf/go": {"target_platform": "go-cpp", "http_verified": True},
    })
    result = load_synthesis_override_candidates(tmp_path)
    assert result == {"3d/python": "python-net", "pdf/go": "go-cpp"}


def test_load_synthesis_override_candidates_excludes_unverified_entries(tmp_path):
    _write_overrides_file(tmp_path / "data", {
        "cells/rust": {"target_platform": "rust-cpp", "http_verified": False},
    })
    result = load_synthesis_override_candidates(tmp_path)
    assert result == {}


def test_load_synthesis_override_candidates_missing_file_returns_empty(tmp_path):
    assert load_synthesis_override_candidates(tmp_path) == {}


def test_load_synthesis_override_candidates_against_real_repo_file():
    """The real repo file already has verified 3d/python and pdf/go entries
    -- confirms this reads live production config, not just fixtures."""
    result = load_synthesis_override_candidates(fetch_targets_mod._REPO_ROOT)
    assert result.get("3d/python") == "python-net"
    assert result.get("pdf/go") == "go-cpp"


def test_synthesize_emits_override_candidate_in_addition_to_local_slug():
    """The confirmed-live regression case: docs.aspose.com synthesis for
    3d/python must ALSO emit a 3d/python-net candidate, not just 3d/python."""
    candidates = synthesize_urls_for_subdomain(
        "docs.aspose.com",
        {"3d": {"python"}},
        None,
        canonical_overrides={"3d/python": "python-net"},
    )
    urls = [c[0] for c in candidates]
    assert "https://docs.aspose.com/3d/python/" in urls
    assert "https://docs.aspose.com/3d/python-net/" in urls
    # The override candidate must be keyed under the override's own slug,
    # matching what resolve_backlink() will look up once applied.
    override_entry = next(c for c in candidates if c[0].endswith("/python-net/"))
    assert override_entry[3] == "python-net"  # platform field


def test_synthesize_without_overrides_only_emits_local_slug():
    """Backward compatible: omitting canonical_overrides (or passing None)
    must behave exactly as before -- no override candidates."""
    candidates = synthesize_urls_for_subdomain("docs.aspose.com", {"3d": {"python"}}, None)
    urls = [c[0] for c in candidates]
    assert "https://docs.aspose.com/3d/python/" in urls
    assert "https://docs.aspose.com/3d/python-net/" not in urls


def test_synthesize_skips_override_when_identical_to_local_slug():
    """Negative control: an override that maps a platform to itself (a
    degenerate/no-op case) must not produce a duplicate candidate."""
    candidates = synthesize_urls_for_subdomain(
        "docs.aspose.com",
        {"3d": {"python"}},
        None,
        canonical_overrides={"3d/python": "python"},
    )
    urls = [c[0] for c in candidates]
    assert urls.count("https://docs.aspose.com/3d/python/") == 1


# ---------------------------------------------------------------------------
# TC8 (2026-08-21): per-URL last_verified freshness field. Narrowed scope --
# the map-wide TTL gate (STALE_WARN_DAYS/STALE_BLOCK_DAYS) and the daily
# scheduled re-verification workflow already shipped via unrelated mission
# MT022 and are confirmed live/working; only this per-entry field was
# missing, needed so a scoped run doesn't leave every entry's freshness
# indistinguishable from the map-wide provenance.generated_at stamp.
# ---------------------------------------------------------------------------

def test_target_entry_last_verified_defaults_to_none():
    """Backward compatible: omitting last_verified must not break existing
    TargetEntry construction sites that predate this field."""
    entry = TargetEntry(
        url="https://reference.aspose.com/pdf/net/", http_status=200,
        redirect_chain=[], validated_via="head", retry_count=0,
        subdomain="reference.aspose.com", url_type="platform-reference-root",
        family="pdf", platform="net",
    )
    assert entry.last_verified is None


def test_target_entry_explicit_last_verified():
    entry = TargetEntry(
        url="https://products.aspose.com/cells/", http_status=200,
        redirect_chain=[], validated_via="head", retry_count=0,
        subdomain="products.aspose.com", url_type="family-products",
        family="cells", platform=None, last_verified="2026-08-21T00:00:00+00:00",
    )
    assert entry.last_verified == "2026-08-21T00:00:00+00:00"


def test_scoped_run_preserves_last_verified_of_untouched_families(tmp_path):
    """The whole point of a per-entry (not map-wide) timestamp: a --families
    html run must not silently overwrite cells/pdf's own last_verified with
    the html run's timestamp -- merge_preserved_families() must carry the
    untouched families' existing per-entry values forward unchanged."""
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True)
    (data_dir / "aspose_com_targets.json").write_text(
        json.dumps({
            "schema_version": "1.0",
            "provenance": {"generated_at": "2026-01-01T00:00:00Z", "total_targets": 1},
            "targets": {
                "products.aspose.com": {
                    "families": {
                        "cells": {
                            "url": "https://products.aspose.com/cells/",
                            "http_status": 200, "redirect_chain": [],
                            "last_verified": "2026-01-01T00:00:00Z",
                        },
                    },
                    "platforms": {},
                },
            },
            "all_urls": {
                "https://products.aspose.com/cells/": {
                    "http_status": 200, "type": "family-products",
                    "family": "cells", "platform": None, "redirect_chain": [],
                    "last_verified": "2026-01-01T00:00:00Z",
                },
            },
            "unavailable_sources": [],
            "family_platform_matrix": {},
        }, indent=2),
        encoding="utf-8",
    )

    fresh_targets = {
        "products.aspose.com": {
            "families": {
                "html": {
                    "url": "https://products.aspose.com/html/",
                    "http_status": 200, "redirect_chain": [],
                    "last_verified": "2026-08-21T00:00:00Z",
                },
            },
            "platforms": {},
        },
    }
    fresh_all_urls = {
        "https://products.aspose.com/html/": {
            "http_status": 200, "type": "family-products",
            "family": "html", "platform": None, "redirect_chain": [],
            "last_verified": "2026-08-21T00:00:00Z",
        },
    }
    merge_preserved_families(fresh_targets, fresh_all_urls, {"html"}, tmp_path)

    cells_entry = fresh_targets["products.aspose.com"]["families"]["cells"]
    assert cells_entry["last_verified"] == "2026-01-01T00:00:00Z"  # untouched, not overwritten
    html_entry = fresh_targets["products.aspose.com"]["families"]["html"]
    assert html_entry["last_verified"] == "2026-08-21T00:00:00Z"  # freshly verified this run
