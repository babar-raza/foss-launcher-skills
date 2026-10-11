#!/usr/bin/env python3
"""Deterministic rendered-HTML audit: the machine companion of the IVP panel.

Parses an already-built Hugo output directory (never runs Hugo) with the
stdlib ``html.parser`` and emits findings whose ``check`` ids match the
Independent Verification Panel rubric (R3.x / R4.x / R6.5 / R2.4).  It FEEDS
human-style reviewers; it never replaces them.

Checks implemented (see ``CHECKS``):
  R3.1  exactly one <h1>; heading level never skips downward by >1
  R3.2  <title>, meta description, canonical (absolute, matches page URL),
        og:title / og:description present and non-empty
  R3.3  <pre><code> block count == fenced code blocks in the Markdown source
        (NA unless the page maps to a .md under --md-source-root)
  R3.4  tables have <thead>/<th> and consistent column counts
  R3.5  every <img> has a non-empty alt
  R3.6  internal links resolve to a file in the build dir; fragments exist
  R3.7  external links via HEAD (opt-in, cached, rate limited, allow-list)
  R3.8  no internal metadata visible (CLM-/ERC- ids, evidence:, model_sha,
        graded_*, provenance; evidence-panel markup)
  R3.9  page is listed in the build's sitemap.xml (NA when absent)
  R3.11 / R2.4  no placeholder markers
  R4.1  paragraphs of >=120 normalised chars repeated within one page
  R4.4  cross-subdomain links are absolute https:// without /en/
  R6.5  accessibility basics: link text, forms

Library: ``audit_page(html, *, url, ...)`` and ``audit_build(build_dir, pages,
...)`` with injectable ``fetch`` / ``clock`` / ``sleep`` / ``sitemap`` seams.

CLI:
  rendered_page_audit.py --build-dir DIR --pages PATH_OR_URL... [--pages-file F]
      [--md-source-root DIR] [--site-base-url URL] [--external-links {off,head}]
      [--external-allowlist FILE] [--cache-dir DIR] [--json-out PATH]
      [--format {json,md}] [--fail-on {blocker,major,none}]

The network is never touched unless ``--external-links head`` is given.
"""
from __future__ import annotations

import argparse
import bisect
import hashlib
import ipaddress
import json
import re
import socket
import sys
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path
from typing import Callable, Collection, Iterable, Optional
from urllib.parse import unquote, urljoin, urlsplit

_PIPELINE_ROOT = Path(__file__).resolve().parents[2]
if str(_PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_ROOT))

SCHEMA = "rendered_page_audit/1"
SEVERITIES = ("blocker", "major", "minor", "info")  # only blocker/major gate the exit code
_SEV_RANK = {s: i for i, s in enumerate(SEVERITIES)}
CHECKS = ("R3.1", "R3.2", "R3.2-host", "R3.3", "R3.4", "R3.5", "R3.6", "R3.7", "R3.8", "R3.9",
          "R3.11", "R2.4", "R4.1", "R4.4", "R6.5")
_CHECK_ORDER = {c: i for i, c in enumerate(("PAGE",) + CHECKS)}

VOID = frozenset("area base br col embed hr img input link meta param source track wbr".split())
SKIP_TEXT = frozenset(("script", "style", "template", "noscript"))
INLINE = frozenset("a span em strong b i code small sub sup abbr kbd mark s u cite q time del ins font".split())
BLOCK = frozenset(
    "address article aside blockquote body dd details div dl dt fieldset figcaption figure footer form "
    "h1 h2 h3 h4 h5 h6 header hr li main nav ol p pre section table tbody td tfoot th thead tr ul br".split())
P_CLOSERS = frozenset(
    "address article aside blockquote details div dl fieldset figcaption figure footer form h1 h2 h3 h4 h5 h6 "
    "header hr main nav ol p pre section table ul".split())
HEADINGS = {f"h{i}": i for i in range(1, 7)}
SECTION_END = {"ul": {"li"}, "ol": {"li"}}

GENERIC_LINK_TEXT = frozenset(("click here", "here", "this link", "click"))
DUP_MIN_CHARS = 120

_DATA_ATTR = re.compile(r"^data-(evidence|claim|erc|clm|provenance|model-sha)", re.I)

# Extensions that make the last URL segment a file (everything else is a Hugo pretty-URL
# directory, so dotted namespace slugs such as /pdf/net/aspose.pdf.facades get a trailing '/').
KNOWN_FILE_EXTENSIONS = frozenset(
    "html htm xml txt json css js mjs map png jpg jpeg gif svg ico webp avif pdf zip gz csv rss atom "
    "woff woff2 ttf otf eot mp4 webm mp3 wasm yaml yml md".split())

# Fence languages that Hugo/themes render without a <pre><code> block (configurable).
DEFAULT_NON_PRE_FENCE_LANGUAGES = frozenset(
    ("mermaid", "math", "katex", "latex", "plantuml", "graphviz", "dot", "flowchart", "sequence"))

# Internal-metadata SHAPES (not bare words).  Scanned only outside <pre>/<code>/<kbd>/<samp>.
# (label, regex, flags, severity)
LEAK_PATTERNS = (
    ("CLM- id", r"\bCLM-[A-Za-z0-9-]+", 0, "blocker"),
    ("ERC- id", r"\bERC-[A-Za-z0-9-]+", 0, "blocker"),
    ("model_sha value", r"\bmodel_sha\b[\s:=]+[0-9a-f]{7,40}\b", 0, "blocker"),
    ("frontmatter key line",
     r"^[ \t]*(?:evidence|model_sha|model_version|graded_at|graded_content_hash|grade_reasons|provenance|"
     r"content_origin|last_mechanism|auto_updatable|content_hash)[ \t]*:", re.M, "blocker"),
)
CODE_TAGS = frozenset(("pre", "code", "kbd", "samp"))
# (label, regex, flags, prose_only)
PLACEHOLDER_PATTERNS = (
    ("Example removed", r"example\s+removed", re.I, False),
    ("lorem ipsum", r"lorem\s+ipsum", re.I, False),
    ("REPLACE_ME", r"REPLACE_ME", 0, False),
    ("TODO", r"\bTODO\b", 0, True),
    ("FIXME", r"\bFIXME\b", 0, True),
)


