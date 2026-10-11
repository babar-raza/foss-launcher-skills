"""SEO-PAGE-METADATA-CONSISTENCY (Contract E): page-level consistency
between a page's title/description (and, for a family-root page, its
subtitle) -- a WARN-only judgment layer, never a hard FAIL.

Real constraint, confirmed against the live theme templates (v14 design
doc): no separate H1 or page-summary field exists anywhere -- `title` is
the rendered `<h1>` on every theme (`themes/{docs,kb,blog,products}/
layouts/_default/single.html` and siblings all emit `<h1>{{ .Title }}</h1>`).
`subtitle` exists only on a family-root `_index.md` page (`content/{docs,
kb,reference,products}.aspose.org/en/{family}/_index.md` -- confirmed
against `scripts/pipeline/commands/diagnostics/audit_family_subtitles.py`'s
own real family-root shape), used only in child-listing shortcodes, never
rendered as a page's own lead. So the real, honest scope of "page-level
consistency" for a regular content page is title vs. description; for a
family-root page, also subtitle vs. the newly-proposed title.

Findings are always WARN-severity, never FAIL -- these are judgment calls
that route to `requires_human_review` in `safety.py`, matching that
module's existing checks-8-9 flagged-not-auto-rejected precedent. This
module performs no I/O of its own for the two field-repetition checks
(`check_page_metadata_consistency` is a pure function over its arguments,
per the design doc's own signature); `load_current_subtitle` is the one
real (local, stdlib+pyyaml) file read, kept separate so the caller decides
when it's worth doing.
"""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field as dataclass_field
from pathlib import Path

import yaml

_THIS_FILE = Path(__file__).resolve()
_DEFAULT_REPO_ROOT = _THIS_FILE.parents[3]
REPO_ROOT = _DEFAULT_REPO_ROOT


def configure(*, repo_root: "Path | str | None" = None) -> None:
    """Override the module-level repo root for testing -- this module
    writes nothing, but `load_current_subtitle`'s real frontmatter read
    must never silently fall through to the real, shared content/ tree
    from an isolated test fixture."""
    global REPO_ROOT
    REPO_ROOT = Path(repo_root) if repo_root is not None else _DEFAULT_REPO_ROOT


_TOKEN_RE = re.compile(r"[a-z0-9]+")

# A small, generic stopword list -- "significant tokens" for the subtitle-
# drift check means content words, not the connective tissue every title
# and subtitle share regardless of topic.
_STOPWORDS = frozenset({
    "a", "an", "the", "of", "to", "in", "on", "for", "and", "or", "is",
    "are", "with", "by", "at", "from", "this", "that", "it", "as", "your",
    "you", "be", "can", "will", "our", "their", "its", "&",
})

_JACCARD_WARN_THRESHOLD = 0.7

# Family-root pages carry a subtitle -- content/{site}/en/{family}/_index.md,
# exactly 2 path segments after en/ (family, then _index.md), no platform
# component. Matches audit_family_subtitles.py's own real, live scope.
_FAMILY_ROOT_SITES = (
    "docs.aspose.org", "kb.aspose.org", "reference.aspose.org", "products.aspose.org",
)


def _tokenize(text: "str | None") -> "list[str]":
    return _TOKEN_RE.findall(text.lower()) if text else []


def _significant_tokens(text: "str | None") -> "set[str]":
    return {t for t in _tokenize(text) if t not in _STOPWORDS}


def _normalize(text: str) -> str:
    return " ".join(_tokenize(text))


@dataclass(frozen=True)
class ConsistencyFinding:
    code: str
    detail: str


@dataclass(frozen=True)
class ConsistencyReport:
    findings: "list[ConsistencyFinding]" = dataclass_field(default_factory=list)

    @property
    def has_warnings(self) -> bool:
        return bool(self.findings)


def _check_near_literal_repetition(title: "str | None", description: "str | None") -> "ConsistencyFinding | None":
    """Near-literal title/description repetition: normalized containment
    (one is wholly contained in the other, ignoring case/punctuation) OR
    token-set Jaccard similarity > 0.7."""
    if not title or not description:
        return None
    norm_title, norm_desc = _normalize(title), _normalize(description)
    if not norm_title or not norm_desc:
        return None

    if norm_title in norm_desc or norm_desc in norm_title:
        return ConsistencyFinding(
            "title_description_near_literal_repetition",
            "the description is a near-literal repetition of the title (normalized containment)",
        )

    title_tokens, desc_tokens = set(_tokenize(title)), set(_tokenize(description))
    union = title_tokens | desc_tokens
    if not union:
        return None
    jaccard = len(title_tokens & desc_tokens) / len(union)
    if jaccard > _JACCARD_WARN_THRESHOLD:
        return ConsistencyFinding(
            "title_description_near_literal_repetition",
            f"title/description token-set Jaccard similarity {jaccard:.2f} > {_JACCARD_WARN_THRESHOLD}",
        )
    return None


