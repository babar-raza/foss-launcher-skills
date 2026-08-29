"""Tests for scripts/llms_verify.py (new 2026-08-29, TASK_BACKLOG.md SYNC-6).

Uses a REAL local HTTP server (loopback, in-process background thread), not
a mocked fetch function, for the end-to-end proof -- genuine socket I/O,
fully offline and deterministic.
"""
import http.server
import json
import sys
import threading
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import llms_verify  # noqa: E402


@pytest.fixture
def local_server(tmp_path):
    """Serve tmp_path over loopback HTTP on an OS-assigned free port."""
    handler = lambda *a, **kw: http.server.SimpleHTTPRequestHandler(*a, directory=str(tmp_path), **kw)
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_address[1]
    try:
        yield f"http://127.0.0.1:{port}", tmp_path
    finally:
        server.shutdown()
        thread.join(timeout=5)


def test_default_fetch_real_socket_success(local_server):
    base_url, root = local_server
    (root / "hello.txt").write_text("Site: docs\nTitle: Hello\n\nBody text.\n", encoding="utf-8")
    status, content_type, body = llms_verify.default_fetch(base_url + "/hello.txt")
    assert status == 200
    assert "Body text." in body


def test_default_fetch_real_socket_404(local_server):
    base_url, _ = local_server
    status, content_type, body = llms_verify.default_fetch(base_url + "/does-not-exist.txt")
    assert status == 404


def test_check_page_flags_missing_content():
    result = llms_verify.check_page("http://x/y.txt", "", 200, "text/plain")
    assert result["ok"] is False
    assert result["checks"]["has_content"] is False


def test_check_page_flags_shortcode_leak():
    result = llms_verify.check_page("http://x/y.txt", "some {{< shortcode >>}} text here", 200, "text/plain")
    assert result["checks"]["no_shortcode"] is False


def test_check_page_flags_non_200():
    result = llms_verify.check_page("http://x/y.txt", "", 404, "")
    assert result["ok"] is False
    assert result["checks"]["http_200"] is False


def test_check_page_passes_clean_page():
    result = llms_verify.check_page("http://x/y.txt", "Site: docs\nTitle: OK\n\nGood body content.\n", 200, "text/plain")
    assert result["ok"] is True


# --- verify_site / main() against the real generic fixture -----------------

FIXTURE_ROOT = REPO_ROOT / "tests" / "fixtures" / "generic_hugo_repo"


def test_verify_site_against_real_generated_output(tmp_path):
    """base_url is documented (skills/llms-verify.md) to point directly at
    wherever llms-output/{site}/ itself is served from -- so the HTTP
    server here is pointed at output_root/docs/ directly, exercising
    verify_site's base_url + relative-to-site-dir URL construction exactly
    as documented (not a Hugo-URL-mapped root; that gap is stated, not
    hidden in the skill doc)."""
    import http.server
    import threading

    import llms_generate

    output_root = tmp_path / "llms-output"
    llms_generate.generate_site(
        FIXTURE_ROOT, output_root, "docs",
        "content/docs.example.org/en/{family}/{platform}/",
    )
    site_dir = output_root / "docs"

    handler = lambda *a, **kw: http.server.SimpleHTTPRequestHandler(*a, directory=str(site_dir), **kw)
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        results = llms_verify.verify_site(output_root, "docs", base_url)
        # 2 content pages + the llms.txt index -- both are real, verifiable
        # URLs post-deploy, and llms.txt passes the same lightweight checks
        # harmlessly (plain text, no shortcodes, real content).
        assert len(results) == 3
        assert all(r["ok"] for r in results)
    finally:
        server.shutdown()
        thread.join(timeout=5)


def test_cli_main_verifies_against_generic_fixture_repo(tmp_path, monkeypatch):
    """CLI-level portability proof: config.yaml + a real (loopback) base_url,
    no aspose.org dependency anywhere."""
    import http.server
    import threading

    import config_loader
    import llms_generate

    output_dir = tmp_path / "llms-output"
    llms_generate.generate_site(
        FIXTURE_ROOT, output_dir, "docs",
        "content/docs.example.org/en/{family}/{platform}/",
    )
    site_dir = output_dir / "docs"

    handler = lambda *a, **kw: http.server.SimpleHTTPRequestHandler(*a, directory=str(site_dir), **kw)
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        fixture_config = {
            "content_repo": str(FIXTURE_ROOT),
            "knowledge_root": "knowledge",
            "reports_path": "reports",
            "sites": {
                "docs": {
                    "content_path": "content/docs.example.org/en/{family}/{platform}/",
                    "base_url": base_url,
                },
            },
        }
        # IMPORTANT: llms_verify.py does `from config_loader import load_config`,
        # a local name binding at import time -- patching config_loader.load_config
        # does NOT affect it (this bit the first version of this test: it
        # "passed" while actually verifying zero sites, because the real
        # project config.yaml has no base_url set on any site, and
        # `any_verified=False` alone makes main() return 0 -- an empty
        # report file also still gets written, so both original assertions
        # were satisfiable with nothing actually checked). Patch
        # llms_verify's own local name, and assert on real per-site content.
        monkeypatch.setattr(llms_verify, "load_config", lambda: fixture_config)

        report_path = tmp_path / "verify-report.json"
        exit_code = llms_verify.main(["--output", str(output_dir), "--report", str(report_path), "--gate", "100"])
        assert exit_code == 0
        report = json.loads(report_path.read_text(encoding="utf-8"))
        assert report["docs"]["total"] == 3  # 2 pages + llms.txt index, actually fetched over the loopback server
        assert report["docs"]["passed"] == 3
    finally:
        server.shutdown()
        thread.join(timeout=5)


def test_main_skips_sites_with_no_base_url(monkeypatch, capsys, tmp_path):
    import config_loader

    monkeypatch.setattr(config_loader, "load_config", lambda: {
        "sites": {"docs": {"content_path": "content/docs.example.org/en/{family}/{platform}/"}},
    })
    exit_code = llms_verify.main(["--output", str(tmp_path / "out")])
    assert exit_code == 0
    assert "No site has a base_url" in capsys.readouterr().err