# --------------------------------------------------------------------------- url helpers
def norm_path(value: str) -> str:
    """Normalise a URL or path to a comparable page path ('/a/b/' form)."""
    p = unquote(urlsplit(value).path)
    p = re.sub(r"/{2,}", "/", "/" + p.lstrip("/"))
    if p.endswith("/index.html"):
        p = p[: -len("index.html")]
    last = p.rsplit("/", 1)[-1]
    ext = last.rsplit(".", 1)[-1].lower() if "." in last else ""
    if last and ext not in KNOWN_FILE_EXTENSIONS:
        p += "/"
    return p


def url_to_file(build_dir: Path, path: str) -> Optional[Path]:
    """Map a URL path to a file in the build dir (index.html semantics)."""
    p = unquote(urlsplit(path).path)
    rel = p.lstrip("/")
    root = Path(build_dir).resolve()
    if rel == "" or p.endswith("/"):
        cands = [root / rel / "index.html"]
    else:
        cands = [root / rel, root / rel / "index.html"]
    for c in cands:
        try:
            r = c.resolve()
        except OSError:
            continue
        if r != root and root not in r.parents:
            continue  # path traversal outside the build dir
        if r.is_file():
            return r
    return None


def _sld(host: str) -> str:
    labels = [x for x in host.lower().split(".") if x]
    return labels[-2] if len(labels) >= 2 else (labels[0] if labels else "")