def _check_source_keyword_in_both(
    title: "str | None", description: "str | None", source_keywords: "list[str] | None",
) -> "ConsistencyFinding | None":
    """A source_keywords phrase appearing verbatim in BOTH fields -> WARN
    (not FAIL -- legitimate when the primary keyword genuinely belongs in
    both)."""
    if not title or not description or not source_keywords:
        return None
    title_lower, desc_lower = title.lower(), description.lower()
    for phrase in source_keywords:
        if not phrase:
            continue
        phrase_lower = phrase.strip().lower()
        if not phrase_lower:
            continue
        if phrase_lower in title_lower and phrase_lower in desc_lower:
            return ConsistencyFinding(
                "source_keyword_in_both_fields",
                f"keyword phrase {phrase_lower!r} appears verbatim in both title and description",
            )
    return None


def _check_family_root_subtitle_drift(
    subtitle: "str | None", proposed_title: "str | None",
) -> "ConsistencyFinding | None":
    """A family-root subtitle sharing zero significant tokens with a
    NEWLY-PROPOSED title -> WARN. Only meaningful when both a real
    subtitle and a genuinely new title proposal exist -- an unchanged
    title cannot "drift" from a subtitle it was presumably already
    consistent with."""
    if not subtitle or not proposed_title:
        return None
    subtitle_tokens = _significant_tokens(subtitle)
    title_tokens = _significant_tokens(proposed_title)
    if not subtitle_tokens or not title_tokens:
        return None
    if not (subtitle_tokens & title_tokens):
        return ConsistencyFinding(
            "family_root_subtitle_title_drift",
            "newly-proposed title shares zero significant tokens with the family-root subtitle",
        )
    return None


def check_page_metadata_consistency(
    page_path: str,
    title: "str | None",
    description: "str | None",
    subtitle: "str | None" = None,
    *,
    source_keywords: "list[str] | None" = None,
    proposed_title: "str | None" = None,
) -> ConsistencyReport:
    """Pure function: runs every consistency check and returns a
    ConsistencyReport (WARN-only findings, never a rejection). `title`/
    `description` are the page's EFFECTIVE post-recommendation values
    (proposed if one exists, else the current value) -- what the page
    would actually carry once this recommendation entry is applied.
    `proposed_title`, used only for the subtitle-drift check, is the
    title's proposed value specifically (None if this entry proposes no
    title change) -- an unchanged title is never "drift".
    """
    findings: "list[ConsistencyFinding]" = []

    f = _check_near_literal_repetition(title, description)
    if f:
        findings.append(f)

    f = _check_source_keyword_in_both(title, description, source_keywords)
    if f:
        findings.append(f)

    f = _check_family_root_subtitle_drift(subtitle, proposed_title)
    if f:
        findings.append(f)

    return ConsistencyReport(findings=findings)


# ---------------------------------------------------------------------------
# Real subtitle loader (the one I/O this module performs)
# ---------------------------------------------------------------------------


def is_family_root_page(page_path: str) -> bool:
    """True if page_path is content/{site}/en/{family}/_index.md -- exactly
    2 path segments after en/ (family, then _index.md), no platform
    component."""
    norm = page_path.replace("\\", "/")
    for site in _FAMILY_ROOT_SITES:
        prefix = f"content/{site}/en/"
        if norm.startswith(prefix):
            rest = norm[len(prefix):]
            parts = rest.split("/")
            return len(parts) == 2 and parts[1] == "_index.md"
    return False


def _read_frontmatter(path: Path) -> "dict | None":
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    if not text.startswith("---"):
        return None
    parts = text.split("---", 2)
    if len(parts) < 3:
        return None
    try:
        fm = yaml.safe_load(parts[1])
    except yaml.YAMLError:
        return None
    return fm if isinstance(fm, dict) else None


def load_current_subtitle(page_path: str, *, repo_root: "Path | None" = None) -> "str | None":
    """The page's real, current frontmatter subtitle -- None unless
    page_path is a family-root page shape AND it carries a non-empty
    string subtitle. Never raises."""
    try:
        if not is_family_root_page(page_path):
            return None
        root = repo_root if repo_root is not None else REPO_ROOT
        p = Path(page_path)
        abs_path = p if p.is_absolute() else (root / p)
        fm = _read_frontmatter(abs_path)
        subtitle = fm.get("subtitle") if fm else None
        return subtitle if isinstance(subtitle, str) and subtitle.strip() else None
    except Exception:
        return None
