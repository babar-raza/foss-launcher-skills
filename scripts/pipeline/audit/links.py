"""links.py — Internal link verification for content pages.

Extracted from audit.py (Phase 5). Checks all markdown links in a file
for broken internal references against the site content directory tree.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

# token_ops.Finding is accessible from audit.py via its import chain
# Resolve import path the same way audit.py does
# sibling-import guard: sub-packages must add the pipeline root so they can
# import sibling top-level modules (knowledge_core, token_ops, core.*).
# This is not the antipattern -- Python adds the sub-package dir to sys.path,
# not the pipeline root. This guard is the correct workaround for the flat layout.
_HERE = Path(__file__).resolve().parent.parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from token_ops import Finding  # noqa: E402
from core.markdown import _FRONTMATTER_RE  # noqa: E402  (was: knowledge_core — R-0b cleanup)


_MD_LINK_RE = re.compile(r"\[([^\]]*)\]\(([^)]+)\)")

# Map from hostname to content directory patterns
_SITE_CONTENT_MAP = {
    "docs.aspose.org":      "content/docs.aspose.org/en",
    "blog.aspose.org":      "content/blog.aspose.org",
    "kb.aspose.org":        "content/kb.aspose.org/en",
    "products.aspose.org":  "content/products.aspose.org/en",
    "reference.aspose.org": "content/reference.aspose.org/en",
}


def _resolve_link_to_file(url, source_filepath):
    """Resolve an internal link URL to a content file path.

    Returns (resolved_path, link_kind) where link_kind is:
      "absolute"       – proper https:// cross-subdomain link
      "cross_relative" – root-relative but targets another subdomain (wrong form)
      "same_site"      – root-relative within the same subdomain
      None             – external / not an internal link (caller should skip)

    resolved_path is a Path if found, or None if the target does not exist.
    """
    url = url.split("#")[0].split("?")[0].rstrip("/")  # strip anchor/query/trailing slash
    if not url:
        return None, None

    # Absolute URL: https://site.aspose.org/path/...
    for hostname, content_dir in _SITE_CONTENT_MAP.items():
        prefix = f"https://{hostname}/"
        if url.startswith(prefix):
            rel_path = url[len(prefix):]
            return _check_content_path(Path(content_dir), rel_path), "absolute"

    # Relative URL starting with /
    if url.startswith("/"):
        rel = url.lstrip("/")
        # Cross-subdomain root-relative: /docs.aspose.org/en/email/net/...
        # These resolve but are the WRONG link form — should be absolute https://
        for hostname, content_dir in _SITE_CONTENT_MAP.items():
            if rel.startswith(hostname + "/"):
                inner = rel[len(hostname) + 1:]  # strip "docs.aspose.org/"
                # The content_dir already includes /en for non-blog sites,
                # so strip a leading en/ from the inner path to avoid doubling.
                if "/en" in content_dir and inner.startswith("en/"):
                    inner = inner[3:]
                return _check_content_path(Path(content_dir), inner), "cross_relative"
        # Same-site root-relative: /email/net/getting-started/...
        source_str = str(source_filepath).replace("\\", "/")
        for hostname, content_dir in _SITE_CONTENT_MAP.items():
            if content_dir.replace("\\", "/") in source_str:
                return _check_content_path(Path(content_dir), rel), "same_site"

    return None, None


def _kebab_to_pascal(slug: str) -> str:
    """Convert a kebab-case slug back to PascalCase.

    Hugo generates kebab-case URLs from PascalCase filenames:
    ``FillFormat.md`` → ``/fill-format/``.  This reverses that transform.
    """
    return "".join(part.capitalize() for part in slug.split("-"))


def _check_content_path(base, rel_path):
    """Check if a content path resolves to a real file. Returns the Path if found, None if not."""
    rel_path = rel_path.strip("/")
    candidates = [
        base / rel_path / "_index.md",
        base / rel_path / "index.md",
        base / (rel_path + ".md"),
        base / rel_path,  # exact file
    ]
    for c in candidates:
        if c.exists():
            return c

    # Fallback: the last path segment may be a kebab-case Hugo slug derived
    # from a PascalCase filename (e.g. /fill-format/ → FillFormat.md).
    parts = rel_path.split("/")
    pascal_leaf = _kebab_to_pascal(parts[-1])
    if pascal_leaf != parts[-1]:
        parent = base / "/".join(parts[:-1]) if len(parts) > 1 else base
        pascal_candidates = [
            parent / pascal_leaf / "_index.md",
            parent / pascal_leaf / "index.md",
            parent / (pascal_leaf + ".md"),
        ]
        for c in pascal_candidates:
            if c.exists():
                return c

    return None


def verify_internal_links(filepath) -> list:
    """Check all markdown links in a file for broken internal references.

    Returns a list of Finding objects.
    """
    try:
        text = filepath.read_text(encoding="utf-8")
    except Exception:
        return []

    # Strip frontmatter
    m = _FRONTMATTER_RE.match(text)
    body = text[m.end():] if m else text

    findings = []
    for line_no, line in enumerate(body.splitlines(),
                                   start=(text[:m.end()].count("\n") + 1 if m else 1)):
        for match in _MD_LINK_RE.finditer(line):
            link_text, url = match.group(1), match.group(2)
            # Skip external links, mailto, images, anchors-only
            if url.startswith(("mailto:", "http://", "#")):
                continue
            if url.startswith("https://") and not any(
                h in url for h in _SITE_CONTENT_MAP
            ):
                continue  # external https link

            resolved, kind = _resolve_link_to_file(url, filepath)
            if kind is None:
                continue  # not an internal link
            if kind == "cross_relative":
                # Root-relative link targeting another subdomain — wrong form.
                # Build the correct absolute URL, stripping /en/ for English.
                rel = url.lstrip("/")
                correct = url
                for h in _SITE_CONTENT_MAP:
                    if rel.startswith(h + "/"):
                        after_host = rel[len(h):]  # e.g. /en/email/net/...
                        # English pages omit /en/ in the public URL
                        if after_host.startswith("/en/"):
                            after_host = "/" + after_host[4:]
                        correct = f"https://{h}{after_host}"
                        break
                findings.append(Finding(
                    "WARN", filepath, line_no,
                    f"Cross-subdomain link must be absolute: [{link_text}]({url})",
                    f"Use {correct} instead of root-relative path",
                ))
            elif resolved is None:
                findings.append(Finding(
                    "WARN", filepath, line_no,
                    f"Broken internal link: [{link_text}]({url})",
                    "Target page does not exist in content/",
                ))

    return findings
