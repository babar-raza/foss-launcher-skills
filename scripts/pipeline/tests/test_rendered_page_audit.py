"""Tests for commands/content/rendered_page_audit.py (MT074 card B14, IVP AC-6).

One seeded defect per check (positive + negative), on synthetic docs-like and
blog-like page structures.  No Hugo, no network: external links use an injected
fetch seam; internal links resolve against a tmp "build dir".
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from commands.content import rendered_page_audit as rpa  # noqa: E402

DOCS_BASE = "https://docs.example.org"
BLOG_BASE = "https://blog.example.org"
DOCS_URL = "/pdf/java/guide/"
BLOG_URL = "/pdf/java/my-post/"


# --------------------------------------------------------------------------- helpers
def make_page(*, title="Guide", desc="A useful guide.", canonical=f"{DOCS_BASE}{DOCS_URL}",
              og=True, body=None, head_extra="", lang="en"):
    if body is None:
        body = "<h1>Guide</h1><p>Intro paragraph.</p>"
    parts = ["<!DOCTYPE html>", f'<html lang="{lang}"><head><meta charset="utf-8">']
    if title is not None:
        parts.append(f"<title>{title}</title>")
    if desc is not None:
        parts.append(f'<meta name="description" content="{desc}">')
    if canonical is not None:
        parts.append(f'<link rel="canonical" href="{canonical}">')
    if og:
        parts.append('<meta property="og:title" content="Guide OG">')
        parts.append('<meta property="og:description" content="Guide OG description">')
    parts.append(head_extra)
    parts.append("</head><body><header><nav><a href=\"/\">Home</a></nav></header><main>")
    parts.append(body)
    parts.append("</main></body></html>")
    return "\n".join(parts)


def make_page_at(url, **kw):
    kw.setdefault("canonical", f"{DOCS_BASE}{url}")
    return make_page(**kw)


def write_build(root: Path, files: dict[str, str]) -> Path:
    for rel, content in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    return root


def checks_of(findings, check):
    return [f for f in findings if f["check"] == check]


def audit(html, url=DOCS_URL, **kw):
    kw.setdefault("site_base_url", DOCS_BASE)
    return rpa.audit_page(html, url=url, **kw)


def PUBLIC(host):
    """Injected resolver: every host is a public address (no DNS in tests)."""
    return ["93.184.216.34"]


class FakeClock:
    def __init__(self):
        self.t = 1000.0
        self.sleeps = []

    def now(self):
        return self.t

    def sleep(self, dt):
        self.sleeps.append(dt)
        self.t += dt


DOCS_BODY = """
<h1>Developer Guide</h1>
<p>Intro with a <a href="/pdf/java/other/">root link</a> and a
<a href="../sibling/#setup">sibling link</a>.</p>
<h2 id="setup">Setup</h2>
<pre><code class="language-java">int a = 1;</code></pre>
<table><thead><tr><th>A</th><th>B</th></tr></thead>
<tbody><tr><td>1</td><td>2</td></tr></tbody></table>
<img src="/img/a.png" alt="Architecture diagram">
<p>See <a href="https://reference.example.org/pdf/java/Document/">the reference</a>.</p>
"""

BLOG_BODY = """
<article>
<header><h1>Release notes for the new feature</h1><time datetime="2026-01-01">Jan 1</time></header>
<p>Lead paragraph about the release, written for readers.</p>
<h2>What changed</h2>
<p>Details follow, with a <a href="https://docs.example.org/pdf/java/">docs link</a>.</p>
<h3>Sample</h3>
<pre><code>run()</code></pre>
<pre><code>stop()</code></pre>
<img src="/images/hero.png" alt="Hero image">
<ul class="tags"><li><a href="/tags/release/">release</a></li></ul>
</article>
"""


@pytest.fixture()
def docs_build(tmp_path):
    return write_build(tmp_path / "public", {
        "pdf/java/guide/index.html": make_page_at("/pdf/java/guide/", body=DOCS_BODY),
        "pdf/java/other/index.html": make_page_at("/pdf/java/other/", title="Other"),
        "pdf/java/sibling/index.html": make_page_at(
            "/pdf/java/sibling/", title="Sib", body='<h1>S</h1><h2 id="setup">Setup</h2>'),
        "img/a.png": "png",
        "index.html": "<html></html>",
        "sitemap.xml": (
            '<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
            f"<url><loc>{DOCS_BASE}/pdf/java/guide/</loc></url>"
            f"<url><loc>{DOCS_BASE}/pdf/java/other/</loc></url>"
            + "".join(f"<url><loc>{DOCS_BASE}/pdf/java/{n}/</loc></url>"
                      for n in ("sibling", "bad", "major", "minor"))
            + "</urlset>"),
    })


# --------------------------------------------------------------------------- clean pages
def test_clean_docs_like_page_has_no_findings(docs_build):
    html = (docs_build / "pdf/java/guide/index.html").read_text(encoding="utf-8")
    md = "# Guide\n\n```java\nint a = 1;\n```\n"
    res = audit(html, build_dir=docs_build, md_source=md,
                sitemap=rpa.load_sitemap_paths(docs_build))
    assert res["findings"] == []
    assert res["checks"]["R3.3"] == "PASS"
    assert res["checks"]["R3.6"] == "PASS"
    assert res["checks"]["R3.9"] == "PASS"
    assert res["checks"]["R3.7"] == "NA"


def test_clean_blog_like_page_has_no_findings(tmp_path):
    build = write_build(tmp_path / "public", {
        "tags/release/index.html": make_page(canonical=f"{BLOG_BASE}/tags/release/"),
        "index.html": "<html></html>",
    })
    html = make_page(canonical=f"{BLOG_BASE}{BLOG_URL}", title="Release notes", body=BLOG_BODY)
    res = rpa.audit_page(html, url=BLOG_URL, build_dir=build, site_base_url=BLOG_BASE,
                         md_source="x\n```\nrun()\n```\n\n~~~\nstop()\n~~~\n")
    assert res["findings"] == []
    assert res["checks"]["R3.3"] == "PASS"


# --------------------------------------------------------------------------- R3.1
@pytest.mark.parametrize("body,expected", [
    ("<p>no heading</p>", 1),
    ("<h1>A</h1><h1>B</h1>", 1),
])
def test_r31_h1_count(body, expected):
    res = audit(make_page(body=body))
    assert len(checks_of(res["findings"], "R3.1")) == expected
    assert res["checks"]["R3.1"] == "FAIL"


def test_r31_heading_skip_flagged_and_descending_ok():
    bad = audit(make_page(body="<h1>A</h1><h2>B</h2><h4>C</h4>"))
    f = checks_of(bad["findings"], "R3.1")
    assert len(f) == 1 and "h2" in f[0]["message"] and "h4" in f[0]["message"]
    ok = audit(make_page(body="<h1>A</h1><h2>B</h2><h3>C</h3><h2>D</h2><h3>E</h3>"))
    assert checks_of(ok["findings"], "R3.1") == []
    # jumping back UP by more than one level is allowed (only downward skips count)
    ok2 = audit(make_page(body="<h1>A</h1><h2>B</h2><h3>C</h3><h4>D</h4><h2>E</h2>"))
    assert checks_of(ok2["findings"], "R3.1") == []


# --------------------------------------------------------------------------- R3.2
@pytest.mark.parametrize("kw,needle", [
    ({"title": None}, "title"),
    ({"title": "  "}, "title"),
    ({"desc": None}, "description"),
    ({"canonical": None}, "canonical"),
    ({"og": False}, "og:title"),
])
def test_r32_missing_head_metadata(kw, needle):
    res = audit(make_page(**kw))
    msgs = " ".join(f["message"] for f in checks_of(res["findings"], "R3.2"))
    assert needle in msgs


def test_r32_empty_description_is_flagged():
    res = audit(make_page(desc=""))
    assert checks_of(res["findings"], "R3.2")


def test_r32_canonical_must_be_absolute_and_match_page_url():
    rel = audit(make_page(canonical="/pdf/java/guide/"))
    assert any("absolute" in f["message"] for f in checks_of(rel["findings"], "R3.2"))
    wrong = audit(make_page(canonical=f"{DOCS_BASE}/pdf/java/elsewhere/"))
    assert any("match" in f["message"] for f in checks_of(wrong["findings"], "R3.2"))
    wrong_host = audit(make_page(canonical="https://other.example.net/pdf/java/guide/"))
    assert any("host" in f["message"] for f in checks_of(wrong_host["findings"], "R3.2-host"))
    ok = audit(make_page(canonical=f"{DOCS_BASE}/pdf/java/guide/index.html"))
    assert checks_of(ok["findings"], "R3.2") == []


# --------------------------------------------------------------------------- R3.3
def test_r33_fence_parity():
    html = make_page(body="<h1>A</h1><pre><code>a</code></pre><pre><code>b</code></pre>")
    md_two = "```\na\n```\n\n```py\nb\n```\n"
    md_three = md_two + "\n~~~\nc\n~~~\n"
    assert audit(html, md_source=md_two)["checks"]["R3.3"] == "PASS"
    res = audit(html, md_source=md_three)
    f = checks_of(res["findings"], "R3.3")
    assert len(f) == 1 and "html=2" in f[0]["evidence"] and "md=3" in f[0]["evidence"]


def test_r33_na_without_md_source():
    html = make_page(body="<h1>A</h1><pre><code>a</code></pre>")
    res = audit(html)
    assert res["checks"]["R3.3"] == "NA"
    assert checks_of(res["findings"], "R3.3") == []


def test_count_markdown_fences_handles_nesting_and_frontmatter():
    md = ("---\ntitle: x\n---\n\n````md\n```inner\nx\n```\n````\n\n"
          "- item\n\n  ```bash\n  ls\n  ```\n\n```\nunclosed fence at EOF\n")
    # outer 4-backtick block (inner fence is content) + indented bash + unclosed = 3
    assert rpa.count_markdown_fences(md) == 3
    assert rpa.count_markdown_fences("no fences here") == 0


def test_html_code_blocks_ignore_pre_without_code_and_line_number_gutter():
    html = make_page(body=(
        "<h1>A</h1><pre>plain preformatted</pre>"
        '<table class="lntable"><tr><td class="lntd"><pre><code><span class="lnt">1</span></code></pre></td>'
        '<td class="lntd"><pre><code>x = 1</code></pre></td></tr></table>'))
    assert audit(html, md_source="```\nx = 1\n```\n")["checks"]["R3.3"] == "PASS"


def test_resolve_md_source_maps_url_to_markdown(tmp_path):
    write_build(tmp_path, {
        "en/pdf/java/guide/index.md": "a",
        "blog/pdf/java/my-post/index.md": "b",
        "pdf/java/flat.md": "c",
        "pdf/java/sec/_index.md": "d",
    })
    assert rpa.resolve_md_source("/pdf/java/guide/", tmp_path).name == "index.md"
    assert rpa.resolve_md_source("/pdf/java/flat/", tmp_path).name == "flat.md"
    assert rpa.resolve_md_source("/pdf/java/sec/", tmp_path).name == "_index.md"
    assert rpa.resolve_md_source("/pdf/java/missing/", tmp_path) is None
    assert rpa.resolve_md_source("/pdf/java/my-post/", tmp_path / "blog").name == "index.md"


# --------------------------------------------------------------------------- R3.4
def test_r34_table_without_header_and_ragged_rows():
    nohead = audit(make_page(body="<h1>A</h1><table><tr><td>1</td><td>2</td></tr></table>"))
    assert any("header" in f["message"] for f in checks_of(nohead["findings"], "R3.4"))
    ragged = audit(make_page(body=(
        "<h1>A</h1><table><thead><tr><th>A</th><th>B</th></tr></thead>"
        "<tbody><tr><td>1</td><td>2</td></tr><tr><td>only</td></tr></tbody></table>")))
    f = checks_of(ragged["findings"], "R3.4")
    assert len(f) == 1 and "column" in f[0]["message"]


def test_r34_colspan_counts_and_th_without_thead_ok():
    ok = audit(make_page(body=(
        "<h1>A</h1><table><tr><th>A</th><th>B</th><th>C</th></tr>"
        '<tr><td colspan="2">wide</td><td>c</td></tr></table>')))
    assert checks_of(ok["findings"], "R3.4") == []


# --------------------------------------------------------------------------- R3.5
def test_r35_img_alt():
    bad = audit(make_page(body='<h1>A</h1><img src="/a.png"><img src="/b.png" alt="  ">'))
    assert len(checks_of(bad["findings"], "R3.5")) == 2
    ok = audit(make_page(body='<h1>A</h1><img src="/a.png" alt="A chart">'
                              '<img src="/d.png" alt="" role="presentation">'))
    assert checks_of(ok["findings"], "R3.5") == []


# --------------------------------------------------------------------------- R3.6
def test_r36_broken_internal_link_and_fragment(docs_build):
    body = ('<h1>A</h1><a href="/pdf/java/missing/">gone</a>'
            '<a href="/pdf/java/sibling/#nope">frag</a>'
            '<a href="#local-missing">local</a><h2 id="here">Here</h2><a href="#here">ok</a>'
            '<a href="/pdf/java/other/">fine</a><a href="mailto:a@b.c">mail</a>')
    res = audit(make_page(body=body), build_dir=docs_build)
    msgs = [f["message"] for f in checks_of(res["findings"], "R3.6")]
    assert len(msgs) == 3, msgs
    assert any("/pdf/java/missing/" in m for m in msgs)
    assert any("#nope" in m or "nope" in m for m in msgs)
    assert any("local-missing" in m for m in msgs)
    sev = {f["severity"] for f in checks_of(res["findings"], "R3.6")}
    assert "blocker" in sev


def test_r36_absolute_same_host_links_are_internal(docs_build):
    body = (f'<h1>A</h1><a href="{DOCS_BASE}/pdf/java/other/">ok</a>'
            f'<a href="{DOCS_BASE}/pdf/java/nowhere/">bad</a>')
    res = audit(make_page(body=body), build_dir=docs_build)
    assert len(checks_of(res["findings"], "R3.6")) == 1


def test_r36_relative_links_resolve_against_page_url(docs_build):
    ok = audit(make_page(body='<h1>A</h1><a href="../other/">x</a><a href="../sibling">y</a>'),
               build_dir=docs_build)
    assert checks_of(ok["findings"], "R3.6") == []


def test_r36_na_without_build_dir():
    res = audit(make_page(body='<h1>A</h1><a href="/x/">x</a>'))
    assert res["checks"]["R3.6"] == "NA"


def test_url_to_file_blocks_path_traversal(docs_build):
    assert rpa.url_to_file(docs_build, "/pdf/java/other/") is not None
    assert rpa.url_to_file(docs_build, "/../../etc/passwd") is None


# --------------------------------------------------------------------------- R3.7
def _ext_body():
    return ('<h1>A</h1><a href="https://ext.example.net/ok">ok</a>'
            '<a href="https://ext.example.net/gone">gone</a>'
            '<a href="https://down.example.net/x">down</a>'
            '<a href="https://allowed.example.net/y">allowed</a>')


def _fetch_factory(calls):
    def fetch(url, timeout):
        calls.append(url)
        if url.endswith("/ok"):
            return 200
        if url.endswith("/gone"):
            return 404
        if "down.example.net" in url:
            raise TimeoutError("timed out")
        return 200
    return fetch


def test_r37_ok_broken_unreachable_and_allowlist(tmp_path):
    calls, clock = [], FakeClock()
    res = audit(make_page(body=_ext_body()), external_links="head",
                allowlist=["allowed.example.net"], fetch=_fetch_factory(calls),
                clock=clock.now, sleep=clock.sleep, cache_dir=tmp_path / "cache", resolve=PUBLIC)
    f = checks_of(res["findings"], "R3.7")
    by_url = {x["evidence"]: x for x in f}
    gone = [x for x in f if "/gone" in x["evidence"]][0]
    down = [x for x in f if "down.example.net" in x["evidence"]][0]
    assert gone["severity"] == "major" and "broken" in gone["message"]
    assert down["severity"] == "minor" and "unreachable" in down["message"]
    assert len(by_url) == 2
    assert not any("allowed.example.net" in c for c in calls)  # allow-list is never fetched
    assert res["checks"]["R3.7"] == "FAIL"
    assert res["external"]["https://ext.example.net/ok"] == "ok"


def test_r37_off_never_fetches():
    calls = []
    res = audit(make_page(body=_ext_body()), fetch=_fetch_factory(calls))
    assert calls == [] and res["checks"]["R3.7"] == "NA"


def test_r37_cache_hit_and_ttl(tmp_path):
    cache, clock = tmp_path / "cache", FakeClock()
    body = '<h1>A</h1><a href="https://ext.example.net/ok">ok</a><a href="https://down.example.net/x">d</a>'
    calls = []
    audit(make_page(body=body), external_links="head", fetch=_fetch_factory(calls),
          clock=clock.now, sleep=clock.sleep, cache_dir=cache, resolve=PUBLIC)
    assert len(calls) == 2
    calls.clear()
    audit(make_page(body=body), external_links="head", fetch=_fetch_factory(calls),
          clock=clock.now, sleep=clock.sleep, cache_dir=cache, resolve=PUBLIC)
    # ok is served from cache; unreachable is never cached so it is retried
    assert calls == ["https://down.example.net/x"]
    calls.clear()
    clock.t += 90000  # beyond default 24h ttl
    audit(make_page(body=body), external_links="head", fetch=_fetch_factory(calls),
          clock=clock.now, sleep=clock.sleep, cache_dir=cache, resolve=PUBLIC)
    assert len(calls) == 2


def test_r37_rate_limit_per_host():
    clock, calls = FakeClock(), []
    body = ('<h1>A</h1><a href="https://same.example.net/1">1</a><a href="https://same.example.net/2">2</a>'
            '<a href="https://other.example.net/3">3</a>')
    audit(make_page(body=body), external_links="head", fetch=_fetch_factory(calls),
          clock=clock.now, sleep=clock.sleep, rate_limit_s=2.0, resolve=PUBLIC)
    assert len(calls) == 3
    assert len(clock.sleeps) == 1 and clock.sleeps[0] == pytest.approx(2.0)


def test_classify_status():
    assert rpa.classify_status(200) == "ok" and rpa.classify_status(301) == "ok"
    assert rpa.classify_status(404) == "broken" and rpa.classify_status(410) == "broken"
    for s in (401, 403, 405, 429, 500, 503):
        assert rpa.classify_status(s) == "unreachable"


# --------------------------------------------------------------------------- R3.8
@pytest.mark.parametrize("leak", [
    "Grounded by CLM-pdf-0a0b35 here.",
    "Claim ERC-pdf-java-2db01116 applies.",
    "(evidence: model_sha 099e70a8)",
    "model_sha: 099e70a8cafe",
    "graded_at: 2026-01-01",
    "evidence:",
    "provenance: skill-generated",
])
def test_r38_metadata_leak_in_visible_body(leak):
    res = audit(make_page(body=f"<h1>A</h1><p>{leak}</p>"))
    f = checks_of(res["findings"], "R3.8")
    assert f and all(x["severity"] == "blocker" for x in f)


@pytest.mark.parametrize("prose", [
    "The provenance of this block is discussed below.",
    "Evidence: we measured this ourselves.",
    "We stamp graded_at somewhere in the pipeline, not on the page.",
    "A sentence that says evidence: inline is ordinary prose.",
    "Tracking model_sha is a topic for another post.",
])
def test_r38_bare_words_and_midsentence_mentions_are_not_leaks(prose):
    res = audit(make_page(body=f"<h1>A</h1><p>{prose}</p>"))
    assert checks_of(res["findings"], "R3.8") == []


@pytest.mark.parametrize("code", [
    "<pre><code>evidence:\n  model_sha: abc1234\n  claims: []</code></pre>",
    "<p>Set <code>model_sha</code> and <code>CLM-abc-1</code> in YAML.</p>",
    "<p>Press <kbd>evidence: x</kbd> now.</p>",
    "<pre><samp>graded_at: 2026-01-01</samp></pre>",
])
def test_r38_code_kbd_samp_are_not_scanned(code):
    res = audit(make_page(body=f"<h1>A</h1>{code}"))
    assert checks_of(res["findings"], "R3.8") == []


def test_r38_evidence_panel_markup():
    res = audit(make_page(body='<h1>A</h1><div class="evidence-panel"><p>x</p></div>'))
    assert any("markup" in f["message"] for f in checks_of(res["findings"], "R3.8"))
    res2 = audit(make_page(body='<h1>A</h1><div data-evidence-claims="1"><p>x</p></div>'))
    assert checks_of(res2["findings"], "R3.8")


def test_r38_hidden_head_and_script_text_is_not_visible_body():
    head = '<script>var x = "CLM-abc-1";</script><style>.x{}/* ERC-zzz-1 */</style>'
    res = audit(make_page(head_extra=head, body="<h1>A</h1><p>clean</p>"))
    assert checks_of(res["findings"], "R3.8") == []


# --------------------------------------------------------------------------- R3.9
def test_r39_sitemap_membership():
    html = make_page(body="<h1>A</h1>")
    assert audit(html, sitemap={"/pdf/java/guide/"})["checks"]["R3.9"] == "PASS"
    res = audit(html, sitemap={"/pdf/java/other/"})
    assert len(checks_of(res["findings"], "R3.9")) == 1
    assert audit(html)["checks"]["R3.9"] == "NA"


def test_load_sitemap_paths_handles_index_and_missing(tmp_path):
    assert rpa.load_sitemap_paths(tmp_path) is None
    write_build(tmp_path, {
        "sitemap.xml": ('<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
                        f"<sitemap><loc>{DOCS_BASE}/en/sitemap.xml</loc></sitemap></sitemapindex>"),
        "en/sitemap.xml": ('<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
                           f"<url><loc>{DOCS_BASE}/pdf/java/guide/</loc></url></urlset>"),
    })
    assert rpa.load_sitemap_paths(tmp_path) == {"/pdf/java/guide/"}


# --------------------------------------------------------------------------- R3.11 / R2.4
@pytest.mark.parametrize("marker", [
    "Example removed: could not be verified.", "TODO finish this", "Lorem ipsum dolor sit amet",
    "FIXME later", "REPLACE_ME", "example REMOVED",
])
def test_r311_placeholder_markers(marker):
    res = audit(make_page(body=f"<h1>A</h1><blockquote><p>{marker}</p></blockquote>"))
    assert checks_of(res["findings"], "R3.11")
    assert res["checks"]["R3.11"] == "FAIL" and res["checks"]["R2.4"] == "FAIL"


def test_r311_todo_in_code_block_is_ignored_but_marker_is_not():
    ok = audit(make_page(body="<h1>A</h1><pre><code>// TODO: tune\nrun();</code></pre>"))
    assert checks_of(ok["findings"], "R3.11") == []
    bad = audit(make_page(body="<h1>A</h1><pre><code>// Example removed\n</code></pre>"))
    assert checks_of(bad["findings"], "R3.11")


def test_r311_negative_words_like_mastodon_not_flagged():
    res = audit(make_page(body="<h1>A</h1><p>Mastodon and todos and fixmes are fine.</p>"))
    assert checks_of(res["findings"], "R3.11") == []


# --------------------------------------------------------------------------- R4.4
def test_r44_cross_subdomain_links():
    bad_en = audit(make_page(body='<h1>A</h1><a href="https://reference.example.org/en/pdf/java/">r</a>'))
    f = checks_of(bad_en["findings"], "R4.4")
    assert len(f) == 1 and "/en/" in f[0]["message"]
    bad_http = audit(make_page(body='<h1>A</h1><a href="http://reference.example.org/pdf/java/">r</a>'))
    assert any("https" in f["message"] for f in checks_of(bad_http["findings"], "R4.4"))
    ok = audit(make_page(body='<h1>A</h1><a href="https://reference.example.org/pdf/java/">r</a>'
                              '<a href="../x/">rel</a>'
                              f'<a href="{DOCS_BASE}/en/same-host/">same</a>'
                              '<a href="https://elsewhere.vendor.io/en/x">other-domain</a>'))
    assert checks_of(ok["findings"], "R4.4") == []


def test_r44_blog_to_docs_en_violation():
    html = make_page(canonical=f"{BLOG_BASE}{BLOG_URL}",
                     body='<h1>P</h1><a href="https://docs.example.org/en/pdf/java/">d</a>')
    res = rpa.audit_page(html, url=BLOG_URL, site_base_url=BLOG_BASE)
    assert len(checks_of(res["findings"], "R4.4")) == 1


# --------------------------------------------------------------------------- R4.1
def test_r41_duplicate_paragraphs():
    para = ("This paragraph repeats verbatim and is considerably longer than the minimum of one "
            "hundred and twenty normalised characters needed.")
    res = audit(make_page(body=f"<h1>A</h1><p>{para}</p><h2>B</h2><p>  {para.upper()} </p>"))
    f = checks_of(res["findings"], "R4.1")
    assert len(f) == 1 and "2" in f[0]["message"]
    short = audit(make_page(body="<h1>A</h1><p>Short dup.</p><p>Short dup.</p>"))
    assert checks_of(short["findings"], "R4.1") == []


# --------------------------------------------------------------------------- R6.5
def test_r65_link_text_and_forms():
    res = audit(make_page(body=('<h1>A</h1><a href="/a/"></a><a href="/b/">click here</a>'
                                '<a href="/c/"><img src="/i.png" alt="logo"></a>'
                                '<a href="/d/" aria-label="Docs"></a><a href="/e/">Real text</a>')))
    f = checks_of(res["findings"], "R6.5")
    assert len(f) == 2
    form = audit(make_page(body='<h1>A</h1><form action="/x"><input name="q"></form>'))
    assert any("form" in f["message"] for f in checks_of(form["findings"], "R6.5"))
    in_nav = audit(make_page(body='<h1>A</h1>', head_extra=''))
    assert checks_of(in_nav["findings"], "R6.5") == []
    search = make_page(body='<h1>A</h1>').replace(
        "<nav>", '<nav><form action="/search"><input name="q"></form>')
    assert checks_of(audit(search)["findings"], "R6.5") == []


# --------------------------------------------------------------------------- canary rendition
def test_canary_style_page_catches_every_seeded_defect(docs_build):
    body = """