def _host(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    h = urlsplit(value).hostname
    return h.lower() if h else None


# --------------------------------------------------------------------------- markdown helpers
def count_markdown_fences(md: str) -> int:
    """Count fenced code blocks (``` / ~~~, nesting by fence length, unclosed counts)."""
    return len(markdown_fence_languages(md))


def markdown_fence_languages(md: str) -> list[str]:
    """Info-string language (lower-case, '' when absent) of each fenced block, in document order."""
    lines = md.replace("\r\n", "\n").split("\n")
    if lines and lines[0].strip() in ("---", "+++"):
        delim = lines[0].strip()
        for i in range(1, len(lines)):
            if lines[i].strip() == delim:
                lines = lines[i + 1:]
                break
    open_char, open_len = None, 0
    langs: list[str] = []
    for line in lines:
        m = re.match(r"^\s*(`{3,}|~{3,})(.*)$", line)
        if open_char is None:
            if not m:
                continue
            fence, info = m.group(1), m.group(2)
            if fence[0] == "`" and "`" in info:
                continue  # inline code span, not a fence
            open_char, open_len = fence[0], len(fence)
            words = re.split(r"[\s{]", info.strip(), maxsplit=1)
            langs.append(words[0].lower())
        elif m and m.group(1)[0] == open_char and len(m.group(1)) >= open_len and not m.group(2).strip():
            open_char = None
    return langs


def resolve_md_source(url_path: str, root: Path) -> Optional[Path]:
    """Map a page URL path to its Markdown source under ``root`` (or None)."""
    root = Path(root)
    p = norm_path(url_path).strip("/")
    prefixes = ["", "en/"]
    if p.startswith("en/"):
        prefixes.append("__strip__")
    for prefix in prefixes:
        q = p[3:] if prefix == "__strip__" else prefix + p
        base = root / q if q else root
        cands = [base / "index.md", base / "_index.md"]
        if q:
            cands.append(root / (q + ".md"))
        for c in cands:
            if c.is_file():
                return c
    return None


# --------------------------------------------------------------------------- HTML parsing
class _PageParser(HTMLParser):
    """Single-pass collector; tolerant of minified HTML (omitted end tags)."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[dict] = []
        self.in_head = False
        self.in_title = False
        self.skip_depth = 0
        self.title_parts: list[str] = []
        self.meta: dict[str, str] = {}
        self.canonical: Optional[str] = None
        self.headings: list[dict] = []
        self.links: list[dict] = []
        self.imgs: list[dict] = []
        self.tables: list[dict] = []
        self.pres: list[dict] = []
        self.forms: list[dict] = []
        self.paragraphs: list[dict] = []
        self.ids: set[str] = set()
        self.markup_hits: list[dict] = []
        self.chunks: list[tuple[str, int, bool]] = []
        self._cur_heading: Optional[dict] = None
        self._cur_a: Optional[dict] = None
        self._cur_p: Optional[dict] = None
        self._pre_stack: list[dict] = []
        self._table_stack: list[dict] = []
        self._cur_row: Optional[dict] = None
        self._code_depth = 0

    # -- stack management
    def _find_open(self, names: Collection[str], stop: Collection[str]) -> int:
        for i in range(len(self.stack) - 1, -1, -1):
            t = self.stack[i]["tag"]
            if t in names:
                return i
            if t in stop:
                return -1
        return -1

    def _pop_to(self, index: int) -> None:
        while len(self.stack) > index:
            self._close(self.stack.pop())

    def _implied_close(self, tag: str) -> None:
        if tag in P_CLOSERS:
            for i in range(len(self.stack) - 1, -1, -1):
                t = self.stack[i]["tag"]
                if t == "p":
                    self._pop_to(i)
                    break
                if t not in INLINE:
                    break
        if tag == "li":
            i = self._find_open({"li"}, {"ul", "ol", "table"})
            if i >= 0:
                self._pop_to(i)
        elif tag in ("td", "th"):
            i = self._find_open({"td", "th"}, {"tr", "table"})
            if i >= 0:
                self._pop_to(i)
        elif tag == "tr":
            i = self._find_open({"tr"}, {"table"})
            if i >= 0:
                self._pop_to(i)
        elif tag in ("thead", "tbody", "tfoot"):
            i = self._find_open({"thead", "tbody", "tfoot"}, {"table"})
            if i >= 0:
                self._pop_to(i)

    def _in_header_or_nav(self) -> bool:
        return any(e["tag"] in ("header", "nav") for e in self.stack)

    # -- html.parser callbacks
    def handle_starttag(self, tag, attrs):
        a = {k.lower(): (v if v is not None else "") for k, v in attrs}
        line = self.getpos()[0]
        self._scan_markup(tag, a, line)
        self._implied_close(tag)
        if tag in BLOCK:
            self.chunks.append(("\n", line, self._in_code()))
        ent = {"tag": tag, "attrs": a, "line": line}
        if tag in ("code", "kbd", "samp"):
            self._code_depth += 1
        if tag == "head":
            self.in_head = True
        elif tag == "body":
            self.in_head = False
        elif tag == "title":
            self.in_title = True
        elif tag in SKIP_TEXT:
            self.skip_depth += 1
        elif tag == "meta":
            self._meta(a)
        elif tag == "link":
            if "canonical" in a.get("rel", "").lower().split() and self.canonical is None:
                self.canonical = a.get("href", "")
        elif tag in HEADINGS:
            rec = {"level": HEADINGS[tag], "tag": tag, "text": [], "line": line}
            self.headings.append(rec)
            self._cur_heading = ent["rec"] = rec
        elif tag == "a":
            rec = {"href": a.get("href"), "text": [], "line": line, "aria": a.get("aria-label", ""),
                   "title": a.get("title", ""), "img_alt": "", "nav": self._in_header_or_nav()}
            self.links.append(rec)
            self._cur_a = ent["rec"] = rec
        elif tag == "img":
            self.imgs.append({"line": line, "src": a.get("src", ""), "attrs": a})
            if self._cur_a is not None and a.get("alt", "").strip():
                self._cur_a["img_alt"] = a["alt"].strip()
        elif tag == "pre":
            rec = {"line": line, "has_code": False, "gutter": False, "lang": ""}
            self.pres.append(rec)
            self._pre_stack.append(rec)
            ent["rec"] = rec
        elif tag == "code":
            if self._pre_stack:
                self._pre_stack[-1]["has_code"] = True
                m = re.search(r"(?:^|\s)language-([\w+#.-]+)", a.get("class", ""))
                self._pre_stack[-1]["lang"] = (m.group(1) if m else a.get("data-lang", "")).lower()
        elif tag == "span":
            if self._pre_stack and "lnt" in a.get("class", "").split():
                self._pre_stack[-1]["gutter"] = True
        elif tag == "table":
            rec = {"line": line, "skip": "lntable" in a.get("class", "").split(),
                   "has_thead": False, "has_th": False, "rows": [], "rowspan": False}
            self.tables.append(rec)
            self._table_stack.append(rec)
            ent["rec"] = rec
        elif tag == "thead" and self._table_stack:
            self._table_stack[-1]["has_thead"] = True
        elif tag == "tr" and self._table_stack:
            self._cur_row = {"cols": 0}
            self._table_stack[-1]["rows"].append(self._cur_row)
        elif tag in ("td", "th") and self._table_stack:
            t = self._table_stack[-1]
            if tag == "th":
                t["has_th"] = True
            span = _to_int(a.get("colspan"), 1)
            if _to_int(a.get("rowspan"), 1) > 1:
                t["rowspan"] = True
            if self._cur_row is not None:
                self._cur_row["cols"] += max(span, 1)
        elif tag == "p" and not self._pre_stack:
            rec = {"text": [], "line": line}
            self.paragraphs.append(rec)
            self._cur_p = ent["rec"] = rec
        elif tag == "form":
            self.forms.append({"line": line, "nav": self._in_header_or_nav()})
        if a.get("id"):
            self.ids.add(a["id"])
        if tag == "a" and a.get("name"):
            self.ids.add(a["name"])
        if tag not in VOID:
            self.stack.append(ent)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if tag in VOID:
            return
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i]["tag"] == tag:
                self._pop_to(i)
                break
        if tag in BLOCK:
            self.chunks.append(("\n", self.getpos()[0], self._in_code()))

    def _in_code(self) -> bool:
        return bool(self._pre_stack) or self._code_depth > 0

    def _close(self, ent: dict) -> None:
        tag = ent["tag"]
        if tag in ("code", "kbd", "samp"):
            self._code_depth = max(0, self._code_depth - 1)
        if tag == "head":
            self.in_head = False
        elif tag == "title":
            self.in_title = False
        elif tag in SKIP_TEXT:
            self.skip_depth = max(0, self.skip_depth - 1)
        elif tag in HEADINGS:
            self._cur_heading = None
        elif tag == "a":
            self._cur_a = None
        elif tag == "p":
            self._cur_p = None
        elif tag == "pre":
            if self._pre_stack:
                self._pre_stack.pop()
        elif tag == "table":
            if self._table_stack:
                self._table_stack.pop()
            self._cur_row = None
        elif tag == "tr":
            self._cur_row = None

    def handle_data(self, data):
        if self.skip_depth:
            return
        if self.in_title:
            self.title_parts.append(data)
            return
        if self.in_head:
            return
        self.chunks.append((data, self.getpos()[0], self._in_code()))
        if self._cur_heading is not None:
            self._cur_heading["text"].append(data)
        if self._cur_a is not None:
            self._cur_a["text"].append(data)
        if self._cur_p is not None:
            self._cur_p["text"].append(data)

    def close(self):
        super().close()
        self._pop_to(0)

    # -- helpers
    def _meta(self, a: dict) -> None:
        key = (a.get("name") or a.get("property") or "").lower()
        if key and "content" in a and key not in self.meta:
            self.meta[key] = a["content"]

    def _scan_markup(self, tag: str, a: dict, line: int) -> None:
        for name, value in a.items():
            if name in ("class", "id") and re.search(r"evidence", value, re.I):
                self.markup_hits.append({"tag": tag, "line": line, "what": f'{name}="{value}"'})
            elif _DATA_ATTR.match(name):
                self.markup_hits.append({"tag": tag, "line": line, "what": name})


def _to_int(value, default: int) -> int:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


def _parse(html: str) -> _PageParser:
    p = _PageParser()
    p.feed(html)
    p.close()
    return p


def _text(parts: Iterable[str]) -> str:
    return re.sub(r"\s+", " ", "".join(parts)).strip()


def _quote(s: str, limit: int = 90) -> str:
    s = re.sub(r"\s+", " ", s).strip()
    return s if len(s) <= limit else s[: limit - 3] + "..."


# --------------------------------------------------------------------------- external links
def classify_status(status: int) -> str:
    """HTTP status -> ok / broken / unreachable (unreachable != broken)."""
    if 200 <= status < 400:
        return "ok"
    if status in (404, 410):
        return "broken"
    return "unreachable"


def _default_resolve(host: str) -> list[str]:
    infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    return sorted({str(i[4][0]) for i in infos})


def _ip_is_public(ip: str) -> bool:
    """True only for globally routable unicast addresses (SSRF guard)."""
    try:
        addr = ipaddress.ip_address(ip.split("%", 1)[0])
    except ValueError:
        return False
    if addr.version == 6 and addr.ipv4_mapped is not None:
        addr = addr.ipv4_mapped
    return bool(addr.is_global and not addr.is_multicast)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D102
        return None  # surface the 3xx so the checker can validate every hop itself


def _default_fetch(url: str, timeout: float) -> tuple[int, Optional[str]]:
    """One HEAD request; redirects are NOT followed here (see ExternalLinkChecker)."""
    opener = urllib.request.build_opener(_NoRedirect)
    req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "rendered-page-audit/1"})
    try:
        with opener.open(req, timeout=timeout) as resp:  # noqa: S310 (scheme validated by the checker)
            return int(resp.status), None
    except urllib.error.HTTPError as e:
        return int(e.code), e.headers.get("Location")


def load_allowlist(path: Path) -> list[str]:
    out = []
    for raw in Path(path).read_text(encoding="utf-8").splitlines():
        s = raw.strip()
        if s and not s.startswith("#"):
            out.append(s)
    return out


class ExternalLinkChecker:
    """SSRF-safe HEAD checker: disk cache (ok/broken only), per-host rate limit, allow-list.

    Every hop (the original URL and each redirect target) must be http(s) and resolve
    only to globally routable addresses before any connection is made.  ``fetch(url,
    timeout)`` returns a status int or ``(status, location)``; ``resolve(host)`` returns
    a list of IP strings.  Both are injectable so tests never touch the network.
    Residual limit: DNS is resolved once for the check and again by the HTTP client
    (DNS-rebinding window); the checker is opt-in and meant for trusted CI networks.
    """

    def __init__(self, *, fetch: Optional[Callable[[str, float], object]] = None,
                 resolve: Optional[Callable[[str], Iterable[str]]] = None,
                 clock: Optional[Callable[[], float]] = None,
                 sleep: Optional[Callable[[float], None]] = None,
                 cache_dir: Optional[Path] = None, allowlist: Iterable[str] = (),
                 rate_limit_s: float = 1.0, ttl_s: float = 86400.0, timeout_s: float = 10.0,
                 max_redirects: int = 5) -> None:
        self.fetch = fetch or _default_fetch
        self.resolve = resolve or _default_resolve
        self.clock = clock or time.time
        self.sleep = sleep or time.sleep
        self.cache_dir = Path(cache_dir) if cache_dir else None
        self.allowlist = [a.strip() for a in allowlist if a and a.strip()]
        self.rate_limit_s = rate_limit_s
        self.ttl_s = ttl_s
        self.timeout_s = timeout_s
        self.max_redirects = max_redirects
        self._memo: dict[str, str] = {}
        self._reasons: dict[str, str] = {}
        self._last: dict[str, float] = {}

    def reason(self, url: str) -> str:
        return self._reasons.get(url, "")

    def is_allowed(self, url: str) -> bool:
        """Match on parsed scheme + host (exact or dot-boundary suffix) and path-segment prefix."""
        u = urlsplit(url)
        uhost = (u.hostname or "").lower()
        if not uhost:
            return False
        for entry in self.allowlist:
            if "://" in entry:
                e = urlsplit(entry)
                scheme = e.scheme.lower()
            else:
                e = urlsplit("//" + entry.lstrip("."))
                scheme = ""
            ehost = (e.hostname or "").lower()
            if not ehost or (scheme and u.scheme.lower() != scheme):
                continue
            if not (uhost == ehost or uhost.endswith("." + ehost)):
                continue
            try:
                if e.port is not None and u.port != e.port:
                    continue
            except ValueError:
                continue
            epath = (e.path or "").rstrip("/")
            upath = u.path or "/"
            if epath and not (upath == epath or upath.startswith(epath + "/")):
                continue
            return True
        return False

    def _cache_file(self, url: str) -> Optional[Path]:
        if not self.cache_dir:
            return None
        return self.cache_dir / (hashlib.sha256(url.encode("utf-8")).hexdigest()[:32] + ".json")

    def _cache_get(self, url: str) -> Optional[str]:
        f = self._cache_file(url)
        if f is None or not f.is_file():
            return None
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
            if d.get("url") == url and self.clock() - float(d["checked_at"]) <= self.ttl_s \
                    and d.get("result") in ("ok", "broken"):
                return d["result"]
        except (OSError, ValueError, KeyError, TypeError):
            pass
        return None

    def _cache_put(self, url: str, result: str, status: Optional[int]) -> None:
        f = self._cache_file(url)
        if f is None or result not in ("ok", "broken"):
            return  # transient (unreachable/blocked) outcomes are never cached
        try:
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(json.dumps({"url": url, "result": result, "status": status,
                                     "checked_at": self.clock()}, sort_keys=True), encoding="utf-8")
        except OSError:
            pass

    def _guard(self, url: str) -> Optional[str]:
        """Return a refusal reason for this hop, or None when it is safe to connect."""
        sp = urlsplit(url)
        if sp.scheme.lower() not in ("http", "https"):
            return f"blocked: scheme {sp.scheme!r} not allowed"
        host = sp.hostname
        if not host:
            return "blocked: URL has no host"
        try:
            ips = [str(ipaddress.ip_address(host.split("%", 1)[0]))]
        except ValueError:
            try:
                ips = [str(i) for i in self.resolve(host)]
            except Exception:  # noqa: BLE001
                return f"resolution failed for {host}"
            if not ips:
                return f"resolution failed for {host}"
        bad = [ip for ip in ips if not _ip_is_public(ip)]
        if bad:
            return f"blocked: {host} resolves to non-public address {bad[0]}"
        return None

    def _throttle(self, url: str) -> None:
        host = _host(url) or ""
        last = self._last.get(host)
        if last is not None:
            wait = last + self.rate_limit_s - self.clock()
            if wait > 0:
                self.sleep(wait)
        self._last[host] = self.clock()

    def _probe(self, url: str) -> tuple[str, Optional[int], str]:
        cur = url
        for hop in range(self.max_redirects + 1):
            why = self._guard(cur)
            if why:
                return "unreachable", None, why
            self._throttle(cur)
            try:
                out = self.fetch(cur, self.timeout_s)
            except Exception as e:  # noqa: BLE001 - transport failure is "unreachable", never "broken"
                return "unreachable", None, f"request failed ({type(e).__name__})"
            status, location = out if isinstance(out, tuple) else (out, None)
            status = int(status)
            if 300 <= status < 400 and location:
                if hop == self.max_redirects:
                    return "unreachable", status, f"too many redirects (more than {self.max_redirects})"
                cur = urljoin(cur, location)
                continue
            return classify_status(status), status, ""
        return "unreachable", None, "too many redirects"

    def check(self, url: str) -> str:
        if url in self._memo:
            return self._memo[url]
        if self.is_allowed(url):
            self._memo[url] = "allowlisted"
            return "allowlisted"
        cached = self._cache_get(url)
        if cached:
            self._memo[url] = cached
            return cached
        result, status, reason = self._probe(url)
        self._memo[url] = result
        if reason:
            self._reasons[url] = reason
        self._cache_put(url, result, status)
        return result


# --------------------------------------------------------------------------- sitemap
def load_sitemap_info(build_dir: Path) -> Optional[dict]:
    """Parse the build's sitemap.xml (following indexes).  None if absent, else
    {'paths': set of normalised page paths, 'missing': sitemap-index children not in the build}."""
    root = Path(build_dir)
    sm = root / "sitemap.xml"
    if not sm.is_file():
        return None
    paths: set[str] = set()
    missing: list[str] = []
    _read_sitemap(root, sm, paths, missing, set(), 0)
    return {"paths": paths, "missing": sorted(set(missing))}


def load_sitemap_paths(build_dir: Path) -> Optional[set[str]]:
    """Page paths of a COMPLETE sitemap, or None when absent or when an index child is missing."""
    info = load_sitemap_info(build_dir)
    if info is None or info["missing"]:
        return None
    return info["paths"]


def partition_prefixes(missing: Iterable[str]) -> list[str]:
    """Directory prefixes of sitemap-index children that were not built (split deploys)."""
    out = set()
    for loc in missing:
        prefix = urlsplit(loc).path.rsplit("/", 1)[0] + "/"
        if prefix != "/":
            out.add(prefix)
    return sorted(out)


def _read_sitemap(root: Path, f: Path, out: set[str], missing: list[str], seen: set[Path], depth: int) -> None:
    if f in seen or depth > 3:
        return
    seen.add(f)
    try:
        tree = ET.parse(f)
    except ET.ParseError as e:
        raise RuntimeError(f"unparsable sitemap {f}: {e}") from e
    top = tree.getroot()
    is_index = top.tag.rsplit("}", 1)[-1] == "sitemapindex"
    for el in top.iter():
        if el.tag.rsplit("}", 1)[-1] != "loc" or not (el.text or "").strip():
            continue
        loc = el.text.strip()
        if is_index:
            child = url_to_file(root, urlsplit(loc).path)
            if child is None:
                missing.append(loc)
            else:
                _read_sitemap(root, child, out, missing, seen, depth + 1)
        else:
            out.add(norm_path(loc))


# --------------------------------------------------------------------------- findings
def _finding(page: str, check: str, severity: str, message: str, evidence: str) -> dict:
    return {"page": page, "check": check, "severity": severity, "message": message, "evidence": evidence}


def _sort_key(f: dict):
    return (f["page"], _CHECK_ORDER.get(f["check"], 99), _SEV_RANK[f["severity"]], f["evidence"], f["message"])


def _line_index(chunks):
    starts, pos = [], 0
    for text, _, _ in chunks:
        starts.append(pos)
        pos += len(text)
    return starts


def _scan_text(chunks, regex: str, flags: int):
    """Yield (match, line, in_pre, joined_text) for each match over the visible text."""
    joined = "".join(c[0] for c in chunks)
    starts = _line_index(chunks)
    for m in re.finditer(regex, joined, flags):
        i = max(bisect.bisect_right(starts, m.start()) - 1, 0)
        yield m, chunks[i][1], chunks[i][2], joined


def _snippet(joined: str, m: re.Match, pad: int = 30) -> str:
    return _quote(joined[max(0, m.start() - pad): m.end() + pad])


# --------------------------------------------------------------------------- core: one page
def audit_page(html: str, *, url: str, md_source: Optional[str] = None,
               build_dir: Optional[Path] = None, site_base_url: Optional[str] = None,
               sitemap: Optional[Collection[str]] = None, external_links: str = "off",
               allowlist: Iterable[str] = (), cache_dir: Optional[Path] = None,
               fetch: Optional[Callable[[str, float], object]] = None,
               resolve: Optional[Callable[[str], Iterable[str]]] = None,
               clock: Optional[Callable[[], float]] = None,
               sleep: Optional[Callable[[float], None]] = None,
               rate_limit_s: float = 1.0, cache_ttl_s: float = 86400.0, timeout_s: float = 10.0,
               max_redirects: int = 5,
               checker: Optional[ExternalLinkChecker] = None,
               non_pre_fence_languages: Optional[Collection[str]] = None,
               sitemap_missing: Collection[str] = (),
               _ids_cache: Optional[dict] = None) -> dict:
    """Audit one built page.  Returns {page, checks, na_reasons, findings, unverified_links, external}.

    ``sitemap_missing`` lists sitemap-index children absent from the build (split deploys):
    R3.9 becomes NA, a PAGE warning is emitted, and links into those partitions are listed
    under ``unverified_links`` instead of being reported as broken (R3.6).
    """
    page = norm_path(url)
    P = _parse(html)
    findings: list[dict] = []
    na: set[str] = set()
    na_reasons: dict[str, str] = {}
    base_host = _host(site_base_url)
    site_host = base_host or _host(url) or _host(P.canonical)  # link classification only
    ids_cache = _ids_cache if _ids_cache is not None else {}
    unbuilt = partition_prefixes(sitemap_missing)
    unverified: list[dict] = []
    tolerated_langs = (DEFAULT_NON_PRE_FENCE_LANGUAGES if non_pre_fence_languages is None
                       else frozenset(x.lower() for x in non_pre_fence_languages))

    def add(check, severity, message, evidence):
        findings.append(_finding(page, check, severity, message, evidence))

    # R3.1 -------------------------------------------------------------
    h1s = [h for h in P.headings if h["level"] == 1]
    if len(h1s) != 1:
        msg = "page has no <h1>" if not h1s else f"page has {len(h1s)} <h1> elements (expected exactly 1)"
        ev = "; ".join(f'h1 "{_quote(_text(h["text"]), 40)}" line {h["line"]}' for h in h1s) or "no h1"
        add("R3.1", "major", msg, ev)
    prev = None
    for h in P.headings:
        if prev is not None and h["level"] > prev["level"] + 1:
            add("R3.1", "minor", f'heading level skips from h{prev["level"]} to h{h["level"]}',
                f'h{h["level"]} "{_quote(_text(h["text"]), 40)}" line {h["line"]}')
        prev = h

    # R3.2 -------------------------------------------------------------
    if not _text(P.title_parts):
        add("R3.2", "major", "missing or empty <title>", "<title>")
    if not P.meta.get("description", "").strip():
        add("R3.2", "major", "missing or empty meta description", 'meta[name=description]')
    if not (P.canonical or "").strip():
        add("R3.2", "major", "missing or empty canonical link", "link[rel=canonical]")
    else:
        sp = urlsplit(P.canonical.strip())
        if sp.scheme not in ("http", "https") or not sp.netloc:
            add("R3.2", "major", "canonical URL is not absolute", f"canonical={P.canonical}")
        else:
            if sp.scheme != "https":
                add("R3.2", "minor", "canonical URL is not https", f"canonical={P.canonical}")
            if norm_path(sp.path) != page:
                add("R3.2", "major", f"canonical path does not match page URL {page}", f"canonical={P.canonical}")
            if base_host is None:
                na.add("R3.2-host")
                na_reasons["R3.2-host"] = "canonical host cannot be verified without --site-base-url"
            elif sp.hostname and sp.hostname.lower() != base_host:
                add("R3.2-host", "major", f"canonical host does not match site host {base_host}",
                    f"canonical={P.canonical}")
    if base_host is None:
        na.add("R3.2-host")
        na_reasons.setdefault("R3.2-host", "canonical host cannot be verified without --site-base-url")
    for key in ("og:title", "og:description"):
        if not P.meta.get(key, "").strip():
            add("R3.2", "minor", f"missing or empty {key}", f"meta[property={key}]")

    # R3.3 -------------------------------------------------------------
    if md_source is None:
        na.add("R3.3")
        na_reasons["R3.3"] = "no Markdown source mapped for this page (--md-source-root)"
    else:
        html_langs = [p["lang"] for p in P.pres if p["has_code"] and not p["gutter"]]
        md_langs = markdown_fence_languages(md_source)
        html_blocks, md_blocks = len(html_langs), len(md_langs)
        tolerated = [lang for lang in md_langs if lang in tolerated_langs]
        expected = md_blocks - len(tolerated)
        if tolerated:
            add("R3.3", "info",
                f"{len(tolerated)} fenced block(s) of non-<pre> language(s) "
                f"{', '.join(sorted(set(tolerated)))} excluded from the parity count",
                f"tolerated={','.join(tolerated)}")
        if html_blocks not in (expected, md_blocks):
            add("R3.3", "major", "rendered <pre><code> block count differs from Markdown fenced blocks",
                f"html={html_blocks} md={md_blocks} expected_pre={expected} "
                f"md_langs={','.join(md_langs) or '-'} html_langs={','.join(x or '-' for x in html_langs) or '-'}")

    # R3.4 -------------------------------------------------------------
    for t in P.tables:
        if t["skip"]:
            continue
        if not t["has_thead"] and not t["has_th"]:
            add("R3.4", "major", "table has no header row (<thead>/<th>)", f'table line {t["line"]}')
        counts = [r["cols"] for r in t["rows"] if r["cols"]]
        if len(set(counts)) > 1 and not t["rowspan"]:
            add("R3.4", "major", "table rows have inconsistent column counts",
                f'table line {t["line"]}: columns per row {",".join(map(str, counts))}')

    # R3.5 -------------------------------------------------------------
    for im in P.imgs:
        a = im["attrs"]
        decorative = a.get("role", "").lower() in ("presentation", "none") or a.get("aria-hidden", "") == "true"
        if "alt" not in a or (not a["alt"].strip() and not (decorative and "alt" in a)):
            add("R3.5", "major", "image has no alt text", f'img src={im["src"]} line {im["line"]}')

    # R3.6 / R4.4 / R3.7 / R6.5 (links) ---------------------------------
    external: dict[str, str] = {}
    ext_urls: dict[str, int] = {}
    internal_file_links = 0
    for ln in P.links:
        href = (ln["href"] or "").strip()
        if not href:
            continue
        ev = f'a href="{href}" line {ln["line"]}'
        sp = urlsplit(href)
        scheme = sp.scheme.lower()
        if scheme and scheme not in ("http", "https"):
            continue  # mailto:, tel:, javascript:, data:, ...
        is_abs = bool(sp.netloc)
        if is_abs and (site_host is None or sp.hostname is None or sp.hostname.lower() != site_host):
            # external or cross-subdomain
            if site_host and sp.hostname and _sld(sp.hostname) == _sld(site_host):
                if scheme != "https":
                    add("R4.4", "major", "cross-subdomain link must be an absolute https:// URL", ev)
                if re.match(r"^/en(/|$)", sp.path):
                    add("R4.4", "major", "cross-subdomain link must not contain /en/ for English", ev)
            if scheme in ("http", "https"):
                ext_urls.setdefault(href.split("#", 1)[0], ln["line"])
            continue
        # internal link (relative, root-relative or same-host absolute)
        if is_abs:
            target_path, frag = sp.path or "/", sp.fragment
        else:
            joined = urljoin(page, href)
            jp = urlsplit(joined)
            target_path, frag = jp.path, jp.fragment
        same_page = (not is_abs and not sp.path and not sp.query) or (not is_abs and href.startswith("#"))
        if same_page:
            target_path = page
        frag = unquote(frag)
        if same_page:
            if frag and frag != "top" and frag not in P.ids:
                add("R3.6", "minor", f"fragment #{frag} not found on this page", ev)
            continue
        if build_dir is None:
            internal_file_links += 1
            continue
        f = url_to_file(Path(build_dir), target_path)
        if f is None:
            if any(target_path.startswith(pfx) for pfx in unbuilt):
                unverified.append({"href": href, "line": ln["line"],
                                   "reason": "target lies in a partition that was not built (sitemap index child missing)"})
                continue
            add("R3.6", "blocker", f"internal link target not found in build: {target_path}", ev)
            continue
        if frag and frag != "top" and f.suffix.lower() in (".html", ".htm"):
            if f not in ids_cache:
                try:
                    ids_cache[f] = _parse(f.read_text(encoding="utf-8", errors="replace")).ids
                except OSError:
                    ids_cache[f] = None
            ids = ids_cache[f]
            if ids is not None and frag not in ids:
                add("R3.6", "minor", f"fragment #{frag} not found in {target_path}", ev)
    if build_dir is None and internal_file_links:
        na.add("R3.6")
        na_reasons["R3.6"] = "no build directory given; internal link targets not resolved"

    # R6.5 -------------------------------------------------------------
    for ln in P.links:
        if ln["href"] is None:
            continue
        text = _text(ln["text"])
        has_name = bool(text or ln["aria"].strip() or ln["title"].strip() or ln["img_alt"])
        ev = f'a href="{ln["href"]}" line {ln["line"]}'
        if not has_name:
            add("R6.5", "minor", "link has no accessible text", ev)
        elif text.lower() in GENERIC_LINK_TEXT:
            add("R6.5", "minor", f'non-descriptive link text "{text}"', ev)
    for fm in P.forms:
        if not fm["nav"]:
            add("R6.5", "minor", "form element in page body", f'form line {fm["line"]}')

    # R3.7 -------------------------------------------------------------
    if external_links == "head":
        chk = checker or ExternalLinkChecker(fetch=fetch, resolve=resolve, clock=clock, sleep=sleep,
                                             cache_dir=cache_dir, allowlist=allowlist,
                                             rate_limit_s=rate_limit_s, ttl_s=cache_ttl_s,
                                             timeout_s=timeout_s, max_redirects=max_redirects)
        for u in sorted(ext_urls):
            res = chk.check(u)
            external[u] = res
            if res == "broken":
                add("R3.7", "major", "external link is broken (HEAD 404/410)", u)
            elif res == "unreachable":
                why = chk.reason(u) or "timeout/DNS/transient error"
                add("R3.7", "minor", f"external link unreachable ({why}); not proven broken", u)
    else:
        na.add("R3.7")
        na_reasons["R3.7"] = "external link checking is off (--external-links head to enable)"

    # R3.8 -------------------------------------------------------------
    for hit in P.markup_hits:
        add("R3.8", "blocker", "internal evidence/provenance markup present in the rendered page",
            f'{hit["tag"]} {hit["what"]} line {hit["line"]}')
    for label, rx, flags, sev in LEAK_PATTERNS:
        for m, line, in_code, joined in _scan_text(P.chunks, rx, flags):
            if in_code:
                continue  # code samples may legitimately show frontmatter / metadata keys
            add("R3.8", sev, f"internal metadata visible in body ({label})", f'line {line}: "{_snippet(joined, m)}"')

    # R3.9 -------------------------------------------------------------
    if sitemap_missing:
        na.add("R3.9")
        shown = ", ".join(sorted(sitemap_missing))
        na_reasons["R3.9"] = f"sitemap index is incomplete; child missing from build: {shown}"
        add("PAGE", "minor", f"sitemap index child missing from the build ({shown}): "
            "R3.9 and cross-partition link checks degraded", shown)
    elif sitemap is None:
        na.add("R3.9")
        na_reasons["R3.9"] = "no sitemap.xml in the build"
    elif page not in {norm_path(s) for s in sitemap}:
        add("R3.9", "major", "page is not listed in the build sitemap.xml", page)

    # R3.11 / R2.4 -------------------------------------------------------
    for label, rx, flags, prose_only in PLACEHOLDER_PATTERNS:
        for m, line, in_pre, joined in _scan_text(P.chunks, rx, flags):
            if prose_only and in_pre:
                continue
            add("R3.11", "blocker", f"placeholder marker visible ({label}; also R2.4)",
                f'line {line}: "{_snippet(joined, m)}"')

    # R4.1 -------------------------------------------------------------
    seen: dict[str, list[int]] = {}
    for p in P.paragraphs:
        norm = _text(p["text"]).lower()
        if len(norm) >= DUP_MIN_CHARS:
            seen.setdefault(norm, []).append(p["line"])
    for norm, lines in sorted(seen.items(), key=lambda kv: kv[1][0]):
        if len(lines) > 1:
            add("R4.1", "major", f"paragraph repeated {len(lines)} times within the page",
                f'lines {",".join(map(str, lines))}: "{_quote(norm, 70)}"')

    # assemble -----------------------------------------------------------
    uniq = {(f["check"], f["severity"], f["message"], f["evidence"]): f for f in findings}
    findings = sorted(uniq.values(), key=_sort_key)
    failed = {f["check"] for f in findings if f["severity"] != "info"}
    if "R3.2-host" in failed:
        failed.add("R3.2")
    checks = {}
    for c in CHECKS:
        if c == "R2.4":
            checks[c] = "FAIL" if "R3.11" in failed else "PASS"
        elif c in na:
            checks[c] = "NA"
        else:
            checks[c] = "FAIL" if c in failed else "PASS"
    return {"page": page, "checks": checks, "na_reasons": dict(sorted(na_reasons.items())),
            "findings": findings, "unverified_links": sorted(unverified, key=lambda u: (u["href"], u["line"])),
            "external": dict(sorted(external.items()))}


# --------------------------------------------------------------------------- build level
def resolve_page_arg(build_dir: Path, arg: str) -> tuple[str, Optional[Path]]:
    """Return (page url path, built file or None) for a URL path/URL/file-path argument."""
    root = Path(build_dir).resolve()
    s = arg.strip()
    if re.match(r"^https?://", s, re.I):
        p = norm_path(s)
        return p, url_to_file(root, p)
    cand = Path(s)
    for c in (cand, root / s):
        try:
            if c.is_file():
                r = c.resolve()
                if r == root or root in r.parents:
                    return norm_path("/" + r.relative_to(root).as_posix()), r
                return norm_path("/" + r.name), r
        except OSError:
            continue
    p = norm_path(s)
    return p, url_to_file(root, p)


def audit_build(build_dir: Path, pages: Iterable[str], *, md_source_root: Optional[Path] = None,
                site_base_url: Optional[str] = None, external_links: str = "off",
                allowlist: Iterable[str] = (), cache_dir: Optional[Path] = None,
                fetch: Optional[Callable[[str, float], object]] = None,
                resolve: Optional[Callable[[str], Iterable[str]]] = None,
                clock: Optional[Callable[[], float]] = None,
                sleep: Optional[Callable[[float], None]] = None,
                sitemap: Optional[Collection[str]] = None, load_sitemap: bool = True,
                rate_limit_s: float = 1.0, cache_ttl_s: float = 86400.0, timeout_s: float = 10.0,
                max_redirects: int = 5,
                non_pre_fence_languages: Optional[Collection[str]] = None) -> dict:
    """Audit many pages of one built site; deterministic output independent of page order."""
    build_dir = Path(build_dir)
    sitemap_missing: list[str] = []
    if sitemap is None and load_sitemap:
        info = load_sitemap_info(build_dir)
        if info is not None:
            sitemap_missing = list(info["missing"])
            sitemap = None if sitemap_missing else info["paths"]
    checker = None
    if external_links == "head":
        checker = ExternalLinkChecker(fetch=fetch, resolve=resolve, clock=clock, sleep=sleep,
                                      cache_dir=cache_dir, allowlist=allowlist,
                                      rate_limit_s=rate_limit_s, ttl_s=cache_ttl_s,
                                      timeout_s=timeout_s, max_redirects=max_redirects)
    resolved: dict[str, Optional[Path]] = {}
    for arg in pages:
        url, f = resolve_page_arg(build_dir, arg)
        if url not in resolved or (resolved[url] is None and f is not None):
            resolved[url] = f
    ids_cache: dict = {}
    results = []
    for url in sorted(resolved):
        f = resolved[url]
        if f is None:
            results.append({"page": url, "checks": {c: "NA" for c in CHECKS}, "na_reasons": {},
                            "external": {}, "unverified_links": [],
                            "findings": [_finding(url, "PAGE", "blocker",
                                                  "page not found in the build directory", url)]})
            continue
        html = f.read_text(encoding="utf-8", errors="replace")
        md = None
        if md_source_root is not None:
            src = resolve_md_source(url, Path(md_source_root))
            if src is not None:
                md = src.read_text(encoding="utf-8", errors="replace")
        results.append(audit_page(html, url=url, md_source=md, build_dir=build_dir,
                                  site_base_url=site_base_url, sitemap=sitemap,
                                  external_links=external_links, checker=checker,
                                  non_pre_fence_languages=non_pre_fence_languages,
                                  sitemap_missing=sitemap_missing, _ids_cache=ids_cache))
    flat = sorted((f for r in results for f in r["findings"]), key=_sort_key)
    by_check: dict[str, int] = {}
    for f in flat:
        by_check[f["check"]] = by_check.get(f["check"], 0) + 1
    summary = {"pages": len(results), "findings": len(flat),
               **{s: sum(1 for f in flat if f["severity"] == s) for s in SEVERITIES},
               "by_check": dict(sorted(by_check.items(), key=lambda kv: _CHECK_ORDER.get(kv[0], 99)))}
    return {"schema": SCHEMA, "summary": summary, "pages": results, "findings": flat}


def exit_code_for(report: dict, fail_on: str) -> int:
    s = report["summary"]
    if fail_on == "none":
        return 0
    if s["blocker"]:
        return 1
    if fail_on == "major" and s["major"]:
        return 1
    return 0


# --------------------------------------------------------------------------- rendering / CLI
def render_markdown(report: dict) -> str:
    s = report["summary"]
    out = ["# Rendered page audit", "",
           f'Pages: {s["pages"]} | findings: {s["findings"]} '
           f'(blocker {s["blocker"]}, major {s["major"]}, minor {s["minor"]}, info {s["info"]})', ""]
    for pg in report["pages"]:
        counts = {}
        for f in pg["findings"]:
            counts[f["severity"]] = counts.get(f["severity"], 0) + 1
        out.append(f'## {pg["page"]}')
        out.append("")
        out.append("Checks: " + ", ".join(f"{k}={v}" for k, v in pg["checks"].items()))
        out.append("")
        if not pg["findings"]:
            out.append("No findings.")
            out.append("")
            continue
        out.append("| severity | check | message | evidence |")
        out.append("|---|---|---|---|")
        for f in pg["findings"]:
            esc = lambda t: t.replace("|", "\\|").replace("\n", " ")  # noqa: E731
            out.append(f'| {f["severity"]} | {f["check"]} | {esc(f["message"])} | {esc(f["evidence"])} |')
        out.append("")
    return "\n".join(out)


def _build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="rendered_page_audit.py",
        description="Deterministic audit of already-built Hugo HTML pages (IVP companion, rubric R3.x/R4.x/R6.5).")
    ap.add_argument("--build-dir", required=True, help="directory holding the built site output")
    ap.add_argument("--pages", nargs="*", default=[], help="URL paths (/a/b/), URLs or built file paths")
    ap.add_argument("--pages-file", help="file with one page per line ('#' comments allowed)")
    ap.add_argument("--md-source-root", help="content dir mapping pages to .md sources (enables R3.3)")
    ap.add_argument("--site-base-url", help="e.g. https://docs.example.org (canonical host / same-host links)")
    ap.add_argument("--external-links", choices=("off", "head"), default="off")
    ap.add_argument("--external-allowlist", help="file of hosts/URL prefixes never fetched")
    ap.add_argument("--cache-dir", help="disk cache for external link results")
    ap.add_argument("--json-out", help="also write the JSON report here")
    ap.add_argument("--format", choices=("json", "md"), default="json")
    ap.add_argument("--fail-on", choices=("blocker", "major", "none"), default="major")
    ap.add_argument("--non-pre-fence-languages",
                    help="comma-separated fence languages rendered without <pre><code> (R3.3 tolerance; "
                         "default: " + ",".join(sorted(DEFAULT_NON_PRE_FENCE_LANGUAGES)) + "; empty = none)")
    return ap


def main(argv: Optional[list[str]] = None) -> int:
    ap = _build_parser()
    args = ap.parse_args(argv)
    build_dir = Path(args.build_dir)
    if not build_dir.is_dir():
        ap.error(f"--build-dir is not a directory: {build_dir}")
    pages = list(args.pages)
    if args.pages_file:
        pf = Path(args.pages_file)
        if not pf.is_file():
            ap.error(f"--pages-file not found: {pf}")
        pages += [ln.strip() for ln in pf.read_text(encoding="utf-8").splitlines()
                  if ln.strip() and not ln.strip().startswith("#")]
    if not pages:
        ap.error("no pages given (use --pages and/or --pages-file)")
    allow = load_allowlist(Path(args.external_allowlist)) if args.external_allowlist else []
    try:
        report = audit_build(build_dir, pages,
                             md_source_root=Path(args.md_source_root) if args.md_source_root else None,
                             site_base_url=args.site_base_url, external_links=args.external_links,
                             allowlist=allow, cache_dir=Path(args.cache_dir) if args.cache_dir else None,
                             non_pre_fence_languages=(
                                 None if args.non_pre_fence_languages is None
                                 else [x.strip() for x in args.non_pre_fence_languages.split(",") if x.strip()]))
    except RuntimeError as e:
        print(f"rendered_page_audit: {e}", file=sys.stderr)
        return 2
    payload = json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    if args.json_out:
        out = Path(args.json_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(payload, encoding="utf-8")
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except (AttributeError, ValueError):
        pass
    sys.stdout.write(payload if args.format == "json" else render_markdown(report) + "\n")
    return exit_code_for(report, args.fail_on)


if __name__ == "__main__":
    sys.exit(main())