<h1>HTML Conversion</h1>
<h2>HtmlToPdfConverter</h2>
<p>HtmlToPdfConverter converts HTML content into a PDF document. CssContext provides CSS context for rendering inline and linked stylesheets during the conversion.</p>
<h2>See Also</h2>
<p>To export a workbook call Document.exportToXlsx on the loaded document.</p>
<p>See also the <a href="/pdf/java/developer-guide/spreadsheet-conversion-guide-does-not-exist/">spreadsheet conversion guide</a>.</p>
<pre><code class="language-java">try (Document doc = new Document("in.pdf")) { doc.save(out); }</code></pre>
<h1>Another Top-Level Heading</h1>
<p>Extra text.</p>
<p><em>Grounded by CLM-pdf-0a0b35 and ERC-pdf-java-2db01116 (evidence: model_sha 099e70a8).</em></p>
<blockquote><p>Example removed: could not be verified.</p></blockquote>
<p>HtmlToPdfConverter converts HTML content into a PDF document. CssContext provides CSS context for rendering inline and linked stylesheets during the conversion.</p>
<p>More in the <a href="https://reference.example.org/en/pdf/java/document/">API reference</a>.</p>
"""
    md = "```java\na\n```\n\n```java\nb\n```\n"
    res = audit(make_page(body=body), build_dir=docs_build, md_source=md)
    hit = {f["check"] for f in res["findings"]}
    assert {"R3.1", "R3.6", "R3.8", "R3.11", "R4.1", "R4.4", "R3.3"} <= hit
    sev = {f["check"]: f["severity"] for f in res["findings"]}
    assert sev["R3.8"] == "blocker" and sev["R3.11"] == "blocker"


# --------------------------------------------------------------------------- audit_build / determinism
def test_audit_build_missing_page_and_url_and_file_inputs(docs_build):
    rep = rpa.audit_build(docs_build, [DOCS_URL, "/pdf/java/nope/",
                                       str(docs_build / "pdf/java/other/index.html")],
                          site_base_url=DOCS_BASE)
    pages = {p["page"]: p for p in rep["pages"]}
    assert set(pages) == {DOCS_URL, "/pdf/java/nope/", "/pdf/java/other/"}
    assert any(f["check"] == "PAGE" and f["severity"] == "blocker" for f in pages["/pdf/java/nope/"]["findings"])
    assert rep["summary"]["pages"] == 3


def test_audit_build_is_deterministic_and_order_independent(docs_build):
    kw = dict(site_base_url=DOCS_BASE)
    pages = [DOCS_URL, "/pdf/java/other/", "/pdf/java/sibling/"]
    a = rpa.audit_build(docs_build, pages, **kw)
    b = rpa.audit_build(docs_build, list(reversed(pages)), **kw)
    c = rpa.audit_build(docs_build, pages, **kw)
    ja, jb, jc = (json.dumps(x, sort_keys=True) for x in (a, b, c))
    assert ja == jb == jc


def test_audit_build_md_source_root(docs_build, tmp_path):
    src = write_build(tmp_path / "content", {"pdf/java/guide/index.md": "```\na\n```\n\n```\nb\n```\n"})
    rep = rpa.audit_build(docs_build, [DOCS_URL], md_source_root=src, site_base_url=DOCS_BASE)
    page = rep["pages"][0]
    assert page["checks"]["R3.3"] == "FAIL"  # html has 1 block, md has 2


def test_summary_counts(docs_build):
    html = make_page_at("/pdf/java/bad/", body="<h1>A</h1><h1>B</h1><p>CLM-aaa-1</p>")
    write_build(docs_build, {"pdf/java/bad/index.html": html})
    rep = rpa.audit_build(docs_build, ["/pdf/java/bad/"], site_base_url=DOCS_BASE)
    s = rep["summary"]
    assert s["blocker"] >= 1 and s["major"] >= 1
    assert s["findings"] == s["blocker"] + s["major"] + s["minor"] + s["info"] == len(rep["findings"])
    assert s["by_check"]["R3.8"] >= 1


# --------------------------------------------------------------------------- CLI
def _cli(args, capsys):
    code = rpa.main(args)
    return code, capsys.readouterr().out


def test_cli_exit_codes_per_fail_on(docs_build, capsys):
    write_build(docs_build, {"pdf/java/bad/index.html": make_page_at("/pdf/java/bad/", body="<h1>A</h1><p>CLM-aaa-1</p>"),
                             "pdf/java/major/index.html": make_page_at("/pdf/java/major/", body="<h1>A</h1><h1>B</h1>"),
                             "pdf/java/minor/index.html": make_page_at("/pdf/java/minor/", body='<h1>A</h1><a href="/pdf/java/other/">click here</a>')})
    base = ["--build-dir", str(docs_build), "--site-base-url", DOCS_BASE]
    assert _cli(base + ["--pages", "/pdf/java/bad/"], capsys)[0] == 1
    assert _cli(base + ["--pages", "/pdf/java/major/"], capsys)[0] == 1
    assert _cli(base + ["--pages", "/pdf/java/major/", "--fail-on", "blocker"], capsys)[0] == 0
    assert _cli(base + ["--pages", "/pdf/java/bad/", "--fail-on", "none"], capsys)[0] == 0
    assert _cli(base + ["--pages", "/pdf/java/minor/"], capsys)[0] == 0
    code, out = _cli(base + ["--pages", "/pdf/java/other/", "--fail-on", "major"], capsys)
    assert code == 0 and json.loads(out)["summary"]["findings"] == 0


def test_cli_pages_file_json_out_and_md_format(docs_build, tmp_path, capsys):
    write_build(docs_build, {"pdf/java/bad/index.html": make_page_at("/pdf/java/bad/", body="<h1>A</h1><p>CLM-aaa-1</p>")})
    listing = tmp_path / "pages.txt"
    listing.write_text("# comment\n/pdf/java/bad/\n\n/pdf/java/other/\n", encoding="utf-8")
    out_json = tmp_path / "out" / "report.json"
    code, out = _cli(["--build-dir", str(docs_build), "--pages-file", str(listing),
                      "--json-out", str(out_json), "--format", "md", "--site-base-url", DOCS_BASE], capsys)
    assert code == 1
    assert "R3.8" in out and out.lstrip().startswith("#")
    data = json.loads(out_json.read_text(encoding="utf-8"))
    assert data["summary"]["pages"] == 2


def test_cli_requires_pages_and_valid_build_dir(tmp_path, capsys):
    with pytest.raises(SystemExit) as e:
        rpa.main(["--build-dir", str(tmp_path)])
    assert e.value.code == 2
    with pytest.raises(SystemExit) as e2:
        rpa.main(["--build-dir", str(tmp_path / "nope"), "--pages", "/x/"])
    assert e2.value.code == 2


def test_cli_never_touches_network_by_default(docs_build, capsys, monkeypatch):
    import urllib.request

    def boom(*a, **k):
        raise AssertionError("network used")
    monkeypatch.setattr(urllib.request, "urlopen", boom)
    code, _ = _cli(["--build-dir", str(docs_build), "--pages", DOCS_URL, "--site-base-url", DOCS_BASE], capsys)
    assert code == 0


# --------------------------------------------------------------------------- minified HTML (omitted end tags)
def test_minified_html_with_omitted_end_tags_parses_correctly():
    para = ("Repeated minified paragraph that is long enough to be detected as a duplicate within one page, "
            "written with no closing tags at all.")
    body = (f"<h1>A<p>{para}<p>{para}"
            "<ul><li>one<li>two</ul>"
            "<table><thead><tr><th>A<th>B<tbody><tr><td>1<td>2<tr><td>3<td>4</table>")
    res = audit(make_page(body=body))
    assert len(checks_of(res["findings"], "R4.1")) == 1
    assert checks_of(res["findings"], "R3.4") == []
    assert checks_of(res["findings"], "R3.1") == []


# =========================================================================== review R4 fixes
# --------------------------------------------------------------------------- R4-4 host check needs a base URL
def test_r32_host_check_requires_site_base_url():
    evil = "https://evil.example.net/pdf/java/guide/"
    html = make_page(canonical=evil)
    with_base = rpa.audit_page(html, url=DOCS_URL, site_base_url=DOCS_BASE)
    assert [f for f in with_base["findings"] if f["check"] == "R3.2-host"]
    assert with_base["checks"]["R3.2-host"] == "FAIL" and with_base["checks"]["R3.2"] == "FAIL"
    without = rpa.audit_page(html, url=DOCS_URL)
    assert not [f for f in without["findings"] if f["check"] == "R3.2-host"]
    assert without["checks"]["R3.2-host"] == "NA"  # never PASS without a base URL
    assert "site-base-url" in without["na_reasons"]["R3.2-host"]
    # the other R3.2 sub-checks still run
    no_title = rpa.audit_page(make_page(title=None, canonical=evil), url=DOCS_URL)
    assert any("title" in f["message"] for f in checks_of(no_title["findings"], "R3.2"))
    ok = audit(make_page())
    assert ok["checks"]["R3.2-host"] == "PASS"


# --------------------------------------------------------------------------- R4-5 incomplete sitemap index
SM_NS = 'xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"'


@pytest.fixture()
def split_build(tmp_path):
    return write_build(tmp_path / "public", {
        "index.html": "<html></html>",
        "pdf/net/guide/index.html": make_page_at(
            "/pdf/net/guide/",
            body='<h1>G</h1><a href="/pdf/java/Foo/">java side</a><a href="/pdf/net/missing/">gone</a>'),
        "sitemap.xml": (f"<sitemapindex {SM_NS}>"
                        f"<sitemap><loc>{DOCS_BASE}/pdf/net/sitemap.xml</loc></sitemap>"
                        f"<sitemap><loc>{DOCS_BASE}/pdf/java/sitemap.xml</loc></sitemap></sitemapindex>"),
        "pdf/net/sitemap.xml": (f"<urlset {SM_NS}><url><loc>{DOCS_BASE}/pdf/net/guide/</loc></url></urlset>"),
    })


def test_incomplete_sitemap_index_is_not_an_empty_sitemap(split_build):
    assert rpa.load_sitemap_paths(split_build) is None
    info = rpa.load_sitemap_info(split_build)
    assert info["missing"] == [f"{DOCS_BASE}/pdf/java/sitemap.xml"]
    assert info["paths"] == {"/pdf/net/guide/"}


def test_split_deploy_build_degrades_r39_and_cross_partition_links(split_build):
    rep = rpa.audit_build(split_build, ["/pdf/net/guide/"], site_base_url=DOCS_BASE)
    page = rep["pages"][0]
    assert page["checks"]["R3.9"] == "NA"
    assert "pdf/java/sitemap.xml" in page["na_reasons"]["R3.9"]
    assert not checks_of(page["findings"], "R3.9")
    warn = checks_of(page["findings"], "PAGE")
    assert len(warn) == 1 and warn[0]["severity"] == "minor"
    assert "sitemap index child" in warn[0]["message"] and "missing" in warn[0]["message"]
    assert "pdf/java/sitemap.xml" in warn[0]["evidence"]
    # built partition: a genuinely broken link is still a blocker; an unbuilt partition is not
    r36 = checks_of(page["findings"], "R3.6")
    assert len(r36) == 1 and "/pdf/net/missing/" in r36[0]["message"] and r36[0]["severity"] == "blocker"
    assert [u["href"] for u in page["unverified_links"]] == ["/pdf/java/Foo/"]


def test_complete_sitemap_index_still_flags_missing_page_and_broken_cross_links(split_build):
    write_build(split_build, {"pdf/java/sitemap.xml": f"<urlset {SM_NS}></urlset>"})
    rep = rpa.audit_build(split_build, ["/pdf/net/guide/"], site_base_url=DOCS_BASE)
    page = rep["pages"][0]
    assert page["checks"]["R3.9"] == "PASS" and not checks_of(page["findings"], "PAGE")
    assert len(checks_of(page["findings"], "R3.6")) == 2  # both targets absent from a complete build
    assert page["unverified_links"] == []


# --------------------------------------------------------------------------- R4-6a dotted namespace slugs
def test_norm_path_uses_known_file_extensions_not_any_dot():
    assert rpa.norm_path("/pdf/net/aspose.pdf.facades") == "/pdf/net/aspose.pdf.facades/"
    assert rpa.norm_path("/pdf/net/Aspose.Pdf.Facades/") == "/pdf/net/Aspose.Pdf.Facades/"
    assert rpa.norm_path("/pdf/net/aspose.pdf.facades/index.html") == "/pdf/net/aspose.pdf.facades/"
    for f in ("/sitemap.xml", "/img/a.PNG", "/robots.txt", "/a/b.json", "/s/app.css", "/s/app.js", "/d/x.pdf",
              "/i/x.svg", "/i/x.ico", "/p/page.html"):
        assert rpa.norm_path(f) == f


def test_dotted_namespace_page_has_no_false_canonical_or_sitemap_finding():
    url = "/pdf/net/aspose.pdf.facades"
    html = make_page_at(url + "/", body="<h1>Facades</h1>")
    res = rpa.audit_page(html, url=url, site_base_url=DOCS_BASE, sitemap={"/pdf/net/aspose.pdf.facades/"})
    assert checks_of(res["findings"], "R3.2") == [] and checks_of(res["findings"], "R3.9") == []
    assert res["page"] == "/pdf/net/aspose.pdf.facades/"


# --------------------------------------------------------------------------- R4-6c R3.3 languages / direction
def test_markdown_fence_languages():
    md = "```java\na\n```\n\n```\nb\n```\n\n~~~ Mermaid\nc\n~~~\n"
    assert rpa.markdown_fence_languages(md) == ["java", "", "mermaid"]
    assert rpa.count_markdown_fences(md) == 3


def test_r33_more_html_blocks_than_markdown_fences_is_flagged():
    html = make_page(body="<h1>A</h1>" + "<pre><code>x</code></pre>" * 3)
    res = audit(html, md_source="```\na\n```\n\n```\nb\n```\n")
    f = checks_of(res["findings"], "R3.3")
    assert len(f) == 1 and f[0]["severity"] == "major"
    assert "html=3" in f[0]["evidence"] and "md=2" in f[0]["evidence"]


def test_r33_fewer_html_blocks_than_markdown_fences_is_flagged():
    html = make_page(body="<h1>A</h1><pre><code>x</code></pre>")
    res = audit(html, md_source="```\na\n```\n\n```\nb\n```\n")
    assert len(checks_of(res["findings"], "R3.3")) == 1


def test_r33_tolerates_non_pre_languages_and_reports_info():
    html = make_page(body='<h1>A</h1><pre><code class="language-java">x</code></pre>'
                          '<pre class="mermaid">graph TD</pre>')
    md = "```java\nx\n```\n\n```mermaid\ngraph TD\n```\n"
    res = audit(html, md_source=md)
    f = checks_of(res["findings"], "R3.3")
    assert [x["severity"] for x in f] == ["info"] and "mermaid" in f[0]["message"]
    assert res["checks"]["R3.3"] == "PASS"
    # mermaid rendered as an ordinary code block is accepted too
    html2 = make_page(body="<h1>A</h1>" + "<pre><code>x</code></pre>" * 2)
    assert audit(html2, md_source=md)["checks"]["R3.3"] == "PASS"


def test_r33_tolerated_language_set_is_configurable():
    html = make_page(body='<h1>A</h1><pre><code>x</code></pre><div class="diagram">g</div>')
    md = "```x\nx\n```\n\n```diagram\ng\n```\n"
    assert audit(html, md_source=md)["checks"]["R3.3"] == "FAIL"
    ok = audit(html, md_source=md, non_pre_fence_languages={"diagram"})
    assert ok["checks"]["R3.3"] == "PASS"
    no_tolerance = audit(make_page(body='<h1>A</h1><pre class="mermaid">g</pre>'),
                         md_source="```mermaid\ng\n```\n", non_pre_fence_languages=set())
    assert no_tolerance["checks"]["R3.3"] == "FAIL"


def test_info_findings_do_not_affect_exit_code_and_are_counted(tmp_path):
    build = write_build(tmp_path / "public", {
        "pdf/java/guide/index.html": make_page_at(
            "/pdf/java/guide/", body='<h1>A</h1><pre class="mermaid">g</pre>'),
        "index.html": "<html></html>"})
    src = write_build(tmp_path / "content", {"pdf/java/guide/index.md": "```mermaid\ng\n```\n"})
    rep = rpa.audit_build(build, [DOCS_URL], md_source_root=src, site_base_url=DOCS_BASE)
    assert rep["summary"]["info"] == 1 and rep["summary"]["blocker"] == 0
    assert rpa.exit_code_for(rep, "major") == 0
    code = rpa.main(["--build-dir", str(build), "--pages", DOCS_URL, "--md-source-root", str(src),
                     "--site-base-url", DOCS_BASE, "--non-pre-fence-languages", "mermaid,plantuml"])
    assert code == 0


# --------------------------------------------------------------------------- R4-7 SSRF safety
BLOCKED_IPS = ["169.254.169.254", "127.0.0.1", "127.5.5.5", "10.1.2.3", "172.16.0.9", "172.31.255.1",
               "192.168.1.1", "::1", "fc00::1", "fd12::5", "fe80::1", "0.0.0.0", "::ffff:127.0.0.1"]


def _checker(fetch, resolve=PUBLIC, **kw):
    kw.setdefault("rate_limit_s", 0.0)  # never really sleep in tests
    return rpa.ExternalLinkChecker(fetch=fetch, resolve=resolve, **kw)


@pytest.mark.parametrize("ip", BLOCKED_IPS)
def test_ssrf_literal_private_ip_is_refused_without_connecting(ip):
    calls = []
    host = f"[{ip}]" if ":" in ip else ip
    chk = _checker(_fetch_factory(calls))
    url = f"http://{host}/latest/meta-data/"
    assert chk.check(url) == "unreachable"
    assert calls == [] and "blocked" in chk.reason(url)


@pytest.mark.parametrize("ip", BLOCKED_IPS)
def test_ssrf_hostname_resolving_to_private_ip_is_refused(ip):
    calls = []
    chk = _checker(_fetch_factory(calls), resolve=lambda h: [ip])
    assert chk.check("https://innocent.example.net/x") == "unreachable"
    assert calls == []


def test_ssrf_mixed_resolution_and_resolution_failure():
    calls = []
    chk = _checker(_fetch_factory(calls), resolve=lambda h: ["93.184.216.34", "10.0.0.1"])
    assert chk.check("https://rebind.example.net/ok") == "unreachable" and calls == []

    def boom(host):
        raise OSError("no such host")
    chk2 = _checker(_fetch_factory(calls), resolve=boom)
    assert chk2.check("https://nx.example.net/ok") == "unreachable" and calls == []
    chk3 = _checker(_fetch_factory(calls), resolve=lambda h: [])
    assert chk3.check("https://empty.example.net/ok") == "unreachable"


def test_ssrf_public_host_is_checked_and_non_http_scheme_refused():
    calls = []
    chk = _checker(_fetch_factory(calls))
    assert chk.check("https://ext.example.net/ok") == "ok" and calls == ["https://ext.example.net/ok"]
    assert chk.check("ftp://ext.example.net/file") == "unreachable"
    assert len(calls) == 1


def _redirect_fetch(table, calls):
    def fetch(url, timeout):
        calls.append(url)
        return table[url]
    return fetch


def test_ssrf_redirect_hops_are_revalidated():
    calls = []
    table = {"https://a.example.net/x": (302, "http://169.254.169.254/latest/meta-data/")}
    chk = _checker(_redirect_fetch(table, calls))
    assert chk.check("https://a.example.net/x") == "unreachable"
    assert calls == ["https://a.example.net/x"]  # the metadata address was never fetched
    assert "blocked" in chk.reason("https://a.example.net/x")

    calls2 = []
    table2 = {"https://a.example.net/x": (301, "https://b.example.net/y"), "https://b.example.net/y": (200, None)}
    seen = []

    def resolve(host):
        seen.append(host)
        return ["10.0.0.9"] if host == "b.example.net" else ["93.184.216.34"]
    chk2 = _checker(_redirect_fetch(table2, calls2), resolve=resolve)
    assert chk2.check("https://a.example.net/x") == "unreachable"
    assert calls2 == ["https://a.example.net/x"] and "b.example.net" in seen


def test_redirects_to_public_hosts_are_followed_relative_and_absolute():
    calls = []
    table = {"https://a.example.net/x": (301, "/y"), "https://a.example.net/y": (302, "https://b.example.net/z"),
             "https://b.example.net/z": (200, None)}
    chk = _checker(_redirect_fetch(table, calls))
    assert chk.check("https://a.example.net/x") == "ok"
    assert calls == ["https://a.example.net/x", "https://a.example.net/y", "https://b.example.net/z"]
    table404 = {"https://a.example.net/x": (301, "https://b.example.net/gone"),
                "https://b.example.net/gone": (404, None)}
    assert _checker(_redirect_fetch(table404, [])).check("https://a.example.net/x") == "broken"


def test_ssrf_non_http_redirect_and_redirect_cap():
    calls = []
    table = {"https://a.example.net/x": (302, "ftp://files.example.net/secret")}
    chk = _checker(_redirect_fetch(table, calls))
    assert chk.check("https://a.example.net/x") == "unreachable" and calls == ["https://a.example.net/x"]
    assert "scheme" in chk.reason("https://a.example.net/x")
    loop = {"https://a.example.net/x": (302, "https://a.example.net/x")}
    calls2 = []
    chk2 = _checker(_redirect_fetch(loop, calls2), max_redirects=3)
    assert chk2.check("https://a.example.net/x") == "unreachable"
    assert len(calls2) == 4 and "redirect" in chk2.reason("https://a.example.net/x")


def test_ssrf_literal_public_ip_needs_no_dns():
    calls = []
    chk = rpa.ExternalLinkChecker(fetch=_fetch_factory(calls))  # default resolver, never invoked for literals
    assert chk.check("https://93.184.216.34/ok") == "ok" and calls


def test_r37_blocked_target_reports_unreachable_with_reason_in_audit():
    body = '<h1>A</h1><a href="http://169.254.169.254/latest/">meta</a>'
    calls = []
    res = audit(make_page(body=body), external_links="head", fetch=_fetch_factory(calls), resolve=PUBLIC)
    f = checks_of(res["findings"], "R3.7")
    assert calls == [] and len(f) == 1 and f[0]["severity"] == "minor" and "blocked" in f[0]["message"]


def test_allowlist_matches_parsed_scheme_and_host_not_string_prefix():
    chk = _checker(_fetch_factory([]), allowlist=["https://github.com", "docs.example.org",
                                                  "https://x.org/docs/", ".dotted.example"])
    ok = ["https://github.com/a/b", "https://api.github.com/a", "https://GITHUB.com/",
          "https://docs.example.org/x", "http://docs.example.org/x", "https://x.org/docs/a",
          "https://sub.dotted.example/"]
    bad = ["https://github.com.evil/", "https://evilgithub.com/", "http://github.com/",
           "https://github.com@evil.com/", "https://evil.com/?u=https://github.com",
           "https://x.org/docsevil", "https://x.org/other", "https://notdocs.example.org.evil/"]
    assert all(chk.is_allowed(u) for u in ok)
    assert not any(chk.is_allowed(u) for u in bad)


def test_allowlisted_urls_are_never_fetched_even_if_private():
    calls = []
    chk = _checker(_fetch_factory(calls), allowlist=["intranet.example.net"], resolve=lambda h: ["10.0.0.1"])
    assert chk.check("https://intranet.example.net/x") == "allowlisted" and calls == []


# --------------------------------------------------------------------------- mutant killers
def test_url_to_file_refuses_real_files_outside_build_dir(tmp_path):
    build = write_build(tmp_path / "public", {"index.html": "<html></html>"})
    secret = tmp_path / "secret.txt"
    secret.write_text("top secret", encoding="utf-8")
    assert secret.is_file()
    assert rpa.url_to_file(build, "/../secret.txt") is None
    assert rpa.url_to_file(build, "/a/../../secret.txt") is None
    assert rpa.url_to_file(build, "/%2e%2e/secret.txt") is None
    assert rpa.url_to_file(build, "/" + secret.as_posix()) is None  # absolute target (drive path on Windows)
    assert rpa.url_to_file(build, "/") is not None


def test_internal_links_to_outside_files_are_broken_not_resolved(tmp_path):
    build = write_build(tmp_path / "public", {"index.html": "<html></html>"})
    secret = tmp_path / "secret.txt"
    secret.write_text("top secret", encoding="utf-8")
    body = f'<h1>A</h1><a href="/{secret.as_posix()}">abs</a><a href="/../secret.txt">dots</a>'
    res = audit(make_page(body=body), build_dir=build)
    f = checks_of(res["findings"], "R3.6")
    assert len(f) == 2 and all(x["severity"] == "blocker" for x in f)


def test_unreachable_results_are_never_written_to_the_cache(tmp_path):
    cache, clock, calls = tmp_path / "cache", FakeClock(), []
    chk = _checker(_fetch_factory(calls), cache_dir=cache, clock=clock.now, sleep=clock.sleep)
    assert chk.check("https://down.example.net/x") == "unreachable"
    assert chk.check("https://ext.example.net/ok") == "ok"
    assert chk.check("https://ext.example.net/gone") == "broken"
    files = [f.read_text(encoding="utf-8") for f in cache.glob("*.json")]
    assert len(files) == 2 and not any("unreachable" in t for t in files)
    # a transient failure is retried by a fresh checker once the host recovers
    chk2 = _checker(lambda u, t: 200, cache_dir=cache, clock=clock.now, sleep=clock.sleep)
    assert chk2.check("https://down.example.net/x") == "ok"


def test_blocked_results_are_not_cached_either(tmp_path):
    cache = tmp_path / "cache"
    chk = _checker(_fetch_factory([]), resolve=lambda h: ["10.0.0.1"], cache_dir=cache)
    assert chk.check("https://x.example.net/a") == "unreachable"
    assert not cache.exists() or not list(cache.glob("*.json"))
