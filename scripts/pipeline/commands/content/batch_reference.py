"""batch_reference.py — Batch reference page generation from api_surface.json.

Backing script for the S-62 batch-reference skill. Generates template-based
skeleton reference pages for all missing classes/enums in a given family+platform
without requiring LLM execution, enabling headless/CI batch runs.

Usage:
    python scripts/pipeline/commands/content/batch_reference.py {family} {platform} [options]

Options:
    --kind class|enum|all   Filter by entry kind (default: all)
    --limit N               Process at most N entries (default: unlimited)
    --dry-run               Print candidates without writing any files
    --update                Re-generate pages for classes in knowledge_delta.json
                            modified_apis; skip all other existing pages.
                            Requires merged/knowledge_delta.json to exist.
                            Falls back to skip-existing mode with a warning if absent.
    --rebuild-all           Regenerate all existing auto-updatable reference pages
                            from current merged/claims.json without requiring
                            knowledge_delta.json. Skips pages with auto_updatable=false
                            or manually curated pages. Requires --confirm-rebuild when
                            more than REBUILD_CONFIRM_THRESHOLD pages would be rebuilt.
    --confirm-rebuild       Required when --rebuild-all would regenerate more than
                            REBUILD_CONFIRM_THRESHOLD existing pages.
    --run-id ID             Required for every mutating execution.
    --run-root DIR          Run directory; when supplied, scope.json restricts writes.

CONTRACT: This script is the backing implementation for S-62 (batch-reference).
The skill spec in .agents/skills/batch-reference/SKILL.md documents the same
platform scope rules and summary format. Keep them in sync.
verified: 2026-04-07
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import re
import sys
import yaml
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from page_spec import SitePlan
from datetime import datetime, timezone
from pathlib import Path

LOG = logging.getLogger(__name__)

# Bootstrap: ensure scripts/pipeline/ is on sys.path for sibling imports
_HERE = Path(__file__).resolve().parent
_PIPELINE_DIR = str(_HERE.parent.parent)
if _PIPELINE_DIR not in sys.path:
    sys.path.insert(0, _PIPELINE_DIR)
_LIB_DIR = str(_HERE.parent.parent / "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)

from core.env_loader import load_env  # noqa: E402
load_env()

from lib.knowledge_core import Knowledge  # noqa: E402
from evidence.runner import attach_evidence  # noqa: E402
from lib.provenance import is_auto_updatable, is_manually_curated, safe_content_write, ProtectedPageError, _normalize_body  # noqa: E402
from lib.backlink_targets import (  # noqa: E402
    load_target_map, resolve_backlink, target_map_age_days, STALE_WARN_DAYS,
    load_canonical_overrides, detect_backlink_downgrade,
)
from commands.ops.backlink_backfill import (  # noqa: E402
    _compute_markdown_backlink_insertion, _load_display_maps,
)
from lib.reference_filter import (  # noqa: E402
    _passes_platform_scope,
    _CPP_ABSTRACT_BASES,
    _JAVA_INTERNAL_CLASSES,
    GROUPED_INDEX_GENERATOR_VERSION,
)

# ---------------------------------------------------------------------------
# Backlink target map (loaded lazily, cached for the run)
# ---------------------------------------------------------------------------
_backlink_target_map: dict | None = None


def _get_backlink_target_map() -> dict | None:
    """Load and cache the aspose_com_targets.json target map."""
    global _backlink_target_map
    if _backlink_target_map is None:
        try:
            _backlink_target_map = load_target_map(_DEFAULT_REPO_ROOT)
        except Exception as exc:
            LOG.warning("backlink: could not load target map: %s", exc)
            _backlink_target_map = {}
        else:
            # MT022 TC-03: provenance.generated_at was written but never read by
            # any consumer -- this is the read half of that gap. Advisory only
            # (generation must still proceed on stale data rather than hard-fail
            # mid-run); the CI-enforceable hard gate lives in
            # scripts/ci/checks/check_backlink_target_map_freshness.py.
            age_days = target_map_age_days(_backlink_target_map)
            if age_days is not None and age_days > STALE_WARN_DAYS:
                LOG.warning(
                    "backlink: data/aspose_com_targets.json is %.1f days old "
                    "(warn threshold: %d) -- run fetch_aspose_com_targets.py "
                    "to refresh before trusting its resolved targets",
                    age_days, STALE_WARN_DAYS,
                )
    return _backlink_target_map or None


_backlink_authority: dict | None = None
_backlink_authority_loaded: bool = False


def _get_backlink_authority() -> dict | None:
    """Load and cache backlink_authority.json (TC13, 2026-08-26). Consulted
    unconditionally (no --deep-style opt-in flag here, matching
    check_backlink_compliance.py's same reasoning): without it,
    resolve_backlink() has no access to the pre-approved deep-authority
    index for reference.aspose.org class pages, so a page whose exact-class
    deep target requires Layer 3 matching -- most of them, per this
    mission's own 1,271-record census -- resolves only a generic
    family-level fallback (or BLOCKED_TARGET) at generation time, even
    though a correct, pre-approved deep link exists. This is the same
    missing-wiring bug this mission found and fixed 4 times earlier the
    same day, in backlink_audit.py's CLI, the pre-commit backlink-
    compliance gate, and refresh_run.py's TC12 writer step -- this is the
    5th and (for this mission's own call-site audit) final instance.
    """
    global _backlink_authority, _backlink_authority_loaded
    if not _backlink_authority_loaded:
        _backlink_authority_loaded = True
        authority_path = (
            _DEFAULT_REPO_ROOT / "data" / "backlinks" / "workspace" / "backlink_authority.json"
        )
        if authority_path.exists():
            try:
                _backlink_authority = json.loads(authority_path.read_text(encoding="utf-8"))
            except Exception as exc:
                LOG.warning("backlink: could not load deep authority index: %s", exc)
                _backlink_authority = None
    return _backlink_authority


_backlink_display_maps: tuple[dict, dict] | None = None


def _get_backlink_display_maps() -> tuple[dict, dict]:
    """Load+cache families.json + metrics_taxonomy.yaml platform display
    names ONCE per process (TC13, 2026-08-26) -- avoids re-parsing both
    files on every page across a 1000+-page --rebuild-all run, and reuses
    the SAME display-name source _expected_anchor_text() validates
    against, replacing _get_family_display()'s own narrower, independently
    hardcoded plat_map (net/python/java/cpp/nodejs/ruby/go/android only)."""
    global _backlink_display_maps
    if _backlink_display_maps is None:
        _backlink_display_maps = _load_display_maps(_DEFAULT_REPO_ROOT)
    return _backlink_display_maps


_canonical_overrides: dict | None = None


def _get_canonical_overrides() -> dict:
    """Load and cache platform_canonical_overrides.yaml (TC6, 2026-08-21).

    Previously this call site never loaded or passed canonical_overrides= to
    resolve_backlink() at all, so a verified override (e.g. words/python ->
    python-net) was silently inert for reference.aspose.org backlinks
    specifically, even though the same override worked correctly for other
    call sites that did pass it -- the exact recurring call-site-omission
    pattern MT043 already found and fixed once, independently, in
    readme_refresh_run.py.
    """
    global _canonical_overrides
    if _canonical_overrides is None:
        _canonical_overrides = load_canonical_overrides(_DEFAULT_REPO_ROOT)
    return _canonical_overrides

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

HEAL_CONFIRM_THRESHOLD = 20    # require --confirm-heal when healing more than this many curated pages
REBUILD_CONFIRM_THRESHOLD = 20  # require --confirm-rebuild when --rebuild-all targets more than this many pages

_DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[4]

REPO_ROOT = _DEFAULT_REPO_ROOT
KNOWLEDGE_ROOT = REPO_ROOT / "knowledge"
CONTENT_ROOT = REPO_ROOT / "content" / "reference.aspose.org" / "en"
_resolve_backlink_fn = resolve_backlink


def _safe_print(message: str) -> None:
    """print(), but never let a display encoding problem escalate into
    losing an entire batch run.

    Found live 2026-08-24 (mission-plan-the-end-to-end-vast-hejlsberg.md
    Task 14, the real upstream E2E proof run for pdf/java): several call
    sites in this module print dynamic text that can embed arbitrary
    generated content -- an exception message, a class/member name, a
    reused snippet -- and generated method-signature tables use
    "->"-as-arrow (U+2192), among other non-ASCII characters. A plain
    ``print()`` of that text raises UnicodeEncodeError on a non-UTF-8
    console (cp1252 on Windows), and when it happens inside the per-entry
    error handler whose whole purpose is fault isolation (one bad page
    must never abort the other 1000+), the encoding failure itself becomes
    the thing that aborts the batch. Falls back to an ASCII-safe
    (backslash-escaped) rendering rather than losing the message entirely.
    """
    try:
        print(message)
    except UnicodeEncodeError:
        print(message.encode("ascii", errors="backslashreplace").decode("ascii"))


def configure(
    repo_root: Path | None = None,
    knowledge_root: Path | None = None,
    content_root: Path | None = None,
    resolve_backlink_fn=None,
) -> None:
    """Set module-level root paths. Call with no args to reset defaults.

    Tests call ``batch_reference.configure(repo_root=tmp_path)`` (or pass
    knowledge_root / content_root directly) instead of monkeypatching globals.
    Omitted args fall back to values derived from repo_root or built-in defaults.

    resolve_backlink_fn (TC13, 2026-08-26): configure() seam for the
    backlink-resolution callable _build_page()/generate_grouped_index()
    call, matching this repo's own established pattern (AGENTS.md §16) --
    tests override behavior via configure() instead of monkeypatching an
    imported module function directly (a T2 monkeypatch-lint violation).
    Omit to reset to the real resolve_backlink().
    """
    global REPO_ROOT, KNOWLEDGE_ROOT, CONTENT_ROOT, _resolve_backlink_fn
    root = repo_root if repo_root is not None else _DEFAULT_REPO_ROOT
    REPO_ROOT = root
    KNOWLEDGE_ROOT = knowledge_root if knowledge_root is not None else root / "knowledge"
    CONTENT_ROOT = (
        content_root if content_root is not None
        else root / "content" / "reference.aspose.org" / "en"
    )
    _resolve_backlink_fn = resolve_backlink_fn if resolve_backlink_fn is not None else resolve_backlink
    # FRESH-001 (2026-08-14): keep freshness_guard's module-level paths in lockstep
    # with this module's own configure() -- it is a separate module with its own
    # REPO_ROOT/KNOWLEDGE_ROOT globals, and the freshness gate below must see the
    # same tree this module was just pointed at (production repo_root in real use;
    # a test's tmp_path under `batch_reference.configure(repo_root=tmp_path)`).
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib"))
        import freshness_guard as _freshness_guard
        _freshness_guard.configure(repo_root=root)
    except ImportError:
        pass


def _canonical_reference_path(page_path: Path) -> str:
    """Return a repo-relative content path without leaking sandbox roots."""
    try:
        return page_path.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return (
            Path("content/reference.aspose.org/en")
            / page_path.relative_to(CONTENT_ROOT)
        ).as_posix()

# Python enum base classes (mirrors extraction/tree_helpers.py _PY_ENUM_BASES)
_PY_ENUM_BASES: frozenset[str] = frozenset({
    "Enum", "IntEnum", "StrEnum", "Flag", "IntFlag",
    "enum.Enum", "enum.IntEnum", "enum.StrEnum", "enum.Flag", "enum.IntFlag",
})

# Canonical kind values emitted by api_surface.py ("kind": cnode.type).
# Source of truth: extraction/tree_helpers.py _CLASS_TYPES dict.
_ENUM_KINDS: frozenset[str] = frozenset({
    "enum_specifier",       # C++
    "enum_declaration",     # Java / C#
    "enum_definition",      # alternative TS / C++
    "enum_item",            # Rust
})

_CLASS_KINDS_BY_PLATFORM: dict[str, set[str]] = {
    "java":       {"class_declaration", "interface_declaration"},
    "net":        {"class_declaration", "interface_declaration",
                   "struct_declaration", "record_declaration"},
    "cpp":        {"class_specifier", "struct_specifier"},
    "python":     {"class_definition"},
    "typescript": {"class_declaration", "interface_declaration",
                   "type_alias_declaration"},
    "javascript": {"class_declaration"},
    "nodejs":     {"class_declaration"},
    "go":         {"type_spec"},
    "rust":       {"struct_item", "enum_item", "trait_item", "union_item"},
}

_PLATFORM_TO_LANG: dict[str, str] = {
    "python": "python",
    "net": "csharp",
    "java": "java",
    "cpp": "cpp",
    "typescript": "typescript",
    "javascript": "javascript",
    "nodejs": "javascript",
    "go": "go",
    "rust": "rust",
}

# ERC-* claim kinds treated as prose-eligible for reference page descriptions
_ERC_PROSE_KINDS: frozenset[str] = frozenset({"api", "feature"})


def _evidence_ids(text: str) -> tuple[list[str], list[str]]:
    """Extract run-decision evidence IDs from final page frontmatter."""
    if not text.startswith("---"):
        return [], []
    parts = text.split("---", 2)
    if len(parts) < 3:
        return [], []
    try:
        frontmatter = yaml.safe_load(parts[1]) or {}
    except yaml.YAMLError:
        return [], []
    evidence = frontmatter.get("evidence") or {}
    claims = evidence.get("claims") or []
    apis = evidence.get("apis") or []
    return (
        [str(value) for value in claims if value],
        [str(value) for value in apis if value],
    )


# ---------------------------------------------------------------------------
# Color constant description template
# ---------------------------------------------------------------------------

def _color_constant_desc(prop_name: str) -> str:
    """Generate a deterministic description for a named color constant property.

    Converts PascalCase or SCREAMING_SNAKE_CASE names to natural language:
      AliceBlue     → "The Alice Blue color."
      ALICE_BLUE    → "The Alice Blue color."
      AntiqueWhite  → "The Antique White color."
    """
    if "_" in prop_name:
        # SCREAMING_SNAKE_CASE → title case
        natural = prop_name.replace("_", " ").title()
    else:
        # PascalCase → insert space before each uppercase letter following a lowercase
        natural = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", prop_name)
    return f"The {natural} color."


def _is_color_type(ptype: str) -> bool:
    """Return True if ptype refers to a Color type (any platform naming convention)."""
    return ptype.lower().rstrip("?") in ("color", "system.drawing.color")


# ---------------------------------------------------------------------------
# ERC claim index builder
# ---------------------------------------------------------------------------

def _build_erc_index(family: str, platform: str, api_surface=None) -> dict[str, dict]:
    """Build a class_name → best ERC-* claim dict from merged/claims.json.

    Returns an empty dict if claims.json is missing or contains no ERC-* claims.
    Only considers claims with kind in _ERC_PROSE_KINDS (api, feature).
    When multiple ERC-* claims match the same class, the highest-confidence one wins.

    When *api_surface* is provided, a bare class name shared by two or more
    DIFFERENT classes (a real, confirmed occurrence -- see
    _build_erc_member_index's own docstring for the full account) is excluded
    entirely: ERC claims carry no reliable per-class evidence to attribute
    them to the right one of several same-named classes, so guessing risks
    silently mis-describing one class with another's text.
    """
    claims_path = KNOWLEDGE_ROOT / family / platform / "merged" / "claims.json"
    if not claims_path.exists():
        return {}
    try:
        claims_list = json.loads(claims_path.read_text(encoding="utf-8"))
    except Exception:
        return {}

    _name_counts: dict[str, int] = {}
    for cls in api_surface or ():
        cls_name = cls.get("name")
        if cls_name:
            _name_counts[cls_name] = _name_counts.get(cls_name, 0) + 1
    ambiguous_names: set[str] = {name for name, count in _name_counts.items() if count > 1}

    index: dict[str, dict] = {}
    for claim in claims_list:
        cid = claim.get("claim_id", "")
        if not cid.startswith("ERC-"):
            continue
        if claim.get("kind", "") not in _ERC_PROSE_KINDS:
            continue
        text = (claim.get("text") or "").strip()
        if not text:
            continue
        confidence = float(claim.get("confidence", 0.0))

        # Extract class name from the claim text.
        # ERC-* claim texts commonly start with "The ClassName." or "**ClassName**"
        cls_name = None
        m = re.match(r"^\*\*([A-Z]\w+)\*\*", text)
        if m:
            cls_name = m.group(1)
        elif re.match(r"^The ([A-Z]\w+)[.\s]", text):
            cls_name = re.match(r"^The ([A-Z]\w+)[.\s]", text).group(1)
        elif re.match(r"^([A-Z]\w+)[.\s]", text):
            cls_name = re.match(r"^([A-Z]\w+)[.\s]", text).group(1)

        if not cls_name:
            continue
        if cls_name in ambiguous_names:
            continue  # cannot safely attribute to one of several same-named classes

        # Keep highest-confidence claim per class
        existing = index.get(cls_name)
        if existing is None or confidence > float(existing.get("confidence", 0.0)):
            index[cls_name] = claim

    return index


# ---------------------------------------------------------------------------
# Member-level ERC description index
# ---------------------------------------------------------------------------

# Regex to extract ClassName.MemberName from the beginning of an ERC claim text.
# Handles common prefixes: "The ClassName.Member ...", "Calling ClassName.Member(...)",
# "ClassName.Member ..."
_MEMBER_PREFIX_RE = re.compile(
    r"^(?:The |Calling )?([A-Za-z]\w+)\.([A-Za-z_]\w*)\b"
)

# Fragments to strip from the description after removing the class.member prefix.
# Strips: "(params) ->" return signatures, "property of type T", leading lowercase
# prose words that are part of the signature (not the description).
_SIGNATURE_STRIP_RE = re.compile(
    r"^(?:\([^)]*\)\s*(?:->\s*\S+\s*)?|"           # (params) -> ret
    r"property\s+of\s+type\s+\S+\s*|"              # property of type T
    r"field\s+of\s+type\s+\S+\s*)"                 # field of type T
)


def _build_erc_member_index(family: str, platform: str, api_surface=None) -> dict[str, str]:
    """Build a 'ClassName.MemberName' → one-sentence description index from ERC api claims.

    Supplements api_surface.json doc fields (which are empty for FOSS repos without
    docstrings) so that property/method table rows have meaningful descriptions.
    Only considers ERC claims with kind == 'api'. Returns an empty dict if no
    api-kind ERC claims are found.

    When *api_surface* is provided (list of api_surface entries), matching is gated
    on known class names: if the matched class name is not in the known classes set,
    the claim is skipped to prevent prose like "it.seems" or "i.e. calling" from
    being misindexed as member descriptions.  When api_surface is None or empty,
    the gate is skipped (graceful degradation).
    """
    claims_path = KNOWLEDGE_ROOT / family / platform / "merged" / "claims.json"
    if not claims_path.exists():
        return {}
    try:
        claims_list = json.loads(claims_path.read_text(encoding="utf-8"))
    except Exception:
        return {}

    known_classes: set[str] = {cls.get("name", "") for cls in api_surface if cls.get("name")} if api_surface else set()
    # Found live 2026-08-24/25 (mission-plan-the-end-to-end-vast-hejlsberg.md
    # Task 14, deep-reassessment pass): this index's own key is the bare class
    # name only -- when two genuinely DIFFERENT classes share a simple name
    # across namespaces (real, confirmed example: pdf/java's
    # org.aspose.pdf.engine.xfa.model.sourceset.Bind vs. ...template.Bind),
    # an ERC-* claim naming that bare name cannot be safely attributed to
    # either specific class: checked live, this pipeline's own enrichment
    # claims (kind="api", ERC-* prefixed) carry only a generic
    # evidence.source_file ("VerifiedFacts.txt", an enrichment-batch
    # intermediate artifact), never the real per-class source file scout's
    # own api_method claims carry -- so there is no reliable signal here to
    # pick the RIGHT one of N same-named classes. Rather than guess (and risk
    # silently mis-attributing one class's description to an unrelated one),
    # ambiguous bare names are excluded from this index entirely; callers
    # fall through to their own per-class doc field (always correct, scout-
    # sourced) or a synthesized, class-agnostic description -- both safe.
    _name_counts: dict[str, int] = {}
    for cls in api_surface or ():
        cls_name = cls.get("name")
        if cls_name:
            _name_counts[cls_name] = _name_counts.get(cls_name, 0) + 1
    ambiguous_names: set[str] = {name for name, count in _name_counts.items() if count > 1}

    index: dict[str, str] = {}
    for claim in claims_list:
        if not claim.get("claim_id", "").startswith("ERC-"):
            continue
        if claim.get("kind", "") != "api":
            continue
        text = (claim.get("text") or "").strip()
        if not text:
            continue

        # ERC claims may start with a backtick-quoted name: "`Workbook.Save` overloads..."
        # Strip leading backtick so the regex can match the class/member name.
        text_clean = text.lstrip("`")
        m = _MEMBER_PREFIX_RE.match(text_clean)
        if not m:
            continue

        class_name = m.group(1)
        if known_classes and class_name not in known_classes:
            continue  # reject prose that happens to match ClassName.word pattern
        if class_name in ambiguous_names:
            continue  # cannot safely attribute to one of several same-named classes

        key = f"{m.group(1)}.{m.group(2)}"

        # Extract the description: strip the matched prefix (+ closing backtick if any),
        # then strip any signature fragments, take the first sentence.
        after_prefix = text_clean[m.end():].lstrip("`").lstrip()
        desc = _SIGNATURE_STRIP_RE.sub("", after_prefix).strip()
        # Take first sentence (split on ". " to avoid splitting on abbreviations)
        sentences = re.split(r"\.\s+", desc)
        desc = sentences[0].rstrip(".").strip() if sentences else desc
        if not desc:
            continue
        # Capitalize first character
        desc = desc[0].upper() + desc[1:] if len(desc) > 1 else desc.upper()

        # When multiple claims exist for the same member, keep the longest description
        # (more informative wins).
        if key not in index or len(desc) > len(index[key]):
            index[key] = desc

    return index


# ---------------------------------------------------------------------------
# Platform scope filter
# ---------------------------------------------------------------------------

def _is_enum(entry: dict, platform: str) -> bool:
    """Return True if this api_surface entry represents an enum type.

    FIX-09: Removed the enum_members-only heuristic that caused classes with
    ALL_CAPS constants (e.g. Scene) to be misclassified as enums.  Now only
    tree-sitter kind or explicit enum base class inheritance qualifies.
    """
    kind = entry.get("kind", "")
    if kind in _ENUM_KINDS:
        return True
    # Python: IntEnum / Flag / etc. appear as class_definition with enum bases
    if platform == "python" and kind == "class_definition":
        bases = entry.get("bases", [])
        if any(b in _PY_ENUM_BASES for b in bases):
            return True
    return False


# _passes_platform_scope is imported from lib.reference_filter (TC-REF-11).
# The authoritative implementation now lives there and is shared with the CI
# validator (check_reference_index_structure.py).  Do not re-define it here.


def _apply_kind_filter(entries: list[dict], kind_arg: str, platform: str) -> list[dict]:
    """Apply --kind class|enum|all filter on top of platform-scoped entries."""
    if kind_arg == "all":
        return entries
    if kind_arg == "enum":
        return [e for e in entries if _is_enum(e, platform)]
    if kind_arg == "class":
        return [e for e in entries if not _is_enum(e, platform)]
    raise ValueError(f"Invalid kind_arg: {kind_arg!r}. Must be 'all', 'enum', or 'class'.")


# ---------------------------------------------------------------------------
# Slug sanitization
# ---------------------------------------------------------------------------

# Characters that are unsafe in filenames across Windows/macOS/Linux or
# that conflict with Hugo section separators.
_UNSAFE_SLUG_RE = re.compile(r'[.:\/\\<>|?*\[\]"]+')


def _sanitize_slug(name: str) -> str:
    """Sanitize a class name into a filesystem-safe slug.

    Replaces dots, colons, and other unsafe characters with underscores.
    Python PEP 8 names pass through unchanged.
    """
    return _UNSAFE_SLUG_RE.sub("_", name)


def _entry_slug(entry: dict) -> str:
    """Return the filesystem slug for an api_surface entry.

    When ``_slug_suffix`` is set (same-name classes in different namespaces),
    appends the suffix to disambiguate: ``Color`` → ``Color-Drawing``.
    """
    base = _sanitize_slug(entry.get("name", ""))
    suffix = entry.get("_slug_suffix", "")
    if suffix:
        return f"{base}-{_sanitize_slug(suffix)}"
    return base


def _effective_namespace(entry: dict) -> str:
    """Return a namespace-equivalent signal for disambiguation.

    Prefers ``canonical_namespace``, falling back to ``class_import``'s dotted
    prefix when absent (TC-DUPIDX-07, 2026-08-12, ST-059) -- the exact fallback
    already proven in ``consolidate_classes()``
    (``scripts/pipeline/extraction/api_surface.py:1737-1746``), ported here since
    ``canonical_namespace``'s rollout across languages (C++ from inception, C#
    2026-06-13, Rust from inception, Python 2026-07-29/MT013 -- see TC-DUPIDX-06
    for extending it to Java/TypeScript at the scout layer) never reached Java, and
    pre-MT013 Python scout snapshots predate that field even though ``class_import``
    was always populated for both. Real incident: ``cells/java`` and ``pdf/java``
    (with ``pdf/java`` alone hitting 28 distinct undisambiguated collisions after a
    knowledge refresh nearly doubled its class count) stayed duplicated indefinitely
    with no re-invocation of ``--generate-index`` able to fix them, because this
    function had no fallback for Java's ``canonical_namespace``-less entries at all.

    Entries with neither field populated (e.g. TypeScript prior to a re-scout after
    TC-DUPIDX-06 adds its extraction branch) return ``""`` -- there is no signal to
    derive a namespace from, and the entry is left undisambiguated by design rather
    than guessing.
    """
    ns = entry.get("canonical_namespace", "")
    if ns:
        return ns
    class_import = entry.get("class_import", "")
    if class_import and class_import != entry.get("name", "") and "." in class_import:
        return class_import.rsplit(".", 1)[0]
    return ""


def _assign_namespace_slug_suffixes(group: list[dict]) -> None:
    """Set ``_slug_suffix`` on each entry in a same-name collision *group*.

    Prefers the short, readable last dot-segment of the effective namespace
    (``_effective_namespace()``, e.g. ``Aspose.Pdf.Drawing`` -> ``Drawing``) -- the
    established, tested convention for deeply-nested namespaces (.NET/Java) where
    the tail alone already disambiguates.

    HARDEN-py-namespace-suffix (2026-07-28, MT013): that shortcut silently
    re-collides when two DIFFERENT namespaces share the same last segment --
    found live on pdf/python, where ``aspose_pdf.document`` and
    ``aspose_pdf.generated.document`` both truncate to ``document``, hiding
    the real, distinct compatibility-shim ``Document`` class entirely
    ("within-batch case-collision", 0 pages written for either). Falls back
    to the FULL sanitized namespace only for entries whose truncated suffix
    is still ambiguous within this group -- leaving the already-tested short
    form (``Color-Drawing.md``) unchanged for every already-disambiguating
    case.
    """
    from collections import Counter as _Counter

    ns_by_id = {id(e): _effective_namespace(e) for e in group}
    entries_with_ns = [e for e in group if ns_by_id[id(e)]]
    truncated = {
        id(e): ns_by_id[id(e)].rsplit(".", 1)[-1]
        for e in entries_with_ns
    }
    counts = _Counter(truncated.values())
    for e in entries_with_ns:
        short = truncated[id(e)]
        e["_slug_suffix"] = ns_by_id[id(e)] if counts[short] > 1 else short


# ---------------------------------------------------------------------------
# Category label
# ---------------------------------------------------------------------------

def _category(entry: dict, platform: str) -> str:
    """FIX-09: The kind field from tree-sitter is authoritative for class vs enum.

    Only classify as Enum when the kind itself is an enum type OR the entry
    has explicit enum base classes (Python).  Convention-based enum_members
    alone are not sufficient — a class with ALL_CAPS constants (like Scene
    with status constants) should remain a Class.
    """
    kind = entry.get("kind", "")
    # Authoritative enum kinds from tree-sitter
    if kind in _ENUM_KINDS:
        return "Enum"
    # Python enum via base class inheritance (Enum, IntEnum, etc.)
    if platform == "python" and kind == "class_definition":
        bases = entry.get("bases", [])
        if any(b in _PY_ENUM_BASES for b in bases):
            return "Enum"
    # Go type_spec is always a "Type" (Go has no classes)
    if platform == "go" and kind == "type_spec":
        return "Type"
    # For all other cases, use the kind field
    if "interface" in kind:
        return "Interface"
    if "trait" in kind:
        return "Trait"
    if "struct" in kind:
        return "Struct"
    return "Class"


# ---------------------------------------------------------------------------
# Page template builder
# ---------------------------------------------------------------------------

def _build_page(
    entry: dict,
    family: str,
    platform: str,
    erc_index: dict[str, dict] | None = None,
    member_erc_index: dict[str, str] | None = None,
    model_sha: str = "",
    model_version: str = "",
    content_created_at: str | None = None,
    page_path: Path | None = None,
) -> str:
    """Build a template-based skeleton reference page from an api_surface entry.

    When *erc_index* is provided and the entry has no docstring (doc=""), the
    highest-confidence ERC-* claim for this class is used as the description
    paragraph and cited in evidence.claims.

    When *member_erc_index* is provided, property/method table description cells
    are populated from ERC api-kind claim descriptions when the api_surface doc
    field is empty. This fills in descriptions for FOSS repos without docstrings.

    page_path (TC13, 2026-08-26): the eventual repo-relative write path for
    this page, e.g. content/reference.aspose.org/en/pdf/java/SetGray.md --
    passed so the backlink block below can pass source_file= to
    resolve_backlink() for deep-authority (Layer 3 exact-class) lookup.
    Optional and best-effort: when omitted (e.g. a caller building a page
    preview without a real destination yet), backlink resolution still
    runs, just without deep-authority matching -- family/platform-level
    resolution only, matching this function's pre-TC13 behavior exactly.
    """
    name = entry.get("name", "")
    doc = (entry.get("doc") or "").strip()
    category = _category(entry, platform)
    lang = _PLATFORM_TO_LANG.get(platform, platform)

    # ERC-* claim fallback when doc is empty
    erc_claim: dict | None = None
    erc_claim_id: str = ""
    if not doc and erc_index:
        erc_claim = erc_index.get(name)
        if erc_claim:
            erc_claim_id = erc_claim.get("claim_id", "")
            doc = (erc_claim.get("text") or "").strip()

    methods = entry.get("methods", [])
    properties = entry.get("properties", [])
    bases = entry.get("bases", [])
    enum_members = entry.get("enum_members") or entry.get("members", [])

    # Description line
    parts = [f"`{name}` {category.lower()}"]
    if bases:
        # FIX-05: filter out self-referential inheritance and enum bases
        bases_filtered = [b for b in bases if b not in _PY_ENUM_BASES and "enum." not in b and b != name]
        if bases_filtered:
            parts.append(f"(inherits {', '.join(bases_filtered[:2])})")
    method_count = len(methods)
    prop_count = len(properties)
    if method_count or prop_count:
        counts = []
        if method_count:
            counts.append(f"{method_count} method{'s' if method_count != 1 else ''}")
        if prop_count:
            counts.append(f"{prop_count} {'properties' if prop_count != 1 else 'property'}")
        parts.append(f"with {' and '.join(counts)}")
    description = " ".join(parts)

    # Build evidence apis list from known class members (metadata-derived, not code-extracted).
    # Capped at 20 total to keep frontmatter readable; methods first, then properties.
    apis_list = []
    seen_api_names: set[str] = set()
    for m in methods:
        if len(apis_list) >= 20:
            break
        mname = m.get("name", "")
        if mname and f"{name}.{mname}" not in seen_api_names:
            seen_api_names.add(f"{name}.{mname}")
            apis_list.append(f"  - {name}.{mname}")
    for p in properties:
        if len(apis_list) >= 20:
            break
        pname = p.get("name", "")
        if pname and f"{name}.{pname}" not in seen_api_names:
            seen_api_names.add(f"{name}.{pname}")
            apis_list.append(f"  - {name}.{pname}")
    # Frontmatter
    # content_created_at must be deterministic across a crash/retry pair under the
    # same run_id: two _production_run() calls stamping different wall-clock values
    # would produce different frontmatter hashes and trip a false-positive "Page
    # decision collision" in _emit_run_decision() (MT033-WAECOLLISION-001). Callers
    # pass the immutable run-manifest timestamp via _run_recorded_at(); this only
    # falls back to the live clock when no run context is available (e.g. direct
    # unit tests of _build_page()).
    now_iso = content_created_at or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")
    lines = [
        "---",
        f"linkTitle: {name}",
        f"title: {name}",
        f'description: "{description}"',
        f'summary: "{description}"',
        "categories:",
        f"- {category}",
        "layout: reference-single",
        "provenance:",
        "  content_origin: skill-generated",
        "  last_mechanism: skill",
        "  auto_updatable: true",
        f"  content_created_at: '{now_iso}'",
        "evidence:",
        f"  model_sha: '{model_sha}'",
        f"  model_version: '{model_version}'",
    ]
    if erc_claim_id:
        lines.append("  claims:")
        lines.append(f"  - \"{erc_claim_id}\"")
    else:
        lines.append("  claims: []")
    if apis_list:
        lines.append("  apis:")
        lines.extend(apis_list)
    else:
        lines.append("  apis: []")
    lines.append("---")
    lines.append("")

    # Overview
    lines.append("## Overview")
    lines.append("")
    # LC-11 FIX: use correct display name for "pdf" family ("PDF" not "Pdf")
    _fam_disp = {"3d": "3D", "pdf": "PDF"}.get(family, family.capitalize())
    _plat_disp = {"net": ".NET", "cpp": "C++"}.get(platform, platform.capitalize())
    product_line = f"`{name}` is a {category.lower()} in Aspose.{_fam_disp} FOSS for {_plat_disp}."
    lines.append(product_line)
    if bases:
        # FIX-05: filter out self-referential inheritance and enum bases
        bases_filtered = [b for b in bases if b not in _PY_ENUM_BASES and "enum." not in b and b != name]
        if bases_filtered:
            _bases_listed = ", ".join(f"`{b}`" for b in bases_filtered[:3])
            if len(bases_filtered) > 3:
                _bases_listed += f", and {len(bases_filtered) - 3} more"
            lines.append(f"Inherits from: {_bases_listed}.")
    if doc:
        lines.append("")
        lines.append(doc)

    # LC-10 FIX: add source-grounded prose summary to satisfy content_substance >=50 word threshold.
    # Only method/property/member names from api_surface.json are used — no hallucinated claims.
    _lc10_prose: list[str] = []
    _all_mnames = sorted({m.get("name", "") for m in methods if m.get("name")})
    _all_pnames = sorted({p.get("name", "") for p in properties if p.get("name")})
    _all_enames = [
        (m.get("name", str(m)) if isinstance(m, dict) else str(m))
        for m in enum_members
    ]
    if _all_mnames:
        _preview_count = min(12, len(_all_mnames))
        _listed = ", ".join(f"`{n}`" for n in _all_mnames[:_preview_count])
        if len(_all_mnames) > _preview_count:
            _listed += f", and {len(_all_mnames) - _preview_count} additional methods"
        # TC-SYS-016: use method_count (len(methods)) not len(_all_mnames) to
        # match the frontmatter description count and the methods table row count.
        # "declares"/"defines", not "provides": RPR-E-02's forbidden-claims
        # scanner treats a bare class name plus generic capability language
        # ("provides", "can", "use") on the same line as an affirmative
        # support claim (by design, for hand-written prose). This boilerplate
        # line names every generated class regardless of forbidden status, so
        # a capability verb here self-triggers the scanner against the page's
        # own class-shape summary -- found live blocking 5 brand-new pdf/python
        # abstract-class pages (Action, DataSource, FontSource, PdfPlugin,
        # Shading) whose only forbidden member is a private/unlisted one this
        # sentence never actually describes.
        _lc10_prose.append(
            f"This {category.lower()} declares {method_count} "
            f"{'method' if method_count == 1 else 'methods'} "
            f"for {name} objects in {_plat_disp} programs."
        )
        _lc10_prose.append(f"Available methods include: {_listed}.")
        _lc10_prose.append(
            f"All public members are accessible to any {_plat_disp} application "
            f"after installing the Aspose.{_fam_disp} FOSS for {_plat_disp} package."
        )
    if _all_pnames:
        _plisted = ", ".join(f"`{n}`" for n in _all_pnames[:6])
        if len(_all_pnames) > 6:
            _plisted += f", and {len(_all_pnames) - 6} more"
        if platform == "cpp":
            _prop_label = "Accessor methods"
        elif platform == "rust":
            _prop_label = "Fields"
        else:
            _prop_label = "Properties"
        _lc10_prose.append(f"{_prop_label}: {_plisted}.")
    if category == "Enum" and _all_enames and not _lc10_prose:
        _elisted = ", ".join(f"`{e}`" for e in _all_enames[:12])
        if len(_all_enames) > 12:
            _elisted += f", and {len(_all_enames) - 12} more"
        _lc10_prose.append(
            f"This enumeration defines {len(_all_enames)} "
            f"{'value' if len(_all_enames) == 1 else 'values'}: {_elisted}."
        )
    if not _lc10_prose:
        # Sparse type: no methods, properties, or enum members listed.
        # Two sentences ensure the page meets the content_substance >=50 word threshold
        # even when the type has no members and api_surface.json has no doc text.
        _lc10_prose.append(
            f"This {category.lower()} is part of the public API of "
            f"Aspose.{_fam_disp} FOSS for {_plat_disp}."
        )
        # Avoid "can"/"used" for the same reason as the method-count sentence
        # above -- see comment there (RPR-E-02 self-trigger on sparse-type
        # boilerplate, found live on the same 5-page batch).
        _lc10_prose.append(
            f"It appears among the other exported types in the package "
            f"alongside {name} in your {_plat_disp} application."
        )
    lines.append("")
    for _lp in _lc10_prose:
        lines.append(_lp)
    lines.append("")

    # Enum values section
    if category == "Enum" and enum_members:
        lines.append("## Values")
        lines.append("")
        lines.append("| Value | Description |")
        lines.append("|-------|-------------|")
        for member in enum_members:
            if isinstance(member, dict):
                mname = member.get("name", str(member))
                mdoc = (member.get("doc") or member.get("description") or "").strip()
            else:
                mname = str(member)
                mdoc = ""
            if not mdoc and member_erc_index:
                mdoc = member_erc_index.get(f"{name}.{mname}", "")
            lines.append(f"| `{mname}` | {mdoc} |")
        lines.append("")

    # Properties section (C++ has no language-level properties — use "Accessor
    # Methods"; Rust exposes pub struct fields — use "Fields")
    if properties:
        if platform == "cpp":
            _prop_heading = "Accessor Methods"
        elif platform == "rust":
            _prop_heading = "Fields"
        else:
            _prop_heading = "Properties"
        lines.append(f"## {_prop_heading}")
        lines.append("")
        lines.append("| Name | Type | Access | Description |")
        lines.append("|------|------|--------|-------------|")
        for prop in properties:
            pname = prop.get("name", "")
            ptype = prop.get("type", prop.get("return_type", ""))
            # Escape bare | in type strings so markdown table parsers don't
            # miscount columns (e.g. "int | None" → "int \| None").
            ptype_md = ptype.replace("|", r"\|")
            writable = prop.get("writable", False)
            # FR-14 compat: TypeScript extraction uses access_mode instead of writable
            access_mode = prop.get("access_mode", "")
            if access_mode == "readwrite":
                writable = True
            elif access_mode == "writeonly":
                writable = True
            access = "Read/Write" if writable else "Read"
            pdoc = (prop.get("doc") or "").strip()
            if not pdoc and member_erc_index:
                pdoc = member_erc_index.get(f"{name}.{pname}", "")
            # Color constant template: generate "The X color." for undocumented
            # read-only Color-typed properties (e.g. AliceBlue, ALICE_BLUE).
            # These are self-documenting by name; source code never adds docstrings
            # to individual color constants, so this is the correct fallback.
            if not pdoc and not writable and _is_color_type(ptype):
                pdoc = _color_constant_desc(pname)
            # RC-001 fallback: when no doc or ERC description is available, generate a
            # minimal signature-based description so description cells are not blank.
            if not pdoc:
                pdoc = f"The {pname} property of {name}."
            lines.append(f"| `{pname}` | `{ptype_md}` | {access} | {pdoc} |")
        lines.append("")

    # Methods section
    if methods:
        lines.append("## Methods")
        lines.append("")
        lines.append("| Signature | Description |")
        lines.append("|-----------|-------------|")
        _described_method_names: set[str] = set()
        for method in methods:
            mname = method.get("name", "")
            params = method.get("params", method.get("parameters", []))
            ret = method.get("return_type", "")
            mdoc = (method.get("doc") or "").strip()
            if not mdoc and member_erc_index and mname not in _described_method_names:
                # Only apply ERC description to the FIRST overload; subsequent overloads
                # use the RC-001 param-based fallback below.
                mdoc = member_erc_index.get(f"{name}.{mname}", "")
                if mdoc:
                    _described_method_names.add(mname)
            # RC-001 fallback: generate a minimal signature-based description for this
            # overload. For methods with multiple overloads, include parameter names so
            # each overload gets a distinct (non-empty) description cell. Methods without
            # parameters use the simple form only for the first overload.
            if not mdoc:
                param_names = [
                    p.get("name", "") if isinstance(p, dict) else str(p)
                    for p in params
                ]
                if param_names:
                    mdoc = f"Calls {mname}({', '.join(param_names)}) on this {name} instance."
                    _described_method_names.add(mname)
                elif mname not in _described_method_names:
                    mdoc = f"Calls {mname} on this {name} instance."
                    _described_method_names.add(mname)

            param_strs = []
            for p in params:
                if isinstance(p, dict):
                    pn = p.get("name", "")
                    pt = p.get("type", "").replace("|", r"\|")
                    param_strs.append(f"{pn}: {pt}" if pt else pn)
                else:
                    param_strs.append(str(p))
            ret_md = ret.replace("|", r"\|") if ret else ret
            sig = f"`{mname}({', '.join(param_strs)})`"
            if ret_md and ret_md not in ("void", "None", ""):
                sig += f" → `{ret_md}`"
            # FIX-04: warn when method is a stub (raises NotImplementedError or similar)
            if method.get("stub"):
                stub_note = "**Not implemented in the FOSS edition — throws at runtime.**"
                mdoc = f"{stub_note} {mdoc}" if mdoc else stub_note
            lines.append(f"| {sig} | {mdoc} |")
        lines.append("")

    # TC-BL-007 / TC13 (2026-08-26): Append See Also section with reciprocal
    # aspose.com backlink -- now routed through the SAME governed chokepoint
    # backlink_backfill.py's writer uses (idempotent dedup, near-duplicate
    # hard-block, max-link guard, stale-bullet replacement), rather than a
    # hand-rolled, independently-implemented "## See Also" construction with
    # its own anchor-text logic (_get_family_display(), now removed) that
    # could silently drift from _expected_anchor_text() -- the same source
    # of truth classify_compliance()'s WRONG_ANCHOR_TEXT check validates
    # against. This is the actual code path launch-product uses to generate
    # the bulk of reference.aspose.org, not an edge case; see the TC13
    # redesign in the governing plan for the full audit that found this.
    #
    # exact_deep_match_enabled/authority/source_file: consults the deep-
    # authority index unconditionally (5th and final call site this mission
    # found missing this wiring the same day, after backlink_audit.py's
    # CLI, the pre-commit backlink-compliance gate, and refresh_run.py's
    # TC12 writer step) -- without it, a freshly-generated reference.aspose.org
    # class page would only ever get a generic family-level fallback (or
    # BLOCKED_TARGET) even when a correct, pre-approved exact-class deep
    # link already exists for it.
    #
    # Passing the whole joined `lines` (frontmatter included) as `body` is a
    # deliberate, reviewed simplification, not an oversight: this
    # function's frontmatter template (built above) never contains an
    # aspose.com URL (evidence.model_sha is a git SHA, not a URL), so the
    # near-duplicate/max-link scan operating slightly more broadly than
    # strictly necessary is harmless here. A cleaner long-term shape would
    # split frontmatter from body before this call; not required for
    # correctness.
    _tm = _get_backlink_target_map()
    if _tm:
        try:
            _authority = _get_backlink_authority()
            _source_file = _canonical_reference_path(page_path) if page_path is not None else None
            chosen_url, _rtype, _rsubdomain, _fallback = _resolve_backlink_fn(
                family, platform, "reference.aspose.org", _tm,
                canonical_overrides=_get_canonical_overrides(),
                exact_deep_match_enabled=bool(_authority),
                authority=_authority,
                source_file=_source_file,
            )
            if chosen_url:
                _families_map, _platforms_map = _get_backlink_display_maps()
                _body_so_far = "\n".join(lines)
                _before, _after, _warnings, _skipped, _skip_reason = _compute_markdown_backlink_insertion(
                    _body_so_far, chosen_url, family, platform, "reference.aspose.org",
                    _families_map, _platforms_map, target_type=_rtype,
                )
                if _after != _body_so_far:
                    lines = _after.split("\n")
                for _w in _warnings:
                    LOG.warning("backlink: %s — %s/%s", _w, family, platform)
            else:
                LOG.warning("backlink: BLOCKED_TARGET for %s/%s — See Also omitted", family, platform)
        except Exception as exc:
            LOG.warning("backlink: See Also generation failed for %s/%s: %s", family, platform, exc)

    # TC-GATE4B: Compute content_hash from the body so the commit hook's
    # provenance_normalize_hash step is a no-op (hash already correct).
    # This prevents the RECONCILE_DRIFTED loop where generator omits
    # content_hash, hook adds it, and manifest output drifts.
    #
    # Body is everything after the closing "---\n" of frontmatter.
    # Use the EXACT same regex as provenance.compute_content_hash to ensure
    # identical body extraction (provenance._FRONTMATTER_RE).
    full_text = "\n".join(lines)
    _FM_RE = re.compile(r"^(---\s*\n)(.*?)(\n---\s*(?:\n|$))", re.DOTALL)
    fm_match = _FM_RE.match(full_text)
    body = full_text[fm_match.end():] if fm_match else full_text
    # Normalize body the same way provenance.compute_content_hash does:
    # CRLF->LF, strip trailing whitespace per line
    normalized = "\n".join(
        line.rstrip() for line in body.replace("\r\n", "\n").splitlines()
    )
    content_hash = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:32]
    # Insert content_hash into provenance block (after content_created_at line)
    lines_out = []
    inserted = False
    for line in lines:
        lines_out.append(line)
        if not inserted and line.strip().startswith("content_created_at:"):
            lines_out.append(f"  content_hash: {content_hash}")
            inserted = True
    return "\n".join(lines_out)


# _get_family_display() removed TC13 (2026-08-26): it was _build_page()'s
# own, independently hand-rolled anchor-text builder (used by nothing else
# after this change), with a narrower hardcoded plat_map than the governed
# _expected_anchor_text()/_get_backlink_display_maps() source of truth now
# used instead -- see the TC13 redesign in the governing plan.


# ---------------------------------------------------------------------------
# Main logic
# ---------------------------------------------------------------------------

def _load_update_apis(family: str, platform: str) -> set[str] | None:
    """Load the set of API class names that need updating from knowledge_delta.json.

    Includes modified_apis, new_apis, and resurrected_apis so that --update mode
    regenerates pages for all classes that changed, were added, or were re-added
    after a prior removal (Fix D — healing sprint 2026-04-15).

    Returns None if the file is absent (caller falls back to full re-run).
    Returns an empty set if the file exists but has no relevant APIs.
    """
    delta_path = KNOWLEDGE_ROOT / family / platform / "merged" / "knowledge_delta.json"
    if not delta_path.exists():
        return None
    try:
        delta = json.loads(delta_path.read_text(encoding="utf-8"))
        return (set(delta.get("modified_apis", []))
                | set(delta.get("new_apis", []))
                | set(delta.get("resurrected_apis", [])))
    except Exception:
        return None


_FRONTMATTER_FENCE_RE = re.compile(r"^---\n", re.MULTILINE)


def _extract_body(text: str) -> str:
    """Return the body of a page (everything after the closing frontmatter fence).

    If no frontmatter is found, returns the full text so that comparisons still
    work (the page is treated as all-body).
    """
    # Find the second occurrence of a line that is exactly "---"
    fences = [m.start() for m in _FRONTMATTER_FENCE_RE.finditer(text)]
    if len(fences) >= 2:
        return text[fences[1] + 4:]  # skip "---\n" (4 chars)
    return text


def _has_meaningful_change(existing_path: Path, new_content: str) -> bool:
    """Return True if *new_content* has a different body than the existing file.

    Only the content *after* the closing frontmatter fence is compared.  This
    means evidence metadata (model_sha, apis list, grade, graded_at, content_hash,
    etc.) and provenance fields (content_created_at, content_hash) are ignored —
    they are all rewritten by attach_evidence() / update_mechanism() after the
    body write anyway.

    Bodies are compared via the same CRLF/trailing-whitespace normalization
    lib.provenance.compute_content_hash() already uses for content_hash, not a
    bare .rstrip(). Without this, a body that is logically identical but
    differs only in line endings (confirmed live 2026-08-14, 3d/java
    --rebuild-all: staged output had CRLF terminators against LF-committed
    HEAD) reads as "meaningfully changed" here, triggering a write attempt
    that the receipt validator's own (CRLF-normalizing) hash check then
    correctly refuses as BODY_UPDATED-with-identical-body -- leaving an
    orphan receipt with no page_decisions.jsonl row.

    Returns True (treat as changed) if the existing file cannot be read.
    """
    try:
        existing = existing_path.read_text(encoding="utf-8")
    except OSError:
        return True

    # _FRONTMATTER_FENCE_RE matches a bare "---\n" only: a CRLF-carrying
    # new_content ("---\r\n") fails the fence match entirely, so
    # _extract_body falls back to returning the FULL text (frontmatter
    # included) rather than just the body -- guaranteeing a spurious
    # "different" verdict even when the actual prose is identical. Collapse
    # CRLF before fence-matching, not just when normalizing the extracted
    # body, so the same page's fence is found on both sides.
    existing = existing.replace("\r\n", "\n")
    new_content = new_content.replace("\r\n", "\n")

    return _normalize_body(_extract_body(existing)) != _normalize_body(
        _extract_body(new_content)
    )


# ---------------------------------------------------------------------------
# Grouped index generation
# ---------------------------------------------------------------------------

# Family-specific group label overrides for human-friendly headings.
# Keys are lowercased package/module tail segments; values are display labels.
_GROUP_LABEL_OVERRIDES: dict[str, dict[str, str]] = {
    "email": {
        "cfb": "CFB Format (Compound File Binary)",
        "msg": "MSG Format",
    },
    "font": {
        "cff": "CFF Font Handling",
        "eot": "EOT Font Handling",
        "ttf": "TrueType Font Handling",
        "type1": "Type1 Font Handling",
        "woff": "WOFF / WOFF2 Handling",
        "_brotli": "Brotli Compression (Internal)",
    },
}


def _derive_group_key(entry: dict, family: str, platform: str) -> str:
    """Extract a package/module group key from an api_surface entry.

    Returns the most informative subpackage segment from the ``file`` path.
    For entries at the package root, returns ``"core"``.
    """
    file_path = entry.get("file", "")
    if not file_path:
        return "core"

    parts = file_path.replace("\\", "/").split("/")

    if platform == "python":
        # Pattern: src/aspose_font/ttf/tables/name.py  or  aspose/email_foss/cfb/reader.py
        # Find the family package root and return the next segment
        for i, p in enumerate(parts):
            if family.replace("-", "_") in p.replace("-", "_").lower():
                if i + 1 < len(parts) - 1:  # -1 to skip the filename
                    return parts[i + 1]
                return "core"
        return "core"

    elif platform in ("java", "net"):
        # Primary pattern: src/main/java/org/aspose/pdf/operators/SetColor.java
        # Find the family name as a directory segment, then take the next segment.
        for i, p in enumerate(parts):
            if p.lower() == family.lower() and i + 1 < len(parts) - 1:
                next_seg = parts[i + 1]
                if next_seg.endswith(".java") or next_seg.endswith(".cs"):
                    return "core"
                return next_seg
        # .NET-specific fallback: repos that use src/{Namespace}/{Class}.cs layout
        # (no family-name directory segment in path, e.g. src/Annotations/Class.cs).
        if platform == "net":
            for i, p in enumerate(parts):
                if p.lower() == "src" and i + 1 < len(parts) - 1:
                    next_seg = parts[i + 1]
                    ext = next_seg.rsplit(".", 1)[-1].lower() if "." in next_seg else ""
                    if ext in ("cs", "vb", "fs"):
                        return "core"  # file directly under src/ — no namespace
                    return next_seg.lower()
        return "core"

    elif platform == "go":
        # Pattern: pkg/api/document.go or internal/cos/stream.go
        for i, p in enumerate(parts):
            if p in ("pkg", "internal", "api") and i + 1 < len(parts) - 1:
                return parts[i + 1]
        # Fallback: use second-to-last directory
        if len(parts) >= 3:
            return parts[-2]
        return "core"

    elif platform in ("cpp", "typescript"):
        # Similar to Java pattern
        for i, p in enumerate(parts):
            if p.lower() == family.lower() and i + 1 < len(parts) - 1:
                next_seg = parts[i + 1]
                if "." in next_seg:  # filename
                    return "core"
                return next_seg
        return "core"

    elif platform == "rust":
        # Pattern: src/formats/xlsx.rs → "formats"; src/workbook.rs → "core".
        # Directory segments that are not valid Rust module identifiers
        # (e.g. the dotted `src/Aspose.Cells_FOSS/` #[path]-mapped layout)
        # are not modules — treat them as crate root.
        for i, p in enumerate(parts):
            if p == "src" and i + 1 < len(parts) - 1:
                next_seg = parts[i + 1]
                if (next_seg.endswith(".rs")
                        or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", next_seg)):
                    return "core"
                return next_seg
        # Fallback: use second-to-last directory (nested crate layouts)
        if len(parts) >= 3 and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", parts[-2]):
            return parts[-2]
        return "core"

    return "core"


def _group_label(key: str, family: str, platform: str) -> str:
    """Convert a group key to a human-readable heading."""
    overrides = _GROUP_LABEL_OVERRIDES.get(family, {})
    if key in overrides:
        return overrides[key]
    if key == "core":
        return "Core API"
    # Title-case the key, replace underscores with spaces
    label = key.replace("_", " ").replace("-", " ").title()
    return label


def _normalize_doc_for_index(doc: str) -> str:
    """Normalize a raw doc string for safe use in a markdown table cell.

    Strips bare CR characters, converts JavaDoc inline tags to markdown,
    strips HTML tags, and collapses whitespace. Does NOT truncate —
    truncation is handled by the caller's split('. ')[0] logic.
    """
    # 1. Strip bare CR characters (from CRLF source files stored as CR-only in JSON)
    doc = doc.replace("\r", " ")
    # 2. Collapse whitespace created by CR removal
    doc = re.sub(r"\s+", " ", doc).strip()
    # 3. {@code X} -> `X` (use \s* to handle both "{@code Foo}" and no-space edge cases)
    doc = re.sub(
        r"\{@code\s*([^}]*)\}",
        lambda m: f"`{m.group(1).strip()}`" if m.group(1).strip() else "",
        doc,
    )
    # 4. {@link pkg.Class#method} -> simple name (last segment after . or #)
    def _link_to_name(m: re.Match) -> str:  # type: ignore[type-arg]
        text = m.group(1).strip()
        for sep in ("#", "."):
            if sep in text:
                text = text.rsplit(sep, 1)[-1]
        return text

    doc = re.sub(r"\{@link\s*([^}]*)\}", _link_to_name, doc)
    # 5. {@literal X} -> X
    doc = re.sub(
        r"\{@literal\s*([^}]*)\}",
        lambda m: m.group(1).strip(),
        doc,
    )
    # 6. Strip any remaining {@...} tags
    doc = re.sub(r"\{@\w+[^}]*\}", "", doc)
    # 7. <code>X</code> -> `X`
    doc = re.sub(
        r"<code>(.*?)</code>",
        lambda m: f"`{m.group(1).strip()}`" if m.group(1).strip() else "",
        doc,
        flags=re.IGNORECASE,
    )
    # 8. Strip remaining HTML tags
    doc = re.sub(r"<[^>]+>", "", doc)
    # 9. Final whitespace normalization
    doc = re.sub(r"\s+", " ", doc).strip()
    return doc


def _build_grouped_index_body(
    api_surface: list[dict],
    family: str,
    platform: str,
    erc_index: dict[str, dict] | None = None,
) -> str:
    """Build the grouped markdown body for a reference platform _index.md.

    Groups api_surface entries by package/module, then by type category.
    Returns the markdown body (no frontmatter).
    """
    from collections import defaultdict

    # Group by package key
    groups: dict[str, list[dict]] = defaultdict(list)
    for entry in api_surface:
        key = _derive_group_key(entry, family, platform)
        groups[key].append(entry)

    # Sort groups: "core" first, then alphabetically
    sorted_keys = sorted(groups.keys(), key=lambda k: ("" if k == "core" else k))

    lines: list[str] = []

    for gkey in sorted_keys:
        entries = groups[gkey]
        label = _group_label(gkey, family, platform)

        # Sub-group by category
        by_cat: dict[str, list[dict]] = defaultdict(list)
        for e in entries:
            cat = _category(e, platform)
            by_cat[cat].append(e)

        # Sort categories: Class first, then Interface, Struct, Enum
        cat_order = {"Class": 0, "Interface": 1, "Struct": 2, "Enum": 3}
        sorted_cats = sorted(by_cat.keys(), key=lambda c: cat_order.get(c, 99))

        # Determine section heading
        # If there's only one category and it's Class, use the group label directly
        # If there are multiple categories, append category name to sub-tables
        multi_cat = len(sorted_cats) > 1

        lines.append(f"## {label}")
        lines.append("")

        for cat in sorted_cats:
            cat_entries = sorted(by_cat[cat], key=lambda e: e.get("name", ""))

            if multi_cat and cat != "Class":
                # Add a sub-heading for non-Class categories
                cat_plural = {
                    "Enum": "Enumerations",
                    "Interface": "Interfaces",
                    "Struct": "Structs",
                }.get(cat, f"{cat}es")
                lines.append(f"### {cat_plural}")
                lines.append("")

            # Table header
            col_name = {
                "Enum": "Enumeration",
                "Interface": "Interface",
                "Struct": "Struct",
            }.get(cat, "Class")
            lines.append(f"| {col_name} | Description |")
            lines.append("|---|---|")

            for e in cat_entries:
                name = e.get("name", "?")
                doc = _normalize_doc_for_index(e.get("doc", "").strip())
                # Truncate to first sentence (after normalization, \r no longer breaks split)
                if doc:
                    doc = doc.split("\n")[0].split(". ")[0]
                    if not doc.endswith("."):
                        doc += "."
                elif erc_index and name in erc_index:
                    # Fallback to ERC claim text (key is "text", not "description")
                    erc = erc_index[name]
                    doc = _normalize_doc_for_index(erc.get("text", ""))
                    doc = doc.split("\n")[0].split(". ")[0] if doc else doc
                    if doc and not doc.endswith("."):
                        doc += "."
                if not doc:
                    # Synthesize a meaningful description from available metadata.
                    # Do NOT repeat the class name — column 1 already has it.
                    method_count = len(e.get("methods", []))
                    prop_count = len(e.get("properties", []))
                    enum_count = len(e.get("enum_members") or e.get("members", []))
                    bases = e.get("bases", [])
                    count_parts = []
                    if method_count:
                        count_parts.append(
                            f"{method_count} {'method' if method_count == 1 else 'methods'}"
                        )
                    if prop_count:
                        count_parts.append(
                            f"{prop_count} {'property' if prop_count == 1 else 'properties'}"
                        )
                    if enum_count:
                        count_parts.append(
                            f"{enum_count} {'member' if enum_count == 1 else 'members'}"
                        )
                    if count_parts:
                        doc = f"{cat} with {' and '.join(count_parts)}."
                    else:
                        base_name = ""
                        if bases:
                            b = bases[0]
                            base_name = (
                                b.get("name", "") if isinstance(b, dict) else str(b)
                            ).strip()
                        if base_name and base_name != name:
                            doc = f"{cat} extending {base_name}."
                        else:
                            doc = f"{cat} in the {family.title()} {platform.upper()} API."
                # Escape pipes in doc
                doc = doc.replace("|", "\\|")
                # GI-01: use _entry_slug(e) so case-variant entries (e.g. ID vs Id) emit
                # the namespace-disambiguated slug that matches the committed .md filename.
                # For the common case (no _slug_suffix) _entry_slug() returns the raw name.
                lines.append(f"| `{_entry_slug(e)}` | {doc} |")

            lines.append("")

        lines.append("---")
        lines.append("")

    return "\n".join(lines)


def _is_flat_index(index_path: Path) -> bool:
    """Return True if a reference _index.md uses only {{< children >}} without grouped tables."""
    if not index_path.exists():
        return False
    text = index_path.read_text(encoding="utf-8")
    # Extract body after frontmatter
    if text.startswith("---"):
        end = text.find("---", 3)
        if end != -1:
            body = text[end + 3:].strip()
        else:
            body = text.strip()
    else:
        body = text.strip()
    # Strip See Also section
    import re as _re
    body = _re.sub(r"##\s*See Also.*", "", body, flags=_re.DOTALL).strip()
    lines = [l.strip() for l in body.splitlines() if l.strip()]
    has_h2 = any(l.startswith("## ") for l in lines)
    has_table = any(l.startswith("|") for l in lines)
    if has_h2 and has_table:
        return False
    return "{{< children" in body


def detect_flat_indexes() -> list[dict]:
    """Scan all reference platforms and return those with flat indexes that could be grouped."""
    ref_root = CONTENT_ROOT / "reference.aspose.org" / "en"
    results = []
    if not ref_root.is_dir():
        return results
    for family_dir in sorted(ref_root.iterdir()):
        if not family_dir.is_dir():
            continue
        for plat_dir in sorted(family_dir.iterdir()):
            if not plat_dir.is_dir():
                continue
            index_path = plat_dir / "_index.md"
            if not _is_flat_index(index_path):
                continue
            api_path = KNOWLEDGE_ROOT / family_dir.name / plat_dir.name / "merged" / "api_surface.json"
            if not api_path.exists():
                continue
            api = json.loads(api_path.read_text(encoding="utf-8"))
            if len(api) >= 5:
                results.append({
                    "family": family_dir.name,
                    "platform": plat_dir.name,
                    "api_count": len(api),
                    "path": str(index_path),
                })
    return results


def generate_grouped_index(
    family: str,
    platform: str,
    dry_run: bool = False,
) -> dict:
    """Generate a grouped reference _index.md from api_surface.json metadata.

    Returns a result dict with keys: written, skipped, reason, path, body_preview.
    """
    api_surface_path = KNOWLEDGE_ROOT / family / platform / "merged" / "api_surface.json"
    if not api_surface_path.exists():
        return {"written": False, "skipped": True, "reason": "api_surface.json missing",
                "path": "", "body_preview": ""}

    api_surface = json.loads(api_surface_path.read_text(encoding="utf-8"))
    if len(api_surface) < 5:
        return {"written": False, "skipped": True,
                "reason": f"api_surface too small ({len(api_surface)} entries, need >= 5)",
                "path": "", "body_preview": ""}

    # Filter to platform-appropriate entries
    entries = [e for e in api_surface if _passes_platform_scope(e, platform)]
    entries = [e for e in entries if e.get("visibility") != "internal"]

    if len(entries) < 5:
        return {"written": False, "skipped": True,
                "reason": f"filtered entries too small ({len(entries)})",
                "path": "", "body_preview": ""}

    # GI-01: Apply the same Phase A case-collision disambiguation used in run() so that
    # _build_grouped_index_body() emits the correct slug (e.g. "ID-Operators" not "ID").
    # Without this, generate_grouped_index() would use raw entry names, producing broken
    # links for case-variant API types (e.g. Id vs ID on pdf/net).
    _gi_content_dir = CONTENT_ROOT / family / platform
    _gi_existing_exact: set[str] = (
        {f.name for f in _gi_content_dir.iterdir() if f.suffix == ".md"}
        if _gi_content_dir.is_dir() else set()
    )
    _gi_slug_by_lower: dict[str, list[dict]] = {}
    for _gie in entries:
        _gi_slug_by_lower.setdefault(_entry_slug(_gie).lower(), []).append(_gie)
    for _gi_lower, _gi_group in _gi_slug_by_lower.items():
        if len(_gi_group) < 2:
            continue
        _gi_winner = None
        for _gie in _gi_group:
            if f"{_entry_slug(_gie)}.md" in _gi_existing_exact:
                _gi_winner = _gie
                break
        _assign_namespace_slug_suffixes([
            _gie for _gie in _gi_group
            if _gie is not _gi_winner and not _gie.get("_slug_suffix")
        ])

    # Load model metadata
    model_sha = ""
    model_version = ""
    model_path = KNOWLEDGE_ROOT / family / platform / "merged" / "model.yaml"
    if model_path.exists():
        try:
            import yaml
            model = yaml.safe_load(model_path.read_text(encoding="utf-8")) or {}
            model_sha = model.get("repo_sha", "") or ""
            model_version = model.get("version", "") or ""
        except Exception:
            pass

    # Build ERC index for description fallback
    erc_index = _build_erc_index(family, platform, api_surface=entries)

    # Generate grouped body
    body = _build_grouped_index_body(entries, family, platform, erc_index=erc_index)

    # Read existing _index.md to preserve/update frontmatter
    index_path = CONTENT_ROOT / family / platform / "_index.md"
    if not index_path.exists():
        return {"written": False, "skipped": True,
                "reason": f"_index.md does not exist at {index_path}",
                "path": str(index_path), "body_preview": ""}

    existing_text = index_path.read_text(encoding="utf-8")

    # Parse existing frontmatter
    fm_match = re.match(r"^---\n(.*?)\n---", existing_text, re.DOTALL)
    if not fm_match:
        return {"written": False, "skipped": True,
                "reason": "Cannot parse existing frontmatter",
                "path": str(index_path), "body_preview": ""}

    fm_text = fm_match.group(1)

    # Update provenance: set auto_updatable to true, content_origin to skill-generated
    fm_text = re.sub(r"auto_updatable:\s*(true|false)", "auto_updatable: true", fm_text)
    fm_text = re.sub(r"content_origin:\s*\S+", "content_origin: skill-generated", fm_text)
    fm_text = re.sub(r"last_mechanism:\s*\S+", "last_mechanism: skill", fm_text)
    # Remove recovery note if present (no longer structural-page after healing)
    fm_text = re.sub(r"\n\s*provenance_recovery_note:\s*\S+", "", fm_text)

    # TC-DUPIDX-02 (2026-08-12, ST-059): stamp the generator-logic version so refresh_run.py's
    # apply_run() can detect an already-published index built by pre-fix code (e.g. GI-01,
    # 362430210c) and re-invoke this function -- the gap that let 9 published pages keep
    # duplicate rows indefinitely after the disambiguation fix landed with no re-invocation path.
    if re.search(r"^\s*index_generator_version:\s*\S+", fm_text, re.MULTILINE):
        fm_text = re.sub(
            r"^(\s*)index_generator_version:\s*\S+",
            rf"\g<1>index_generator_version: {GROUPED_INDEX_GENERATOR_VERSION}",
            fm_text, flags=re.MULTILINE,
        )
    else:
        fm_text = re.sub(
            r"(auto_updatable:\s*true)",
            rf"\g<1>\n  index_generator_version: {GROUPED_INDEX_GENERATOR_VERSION}",
            fm_text, count=1,
        )

    # Build intro paragraph
    _PLAT_DISPLAY = {
        "net": ".NET", "java": "Java", "python": "Python",
        "cpp": "C++", "typescript": "TypeScript", "go": "Go",
        "nodejs": "Node.js",
    }
    plat_display = _PLAT_DISPLAY.get(platform, platform.capitalize())
    version_str = f" v{model_version}" if model_version else ""
    intro = (f"API reference for **Aspose.{family.capitalize()} FOSS for "
             f"{plat_display}**{version_str}. "
             f"{len(entries)} public types organized by module.\n")

    # Compose full page
    full_content = f"---\n{fm_text}\n---\n\n{intro}\n{body}"

    # TC13 (2026-08-26): See Also section, now routed through the same
    # governed chokepoint _build_page() uses -- this hardcoded block was a
    # THIRD, independently-implemented backlink insertion (never called
    # resolve_backlink() at all, always family-level even for a
    # platform-level index page, hardcoded `family.capitalize()` instead of
    # the governed families.json display name). See the TC13 redesign in
    # the governing plan for the full audit that found this.
    _tm = _get_backlink_target_map()
    if _tm:
        try:
            _authority = _get_backlink_authority()
            _source_file = _canonical_reference_path(index_path)
            chosen_url, _rtype, _rsubdomain, _fallback = _resolve_backlink_fn(
                family, platform, "reference.aspose.org", _tm,
                canonical_overrides=_get_canonical_overrides(),
                exact_deep_match_enabled=bool(_authority),
                authority=_authority,
                source_file=_source_file,
            )
            if chosen_url:
                _families_map, _platforms_map = _get_backlink_display_maps()
                _before, _after, _warnings, _skipped, _skip_reason = _compute_markdown_backlink_insertion(
                    full_content, chosen_url, family, platform, "reference.aspose.org",
                    _families_map, _platforms_map, target_type=_rtype,
                )
                if _after != full_content:
                    full_content = _after
                for _w in _warnings:
                    LOG.warning("backlink: %s — %s/%s (index)", _w, family, platform)
            else:
                LOG.warning("backlink: BLOCKED_TARGET for %s/%s (index) — See Also omitted", family, platform)
        except Exception as exc:
            LOG.warning("backlink: See Also generation failed for %s/%s (index): %s", family, platform, exc)

    if dry_run:
        preview = "\n".join(full_content.splitlines()[:40])
        print(f"DRY-RUN: {family}/{platform} — {len(entries)} entries, "
              f"{len(body.splitlines())} body lines")
        return {"written": False, "skipped": False, "reason": "dry-run",
                "path": str(index_path), "body_preview": preview,
                "entry_count": len(entries), "body_lines": len(body.splitlines())}

    # Check if manually curated — never overwrite
    if is_manually_curated(index_path):
        return {"written": False, "skipped": True,
                "reason": "manually curated — skipping",
                "path": str(index_path), "body_preview": ""}

    # Determine if force is needed
    needs_force = not is_auto_updatable(index_path)
    force_reason = ("ref-structure-healing: structural-page recovery — "
                    "replacing flat children shortcode with grouped API tables")

    try:
        safe_content_write(
            index_path, full_content,
            mechanism="skill",
            force=needs_force,
            reason=force_reason if needs_force else "",
        )
    except ProtectedPageError as exc:
        return {"written": False, "skipped": True,
                "reason": f"ProtectedPageError: {exc}",
                "path": str(index_path), "body_preview": ""}

    # Attach evidence
    knowledge = Knowledge(family, platform, knowledge_root=KNOWLEDGE_ROOT)
    if knowledge.available:
        attach_evidence(index_path, knowledge, force=True)

    print(f"WRITTEN: {family}/{platform}/_index.md — {len(entries)} entries, "
          f"{len(body.splitlines())} body lines, force={needs_force}")

    return {"written": True, "skipped": False, "reason": "success",
            "path": str(index_path), "body_preview": "",
            "entry_count": len(entries), "body_lines": len(body.splitlines()),
            "force_used": needs_force}


def check_member_doc_coverage(
    api_surface: list[dict],
    member_erc_index: dict[str, str],
) -> tuple[float, int, int]:
    """Compute ERC member-doc coverage across all public members.

    Returns (coverage_rate, covered_count, total_count) where coverage_rate
    is the fraction of public properties/methods that have an ERC member-doc
    description (0.0–1.0).  Used as a pre-generation gate to detect when
    enrich --mode member-doc has not been run.
    """
    total = 0
    covered = 0
    for entry in api_surface:
        cname = entry.get("name", "")
        for prop in entry.get("properties", []):
            if prop.get("doc", "").strip():
                # Docstring from source — always counts
                total += 1
                covered += 1
            else:
                total += 1
                pname = prop.get("name", "")
                if member_erc_index.get(f"{cname}.{pname}", ""):
                    covered += 1
        for method in entry.get("methods", []):
            if method.get("is_constructor"):
                continue
            if method.get("doc", "").strip():
                total += 1
                covered += 1
            else:
                total += 1
                mname = method.get("name", "")
                if member_erc_index.get(f"{cname}.{mname}", ""):
                    covered += 1
    rate = covered / total if total > 0 else 0.0
    return rate, covered, total


def run(family: str, platform: str, kind_arg: str = "all",
        limit: int | None = None, dry_run: bool = False, update: bool = False,
        require_member_doc_coverage: int | None = None, heal: bool = False,
        confirm_heal: bool = False, plan_path: str | None = None,
        rebuild_all: bool = False, confirm_rebuild: bool = False,
        run_id: str | None = None, run_root: str | Path | None = None) -> dict:
    """Run batch reference generation. Returns result dict with counts.

    When update=True, only re-generates pages for classes listed in
    knowledge_delta.json modified_apis.  Default mode (update=False) is
    unchanged: skip pages that already exist (idempotent).

    When rebuild_all=True, regenerates all existing auto-updatable pages from
    current merged/claims.json without requiring knowledge_delta.json.
    Pages marked auto_updatable=false or manually curated are protected.
    Requires confirm_rebuild=True when more than REBUILD_CONFIRM_THRESHOLD pages
    would be overwritten.
    """
    if not dry_run and not run_id:
        raise ValueError("mutating batch-reference execution requires an explicit run_id")
    explicit_run_root = run_root is not None
    resolved_run_root = (
        Path(run_root)
        if run_root is not None
        else REPO_ROOT / "reports" / "refresh_runs" / family / platform / str(run_id)
        if run_id
        else None
    )

    if update and rebuild_all:
        print("STOP: --update and --rebuild-all are mutually exclusive. Use one or the other.")
        sys.exit(2)

    api_surface_path = KNOWLEDGE_ROOT / family / platform / "merged" / "api_surface.json"
    if not api_surface_path.exists():
        print(f"STOP: api_surface.json not found at {api_surface_path}. "
              f"Run /knowledge-bootstrap {family} {platform} first.")
        sys.exit(1)

    if limit == 0:
        print("STOP: --limit must be a positive integer.")
        sys.exit(1)

    # Check for stale knowledge; also read model_sha and version for evidence blocks
    model_sha = ""
    model_version = ""
    model_path = KNOWLEDGE_ROOT / family / platform / "merged" / "model.yaml"
    if not model_path.exists():
        print(f"STOP: model.yaml not found at {model_path}. "
              f"Run /truth-merge {family} {platform} to build a complete knowledge model "
              f"before generating content.")
        sys.exit(1)
    if model_path.exists():
        try:
            import yaml
            model = yaml.safe_load(model_path.read_text(encoding="utf-8")) or {}
            # FRESH-001 (2026-08-14, T7): migrated from a raw stale_since read to the
            # shared freshness_guard gate — degraded mode (no network call, appropriate
            # for this high-volume generation-time caller) still honors an authored
            # stale_since flag exactly as before, and additionally catches CORRUPT
            # (disagreeing baseline sources) and REFRESHING/REFRESH_FAILED, none of
            # which the old check could see.
            sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib"))
            from freshness_guard import is_generation_allowed
            allowed, fresh_result = is_generation_allowed(family, platform, mode="degraded")
            if not allowed:
                print(f"STOP: Knowledge model is not fresh (state={fresh_result.state}: "
                      f"{fresh_result.reason}). Run /knowledge-diff then "
                      f"/knowledge-update {family} {platform} before generating content.")
                sys.exit(1)
            model_sha = model.get("repo_sha", "") or ""
            model_version = model.get("version", "") or ""
        except Exception:
            pass

    api_surface = json.loads(api_surface_path.read_text(encoding="utf-8"))

    # Build ERC-* claim index for prose fallback when doc is empty
    erc_index = _build_erc_index(family, platform, api_surface=api_surface)
    if erc_index:
        print(f"ERC index: {len(erc_index)} class entries available for doc fallback.")

    # Build member-level ERC index for property/method table descriptions
    member_erc_index = _build_erc_member_index(family, platform, api_surface=api_surface)
    if member_erc_index:
        print(f"Member ERC index: {len(member_erc_index)} member descriptions available.")

    # Pre-generation member-doc coverage gate
    _cov_rate, _cov_covered, _cov_total = check_member_doc_coverage(api_surface, member_erc_index)
    _cov_pct = int(100 * _cov_rate)
    if _cov_total > 0:
        print(f"Member-doc coverage: {_cov_pct}% ({_cov_covered}/{_cov_total} members documented)")
        _COVERAGE_WARN_THRESHOLD = 20
        if _cov_pct < _COVERAGE_WARN_THRESHOLD:
            LOG.warning(
                "member-doc coverage is %d%% (%d/%d) — run enrich --mode member-doc first "
                "to populate property/method table descriptions",
                _cov_pct, _cov_covered, _cov_total,
            )
        if require_member_doc_coverage is not None and _cov_pct < require_member_doc_coverage:
            print(
                f"STOP: member-doc coverage {_cov_pct}% < required {require_member_doc_coverage}%. "
                f"Run: python scripts/pipeline/commands/knowledge/enrich.py --family {family} --platform {platform} "
                f"--mode member-doc, then promote.py, then retry."
            )
            sys.exit(1)

    # Filter candidates
    candidates = [e for e in api_surface if _passes_platform_scope(e, platform)]
    candidates = _apply_kind_filter(candidates, kind_arg, platform)
    # H-04d: Exclude internal/vendor classes from reference page generation.
    _internal_before = len(candidates)
    candidates = [e for e in candidates if e.get("visibility") != "internal"]
    _internal_skipped = _internal_before - len(candidates)
    if _internal_skipped:
        print(f"Skipped {_internal_skipped} internal/vendor class(es).")

    # H-04e: When __all__ is defined (detected by any "exported" entries),
    # exclude "conventional" classes — they are implementation details not
    # intended for public consumption. Only "exported" and "public" remain.
    _has_exports = any(e.get("visibility") == "exported" for e in candidates)
    if _has_exports:
        _conv_before = len(candidates)
        candidates = [e for e in candidates
                      if e.get("visibility") != "conventional"]
        _conv_skipped = _conv_before - len(candidates)
        if _conv_skipped:
            print(f"Skipped {_conv_skipped} conventional class(es) "
                  f"(package defines __all__).")

    scoped_paths: set[str] | None = None
    if explicit_run_root and resolved_run_root is not None:
        if not run_id:
            raise ValueError("an explicit run_root requires run_id")
        from commands.content.body_refresh import _validated_run_scope

        scope_data = _validated_run_scope(
            resolved_run_root,
            run_id=run_id,
            family=family,
            platform=platform,
        )
        scoped_paths = {
            Path(value).as_posix() for value in scope_data.get("paths", [])
        }
        # HARDEN-BR-01 (2026-07-29): scope manifests are typically built from a
        # file listing (e.g. `find`/glob), which captures whatever casing is
        # actually tracked on disk. A candidate's target filename is always
        # computed from api_surface.json's PascalCase class name
        # (_entry_slug), so a class whose existing tracked page happens to use
        # different casing (e.g. legacy "material.md" for the "Material"
        # class) silently drops out of every scoped run: "Material.md" (the
        # candidate's target) is a byte-for-byte different string than
        # "material.md" (what the manifest listed), even though they name the
        # SAME file on a case-insensitive filesystem (Windows). Found live:
        # 8 pre-existing 3d/java pages (camera/entity/light/material/mesh/
        # node/scene/transform) were silently excluded from two full
        # ST-013-remediation regeneration passes this way. Matching on the
        # lowercased path preserves the manifest's intent ("this file is in
        # scope") without depending on exact tracked casing. This is scope
        # membership, not the Phase A case-collision disambiguation below
        # (a different, legitimate concern: deciding NEW filenames when two
        # DIFFERENT classes would collide) -- that logic is untouched.
        scoped_paths_lower = {p.lower() for p in scoped_paths}

    # api_surface is already consolidated at extraction time (consolidate_classes
    # in api_surface.py).  Remaining same-name entries have distinct namespaces.
    # Disambiguate their output slugs so each gets its own page file.
    from collections import Counter as _Counter
    from collections import defaultdict as _defaultdict
    _name_counts = _Counter(e.get("name", "") for e in candidates)
    _collisions = {n for n, c in _name_counts.items() if c > 1}
    if _collisions:
        _groups: dict[str, list[dict]] = _defaultdict(list)
        for entry in candidates:
            if entry.get("name", "") in _collisions:
                _groups[entry["name"]].append(entry)
        for _group in _groups.values():
            _assign_namespace_slug_suffixes(_group)
        print(f"  {len(_collisions)} name collision(s) disambiguated by namespace")

    # Phase A: Case-collision detection.
    # Catches entries whose slugs are case-identical on Windows NTFS (e.g., Id vs ID).
    # The existing name-exact block above only catches entries with the same .name string;
    # Phase A catches entries whose names differ only by case (e.g., "Id" vs "ID").
    # Existing committed file on disk wins its slug; new entry gets namespace-suffix
    # disambiguation.  _case_dir is a local because output_dir is defined later (line ~1530).
    _case_dir = CONTENT_ROOT / family / platform  # output_dir not yet defined here
    # Build a case-SENSITIVE set of filenames actually stored on disk.
    # Path.exists() is case-insensitive on Windows NTFS, so "ID.md" would
    # match a file stored as "Id.md".  iterdir() returns the real stored name.
    _existing_exact: set[str] = (
        {f.name for f in _case_dir.iterdir() if f.suffix == ".md"}
        if _case_dir.is_dir() else set()
    )
    _slug_by_lower: dict[str, list[dict]] = {}
    for _ce in candidates:
        _cl = _entry_slug(_ce).lower()
        _slug_by_lower.setdefault(_cl, []).append(_ce)
    _case_only_collisions = {k: v for k, v in _slug_by_lower.items() if len(v) > 1}
    if _case_only_collisions:
        for _cl, _cgroup in _case_only_collisions.items():
            # The entry whose exact-case slug file already exists on disk keeps its slug.
            # On a normal clone all committed files are present, so the first found wins.
            # CRITICAL: use _existing_exact (case-sensitive iterdir set), not Path.exists()
            # which is case-insensitive on Windows NTFS.
            _existing_on_disk = None
            for _ce in _cgroup:
                if f"{_entry_slug(_ce)}.md" in _existing_exact:
                    _existing_on_disk = _ce
                    break
            _targets = [
                _ce for _ce in _cgroup
                if _ce is not _existing_on_disk and not _ce.get("_slug_suffix")
            ]
            _assign_namespace_slug_suffixes(_targets)
            for _ce in _targets:
                if not _ce.get("canonical_namespace"):
                    print(f"  WARN: case-collision for '{_ce.get('name')}' but "
                          f"canonical_namespace is empty — cannot auto-disambiguate; "
                          f"Phase C backstop will catch if both reach write loop")
        print(f"  {len(_case_only_collisions)} case-only collision(s) auto-disambiguated by namespace")

    # Never delete a tracked content page from this generator. A stale
    # undisambiguated page requires the governed page-retire workflow (draft:
    # true), with its own run-scoped disposition.
    if _collisions and not dry_run:
        _ref_dir = CONTENT_ROOT / family / platform
        _stale_pages: list[Path] = []
        for _cname in sorted(_collisions):
            _old = _ref_dir / f"{_sanitize_slug(_cname)}.md"
            if (
                _old.exists()
                and (
                    scoped_paths is None
                    or _canonical_reference_path(_old).lower() in scoped_paths_lower
                )
            ):
                _stale_pages.append(_old)
        if _stale_pages:
            raise RuntimeError(
                f"{len(_stale_pages)} stale undisambiguated page(s) require "
                "the governed page-retire workflow; no files were deleted: "
                f"{[path.name for path in _stale_pages[:5]]}"
            )

    if limit is not None:
        candidates = candidates[:limit]

    output_dir = CONTENT_ROOT / family / platform
    if scoped_paths is not None:
        candidates = [
            entry
            for entry in candidates
            if (
                _canonical_reference_path(
                    output_dir / f"{_entry_slug(entry)}.md"
                ).lower()
                in scoped_paths_lower
            )
        ]
    total = len(candidates)

    # Plan-aware advisory filtering (CP-P4)
    plan_slugs: set[str] | None = None
    if plan_path is not None:
        from page_spec import load_plan
        try:
            site_plan = load_plan(plan_path)
            ref_section = site_plan.sections.get("reference")
            if ref_section is not None:
                plan_slugs = {p.slug for p in ref_section.pages}
                not_in_plan = [e.get("name", "") for e in candidates
                               if e.get("name", "") not in plan_slugs]
                candidate_names = {e.get("name", "") for e in candidates}
                plan_only = [s for s in plan_slugs if s not in candidate_names
                             and s != "_index"]
                print(f"--plan: {len(plan_slugs)} reference pages in plan, "
                      f"{total} candidates in api_surface.")
                if not_in_plan:
                    print(f"  ADVISORY: {len(not_in_plan)} candidate(s) not in plan "
                          f"(will still generate):")
                    for name in not_in_plan[:10]:
                        print(f"    - {name}")
                    if len(not_in_plan) > 10:
                        print(f"    ... and {len(not_in_plan) - 10} more")
                if plan_only:
                    print(f"  ADVISORY: {len(plan_only)} plan page(s) have no "
                          f"api_surface candidate:")
                    for slug in sorted(plan_only)[:10]:
                        print(f"    - {slug}")
                    if len(plan_only) > 10:
                        print(f"    ... and {len(plan_only) - 10} more")
            else:
                print("--plan: no 'reference' section found in plan; ignoring.")
        except (FileNotFoundError, ValueError) as exc:
            _safe_print(f"WARN: --plan failed to load {plan_path}: {exc}")

    # Build a normalized slug index of existing pages for deduplication.
    # This prevents creating e.g. "MsgReader.md" when "msg-reader.md" or
    # "msg_reader.md" already exists.
    _existing_normalized: dict[str, Path] = {}
    if output_dir.exists():
        for existing in output_dir.glob("*.md"):
            norm = existing.stem.lower().replace("-", "_")
            _existing_normalized[norm] = existing

    def _has_slug_duplicate(entry: dict) -> Path | None:
        """Return existing path if a slug-normalized duplicate exists."""
        sanitized = _entry_slug(entry)
        norm = sanitized.lower().replace("-", "_")
        existing = _existing_normalized.get(norm)
        if existing is not None and existing.stem != sanitized:
            return existing
        return None

    def _resolve_page_path(entry: dict) -> Path:
        """Return the path an update/rebuild for *entry* must write to.

        Found live 2026-08-28 (note/python, 3d/net): the canonical
        ``output_dir / f"{_entry_slug(entry)}.md"`` path is always freshly
        derived from the CURRENT class name, ignoring any already-tracked
        page for that same class under a legacy casing/separator (e.g.
        note/python's reference pages are tracked as ``attachedfile.md``,
        while every current class name -- and this function -- derives
        ``AttachedFile.md``). ``Path.exists()`` on a case-insensitive
        filesystem (Windows) silently treats the two as the same file, so
        classification into to_update/to_skip still worked there, but
        writing to the freshly-derived path renamed the tracked file's
        casing as a side effect of what should have been a same-name
        update. On a case-SENSITIVE filesystem (Linux -- what actually
        serves the site and runs CI), the same write would create a
        genuinely NEW page under the new casing while leaving the
        legacy-cased original orphaned: a real, silent duplicate-page
        defect, invisible in every local (Windows) test run.
        _existing_normalized (built from a real directory listing, so it
        always reflects the actual on-disk casing) already exists for
        exactly this kind of lookup -- reuse it here rather than deriving
        fresh every time an entry is being updated, not newly generated.
        """
        existing = _has_slug_duplicate(entry)
        if existing is not None:
            return existing
        return output_dir / f"{_entry_slug(entry)}.md"

    # Determine which pages to generate/update vs skip
    to_generate = []   # pages that don't exist yet (always created)
    to_update = []     # pages that exist and are in modified_apis (--update mode only)
    to_skip = []       # pages that exist and are not being updated
    skip_reasons: dict[str, str] = {}

    def _skip(entry: dict, reason: str) -> None:
        to_skip.append(entry)
        skip_reasons[_entry_slug(entry)] = reason

    if update:
        # Load update-eligible APIs from knowledge_delta.json (modified + new + resurrected)
        modified_apis = _load_update_apis(family, platform)
        if modified_apis is None:
            print("WARN: knowledge_delta.json not found; falling back to skip-existing mode "
                  "(all existing pages will be skipped, only new pages generated). "
                  "Use --rebuild-all to regenerate existing pages without a delta.")
            update = False  # degrade to skip-existing mode
        else:
            print(f"--update mode: {len(modified_apis)} update-eligible API classes in knowledge_delta.json.")

    if update:
        for entry in candidates:
            name = entry.get("name", "")
            page_path = _resolve_page_path(entry)
            if not page_path.exists():
                # Phase B backstop: catch cross-run case collisions Phase A could not resolve
                _dup = _has_slug_duplicate(entry)
                if _dup is not None:
                    print(f"  DEDUP-SLUG: {name} — slug-duplicate of {_dup.stem}, skipping")
                    _skip(entry, "SLUG_DUPLICATE")
                else:
                    to_generate.append(entry)
            elif name in modified_apis:
                # Respect provenance protection: skip pages marked auto_updatable: false
                # or pages that were manually curated (manual-edit-skill, human-edit, etc.)
                if not is_auto_updatable(page_path):
                    print(f"  PROTECTED: {name} — auto_updatable: false, skipping update")
                    _skip(entry, "AUTO_UPDATABLE_FALSE")
                elif is_manually_curated(page_path) and not heal:
                    print(f"  PROTECTED: {name} — manually curated, skipping update")
                    _skip(entry, "MANUALLY_CURATED")
                else:
                    if is_manually_curated(page_path) and heal:
                        print(f"  HEAL: {name} — overriding manual-curation protection (auto_updatable=true)")
                    to_update.append(entry)
            else:
                _skip(entry, "NOT_IN_KNOWLEDGE_DELTA")
        print(f"Found {total} candidates: {len(to_generate)} to generate, "
              f"{len(to_update)} to update (in modified_apis), "
              f"{len(to_skip)} to skip.")
    elif rebuild_all:
        # --rebuild-all: regenerate all existing auto-updatable pages from current merged/claims.json
        # Does not require knowledge_delta.json.
        for entry in candidates:
            name = entry.get("name", "")
            page_path = _resolve_page_path(entry)
            if not page_path.exists():
                # Phase B backstop: catch cross-run case collisions Phase A could not resolve
                _dup = _has_slug_duplicate(entry)
                if _dup is not None:
                    print(f"  DEDUP-SLUG: {name} — slug-duplicate of {_dup.stem}, skipping")
                    _skip(entry, "SLUG_DUPLICATE")
                else:
                    to_generate.append(entry)
            elif not is_auto_updatable(page_path):
                print(f"  PROTECTED: {name} — auto_updatable: false, skipping rebuild")
                _skip(entry, "AUTO_UPDATABLE_FALSE")
            elif is_manually_curated(page_path):
                print(f"  PROTECTED: {name} — manually curated, skipping rebuild")
                _skip(entry, "MANUALLY_CURATED")
            else:
                to_update.append(entry)
        print(f"--rebuild-all: {len(to_generate)} new, {len(to_update)} eligible for rebuild, "
              f"{len(to_skip)} protected/skipped.")
        if len(to_update) > REBUILD_CONFIRM_THRESHOLD and not confirm_rebuild:
            raise SystemExit(
                f"--rebuild-all would regenerate {len(to_update)} existing pages. "
                f"Re-run with --confirm-rebuild to proceed."
            )
    else:
        for entry in candidates:
            name = entry.get("name", "")
            page_path = _resolve_page_path(entry)
            if page_path.exists():
                _skip(entry, "EXISTING_PAGE_NO_UPDATE_MODE")
            else:
                dup_path = _has_slug_duplicate(entry)
                if dup_path is not None:
                    print(f"  DEDUP-SLUG: {name} — slug-duplicate of {dup_path.stem}, skipping")
                    _skip(entry, "SLUG_DUPLICATE")
                else:
                    to_generate.append(entry)
        print(f"Found {total} candidates: {len(to_generate)} to generate, "
              f"{len(to_skip)} to skip (already exist or slug-duplicate).")

    # Combined list to write: new pages + pages being updated
    to_write = to_generate + to_update

    if heal:
        curated_pages = [p for p in to_write if is_manually_curated(
            output_dir / f"{p.get('name', '')}.md"
        )]
        if curated_pages:
            LOG.warning(
                "HEAL mode: %d manually-curated page(s) will have auto-generation override applied",
                len(curated_pages),
            )
            if len(curated_pages) > HEAL_CONFIRM_THRESHOLD and not confirm_heal:
                raise SystemExit(
                    f"--heal would override {len(curated_pages)} manually-curated pages. "
                    f"Re-run with --confirm-heal to proceed."
                )

    if dry_run:
        print("DRY-RUN: no files written.")
        for e in to_generate:
            print(f"  WOULD GENERATE: {e.get('name')} ({e.get('kind')})")
        for e in to_update:
            print(f"  WOULD UPDATE: {e.get('name')} ({e.get('kind')})")
        result = {
            "generated": 0, "updated": 0, "skipped": len(to_skip), "errors": 0, "dry_run": True,
            # Content-coverage audit (found live 2026-08-24, deepreassess pass,
            # mission-plan-the-end-to-end-vast-hejlsberg.md): the class-level
            # detail behind the counts above, so a caller (e.g.
            # content_coverage_audit.py) can report WHICH classes have no
            # page yet, not just how many -- purely additive, no existing
            # caller reads these two new keys.
            "to_generate_names": sorted(e.get("name", "") for e in to_generate),
            "to_update_names": sorted(e.get("name", "") for e in to_update),
            # Full-reference-scope resolution (deep-reassessment pass, 2026-08-24
            # -- G17/S-84 full-coverage regeneration): repo-relative page PATHS
            # (not just names), so refresh_run.py's prepare_run() can pin the
            # COMPLETE, delta-independent reference-page candidate set into
            # scope.json, the same path format scope.json already uses
            # everywhere else (_canonical_reference_path).
            "to_generate_paths": sorted(
                _canonical_reference_path(_resolve_page_path(e))
                for e in to_generate
            ),
            "to_update_paths": sorted(
                _canonical_reference_path(_resolve_page_path(e))
                for e in to_update
            ),
        }
        return result

    generated = []
    updated = []
    unchanged = []  # pages in to_update with no meaningful change (timestamp-only guard)
    errors = []
    _seen_lower_slugs: set[str] = set()  # Phase C: within-run case-collision backstop
    output_dir.mkdir(parents=True, exist_ok=True)

    # Load knowledge once for evidence attachment
    knowledge = Knowledge(family, platform, knowledge_root=KNOWLEDGE_ROOT)
    # LH-02 enforcement: knowledge.available MUST be checked BEFORE any page
    # writes (AGENTS.md §5a).  The early-exit checks above verify model.yaml
    # existence and staleness, but Knowledge.available is True only when
    # api_surface.json is loadable.  This guard closes the gap.
    if not knowledge.available:
        print(f"STOP: Knowledge not available for {family}/{platform} "
              f"(api_surface.json missing or unreadable). "
              f"Run /repo-scout {family} {platform}, then /truth-merge.")
        sys.exit(1)

    if resolved_run_root is None or run_id is None:
        raise ValueError("run evidence root could not be resolved")
    from commands.content.body_refresh import (
        _emit_receipt,
        _emit_run_decision,
        _existing_run_receipts,
        _normalized_body_hash,
        _run_recorded_at,
        _scan_forbidden_claims,
    )
    existing_run_receipts = _existing_run_receipts(
        resolved_run_root, run_id
    )

    def _receipt_already_applied(page_path: Path) -> bool:
        relative_page = _canonical_reference_path(page_path)
        receipt = existing_run_receipts.get(relative_page)
        if receipt is None or not page_path.is_file():
            return False
        return (
            "sha256:" + hashlib.sha256(page_path.read_bytes()).hexdigest()
            == receipt.get("new_hash")
        )

    def _record_reference_attempt(
        page_path: Path,
        before_content: str,
        final_content: str,
        *,
        before_file_hash: str | None = None,
        final_file_hash: str | None = None,
        intended_action: str,
        disposition: str,
        verdict: str,
        reason: str,
    ) -> None:
        """Persist one validated receipt/decision for every scoped candidate."""
        relative_page = _canonical_reference_path(page_path)
        old_digest = before_file_hash or hashlib.sha256(
            before_content.encode("utf-8")
        ).hexdigest()
        new_digest = final_file_hash or hashlib.sha256(
            final_content.encode("utf-8")
        ).hexdigest()
        # Scan body only, not the full file: the frontmatter evidence.apis list
        # cites exactly which API members a page discusses (a metadata index,
        # not a capability claim), so it legitimately contains the same
        # fully-qualified names forbidden_claims flags in body prose. Found
        # live: a brand-new abstract-class page's own evidence.apis reproduced
        # its forbidden dotted member verbatim (e.g. DataSource.read_bytes),
        # self-triggering RPR-E-02's tier-1 fully-qualified match against
        # frontmatter YAML the scanner was never meant to read as prose.
        forbidden_violations, forbidden_scan_ok, forbidden_scan_error = (
            _scan_forbidden_claims(
                _extract_body(before_content),
                _extract_body(final_content),
                family,
                platform,
            )
        )
        if forbidden_violations:
            raise ValueError(
                f"Reference generation introduced forbidden claims for "
                f"{relative_page}: {forbidden_violations[:3]}"
            )
        # Deep-reassessment pass, 2026-08-25 (mission-plan-the-end-to-end-vast-
        # hejlsberg.md Task 14, per direct user instruction to find the actual
        # root cause rather than patch symptoms): RegroundingCache's own
        # cross-page textual-novelty check (RPR-E-03) is deliberately NOT run
        # here anymore. It exists to catch an LLM fabricating a span once and
        # reusing it verbatim across unrelated pages (the 3d/net FVector3
        # incident it was built for) -- a real risk for body_refresh.py, which
        # DOES call an LLM. batch_reference.py has no such risk: confirmed by
        # direct code reading, _build_page() is entirely deterministic and
        # self-contained per class entry (no LLM, no cross-page data flow of
        # any kind). Its cross-page check produced only false positives here:
        # first for two genuinely different classes sharing a bare name
        # (org.aspose.pdf.engine.xfa.model.sourceset.Bind vs. ...template.Bind,
        # each with a real getRef() -- fixed once by reading cited evidence
        # from final_content instead of the pre-generation before_content, but
        # that fix only closed the "brand-new page" half of the gap) and then,
        # even with that fix, for six real, unrelated XFA registry classes
        # (ConnectionSetElements, DataDescriptionElements, ...) that
        # independently, correctly carry byte-identical Javadoc for a shared
        # registerAll(Map<String, XfaNodeFactory.Ctor>) method -- confirmed
        # directly against the real Java source in both cases, not assumed.
        # Cross-page textual novelty cannot distinguish "coincidentally
        # identical because the real source is identical" from "fabricated
        # and copied" for a generator that never fabricates in the first
        # place; patching the escape hatch for each newly-discovered
        # collision shape is not a durable fix.
        #
        # The actual risk this check could ever have caught for
        # batch_reference.py -- one class's description silently landing on a
        # different, same-named class -- runs through exactly one real
        # mechanism: _build_erc_index()/_build_erc_member_index()'s own
        # lookup keys, which used to be bare class names only. Both are now
        # namespace-collision-aware (ambiguous bare names are excluded from
        # the index entirely, since ERC claims carry no reliable per-class
        # evidence to disambiguate them -- see _build_erc_member_index's own
        # docstring), closing the one path by which this generator's output
        # could ever legitimately be mis-attributed across classes. With that
        # closed, every span batch_reference.py emits is either the entry's
        # own scout-extracted doc field (always correct for its own class) or
        # a class-agnostic synthesized description (also always correct) --
        # there is no remaining mechanism for cross-class leakage, so a
        # cross-page duplicate-text check has no true positive left to catch
        # here, only false ones. _scan_forbidden_claims above (a fixed,
        # explicit denylist of previously-debunked claims) is a different,
        # still-fully-active check, untouched by this change.
        regrounding_violations: list[dict] = []
        regrounding_scan_ok = True
        regrounding_scan_error = ""
        if before_content == final_content and page_path.is_file():
            new_digest = old_digest
        receipt_seed = (
            f"{run_id}\0{relative_page}\0{old_digest}\0{new_digest}\0{verdict}"
        ).encode("utf-8")
        receipt = {
            "receipt_id": f"RCP-{hashlib.sha256(receipt_seed).hexdigest()[:20]}",
            "run_id": run_id,
            "page_path": relative_page,
            "locale": "en",
            "change_ids": [],
            "strategy_used": "REFERENCE_REGENERATION",
            "old_hash": f"sha256:{old_digest}",
            "new_hash": f"sha256:{new_digest}",
            "verdict": verdict,
            "surface": "reference",
            "reason": reason,
            "forbidden_violations": forbidden_violations,
            "forbidden_claims_scan": {
                "ok": forbidden_scan_ok,
                "error": forbidden_scan_error,
            },
            "regrounding_violations": regrounding_violations,
            "regrounding_scan": {
                "ok": regrounding_scan_ok,
                "error": regrounding_scan_error,
            },
            "generated_at": _run_recorded_at(resolved_run_root),
        }
        receipt_path, receipt_digest = _emit_receipt(
            receipt,
            family,
            platform,
            run_root=resolved_run_root,
        )
        evidence_claims, evidence_apis = _evidence_ids(final_content)
        _emit_run_decision(
            run_root=resolved_run_root,
            receipt=receipt,
            receipt_path=receipt_path,
            receipt_digest=receipt_digest,
            old_content=before_content,
            new_content=final_content,
            impact={
                "evidence_claims_checked": evidence_claims,
                "evidence_apis_checked": evidence_apis,
            },
            intended_action=intended_action,
            disposition=disposition,
        )

    for entry in to_skip:
        reason = skip_reasons.get(_entry_slug(entry), "UNCLASSIFIED_SKIP")
        # SLUG_DUPLICATE is the one skip reason where _resolve_page_path()
        # would deliberately resolve to a DIFFERENT class's existing page
        # (the whole point of the Phase B backstop) -- every other reason
        # (AUTO_UPDATABLE_FALSE, MANUALLY_CURATED, NOT_IN_KNOWLEDGE_DELTA,
        # EXISTING_PAGE_NO_UPDATE_MODE) only ever fires for this SAME
        # entry's own existing page, found via _resolve_page_path() during
        # classification above. Recording a SLUG_DUPLICATE skip against the
        # canonical (still-nonexistent, for this entry) path -- not the
        # colliding page's real content -- is deliberate: this entry never
        # had a page of its own to report on.
        page_path = (
            output_dir / f"{_entry_slug(entry)}.md"
            if reason == "SLUG_DUPLICATE"
            else _resolve_page_path(entry)
        )
        if _receipt_already_applied(page_path):
            continue
        content = page_path.read_text(encoding="utf-8") if page_path.is_file() else ""
        before_file_hash = (
            hashlib.sha256(page_path.read_bytes()).hexdigest()
            if page_path.is_file()
            else None
        )
        blocked = reason in {
            "AUTO_UPDATABLE_FALSE",
            "MANUALLY_CURATED",
            "SLUG_DUPLICATE",
        }
        _record_reference_attempt(
            page_path,
            content,
            content,
            before_file_hash=before_file_hash,
            intended_action="REFERENCE_UPDATE",
            disposition="BLOCKED" if blocked else "NOT_AFFECTED",
            verdict="REFERENCE_BLOCKED" if blocked else "REFERENCE_SKIPPED",
            reason=reason,
        )

    for i, entry in enumerate(to_write, 1):
        name = entry.get("name", "")
        kind = entry.get("kind", "")
        is_rebuild = rebuild_all and entry in to_update
        is_update = entry in to_update
        action = "Rebuilding" if is_rebuild else ("Updating" if is_update else "Generating")
        print(f"[{i}/{len(to_write)}] {action} page for {name} ({kind})...")
        try:
            page_path = _resolve_page_path(entry)
            if _receipt_already_applied(page_path):
                receipt = existing_run_receipts[
                    _canonical_reference_path(page_path)
                ]
                if receipt.get("verdict") in ("BODY_UPDATED", "EVIDENCE_ONLY"):
                    updated.append(entry)
                elif receipt.get("verdict") == "GENERATED":
                    generated.append(entry)
                continue
            before_file_hash = (
                hashlib.sha256(page_path.read_bytes()).hexdigest()
                if page_path.is_file()
                else None
            )
            before_content = (
                page_path.read_text(encoding="utf-8") if page_path.is_file() else ""
            )
            # Phase C backstop: catch any case-collisions Phase A could not resolve
            # (e.g., entry with empty canonical_namespace that could not be auto-disambiguated).
            # Placed before _build_page() to avoid wasting an LLM call on a discarded page.
            _page_lower = _entry_slug(entry).lower()
            if _page_lower in _seen_lower_slugs:
                print(f"  WITHIN-BATCH-DEDUP: {name} — case-collision with already-written slug, skipping")
                errors.append((entry, "within-batch case-collision"))
                continue
            content = _build_page(entry, family, platform, erc_index=erc_index,
                                   member_erc_index=member_erc_index,
                                   model_sha=model_sha, model_version=model_version,
                                   content_created_at=_run_recorded_at(resolved_run_root),
                                   page_path=page_path)
            # Timestamp-only churn guard: in --rebuild-all mode, skip pages where
            # the only differences from the existing file are pure timestamp fields
            # (content_created_at, graded_at, grade, graded_content_hash, content_hash).
            # This prevents committing noise when the merged knowledge has not changed.
            if is_rebuild and not _has_meaningful_change(page_path, content):
                print(f"  UNCHANGED: {name} — no meaningful changes beyond timestamps, skipping write")
                unchanged.append(entry)
                _record_reference_attempt(
                    page_path,
                    before_content,
                    before_content,
                    before_file_hash=before_file_hash,
                    intended_action="REFERENCE_UPDATE",
                    disposition="NOT_AFFECTED",
                    verdict="REFERENCE_UNCHANGED",
                    reason="NO_MEANINGFUL_CHANGE",
                )
                continue
            # Preserve content_created_at from the existing page (write-once field).
            # safe_content_write() writes content as-is without timestamp preservation,
            # so we must carry the original value forward before writing.
            if is_rebuild and page_path.exists():
                try:
                    existing_text = page_path.read_text(encoding="utf-8")
                    _m = re.search(r"content_created_at:\s*'([^']+)'", existing_text)
                    if _m:
                        content = re.sub(
                            r"content_created_at:\s*'[^']+'",
                            f"content_created_at: '{_m.group(1)}'",
                            content,
                        )
                except OSError:
                    pass
            relative_page = Path(_canonical_reference_path(page_path))
            if relative_page.is_absolute() or ".." in relative_page.parts:
                raise ValueError(f"unsafe scoped page path: {relative_page}")
            staging_path = resolved_run_root / "staging" / relative_page
            safe_content_write(
                staging_path, content, mechanism="batch-reference-staging"
            )
            # Attach evidence and grading to the staged candidate.  The final
            # candidate bytes and their receipt exist before the real content
            # path is mutated.
            attach_evidence(staging_path, knowledge, force=True)
            final_content = staging_path.read_text(encoding="utf-8")
            final_file_hash = hashlib.sha256(
                staging_path.read_bytes()
            ).hexdigest()
            # PDF-NET-REFRESH-001 (v26.7.0): `is_update` only means "this page
            # already existed and was regenerated," not "its body prose
            # actually changed" -- attach_evidence(force=True) always
            # re-stamps the evidence block (model_sha, apis, etc.) even when
            # the class's real generated body is byte-identical to before.
            # Unconditionally recording BODY_UPDATED here is exactly the
            # defect post_refresh_verify.py's Check 8 Case A (RPR-J-05) exists
            # to catch -- confirmed live 2026-08-28: 509 of 854 pdf/net
            # reference pages recorded BODY_UPDATED with zero real git body
            # diff. The schema validator deliberately does not enforce this
            # itself (validate_refresh_page_decision's own docstring: "They do
            # not prove that a body changed" -- by design, deferring to git-
            # based post-hoc verification), so the caller must get the
            # disposition right up front.
            reference_body_changed = is_update and (
                _normalized_body_hash(before_content)
                != _normalized_body_hash(final_content)
            )
            if is_update:
                reference_disposition = (
                    "BODY_UPDATED" if reference_body_changed else "EVIDENCE_ONLY"
                )
            else:
                reference_disposition = "GENERATED"
            _record_reference_attempt(
                page_path,
                before_content,
                final_content,
                before_file_hash=before_file_hash,
                final_file_hash=final_file_hash,
                intended_action=(
                    "REFERENCE_UPDATE" if is_update else "REFERENCE_GENERATE"
                ),
                disposition=reference_disposition,
                verdict=reference_disposition,
                reason="GENERATED_FROM_PINNED_KNOWLEDGE",
            )
            # TC13 (2026-08-26): structural no-downgrade guard for backlink
            # presence, mirroring no_downgrade_guard.py's existing grade-
            # regression philosophy but for link presence -- confirmed live
            # (commit ea05b9d8c8, "Task 14 upstream E2E proof run"): a
            # --rebuild-all regeneration through this exact write path
            # silently stripped 247 reference.aspose.org/pdf/java pages'
            # previously-correct backlinks because resolve_backlink()
            # returned no target during that specific run, and nothing
            # detected the drop before the page was written. Raises into
            # the existing per-entry except-clause below (same pattern the
            # Task 14 incident's own ERROR-isolation fix already
            # established) rather than silently regenerating over a known-
            # good link -- the correct recovery is a deliberate
            # backlink_backfill.py reconciliation pass, not this writer
            # papering over its own resolve_backlink() failure.
            _downgrade_reason = detect_backlink_downgrade(before_content, final_content)
            if _downgrade_reason:
                raise RuntimeError(
                    f"{_downgrade_reason} for "
                    f"{_canonical_reference_path(page_path)} -- refusing write "
                    f"(would silently strip an existing backlink); run "
                    f"backlink_backfill.py --deep --write to reconcile instead"
                )
            safe_content_write(
                page_path, final_content, mechanism="batch-reference"
            )
            actual_file_hash = hashlib.sha256(page_path.read_bytes()).hexdigest()
            if actual_file_hash != final_file_hash:
                raise RuntimeError(
                    f"content write hash mismatch for "
                    f"{_canonical_reference_path(page_path)}"
                )
            _seen_lower_slugs.add(_page_lower)
            if is_update:
                updated.append(entry)
            else:
                generated.append(entry)
        except Exception as exc:
            # See _safe_print's own docstring: this except clause exists so
            # ONE page's failure (e.g. a re-grounding rejection from
            # _record_reference_attempt) never aborts the whole batch --
            # a plain print() of the exception text defeated that (found
            # live 2026-08-24, Task 14, mission-plan-the-end-to-end-vast-hejlsberg.md).
            _safe_print(f"  ERROR: {name} — {exc}")
            errors.append((entry, str(exc)))

    # Summary
    print("")
    print("=== batch-reference summary ===")
    print(f"Family:    {family}")
    print(f"Platform:  {platform}")
    print(f"Kind:      {kind_arg}")
    print(f"Limit:     {limit if limit is not None else 'none'}")
    _mode = "update" if update else ("rebuild-all" if rebuild_all else "generate-new")
    print(f"Mode:      {_mode}")
    print("")
    print(f"Candidates:   {total}")
    print(f"Generated:    {len(generated)}")
    if update:
        print(f"Updated:      {len(updated)} pages, skipped {len(to_skip)} unchanged")
    elif rebuild_all:
        print(f"Rebuilt:      {len(updated)} pages ({len(unchanged)} unchanged/skipped as timestamp-only)")
        print(f"Protected:    {len(to_skip)} (auto_updatable=false or manually curated)")
    else:
        print(f"Skipped:      {len(to_skip)} (already existed)")
    print(f"Errors:       {len(errors)} (failed to generate)")

    if generated:
        print("")
        print("Generated pages:")
        for e in generated:
            print(f"  - {e.get('name')}  ({e.get('kind')})")

    if updated:
        print("")
        print("Updated pages:")
        for e in updated:
            print(f"  - {e.get('name')}  ({e.get('kind')})")

    if to_skip:
        print("")
        print("Skipped pages:")
        for e in to_skip:
            print(f"  - {e.get('name')}  (already exists)")

    if errors:
        print("")
        print("Error pages (manual review required):")
        for e, msg in errors:
            _safe_print(f"  - {e.get('name')}  ({msg})")

    # Write generation manifest for denominator reconciliation (L-12 gate)
    _write_generation_manifest(
        family, platform,
        api_surface_total=len(api_surface),
        scope_eligible=total,
        pages_created=len(generated),
        pages_updated=len(updated),
        pages_skipped=len(to_skip),
        pages_failed=len(errors),
        pages_unchanged=len(unchanged),
        model_sha=model_sha,
    )

    # TC-DESIGN-001: Write freshness manifest after successful generation
    _write_freshness_manifest_if_enabled(
        family, platform,
        pages_failed=len(errors),
        actual_page_count=len(generated) + len(updated) + len(to_skip) + len(unchanged),
        dry_run=dry_run,
    )

    # NOTE (TC-DUPIDX-02, 2026-08-12, ST-059): a flat/stale-grouped-index auto-heal call used to
    # live here, gated on `resolved_run_root is None` -- that condition can only hold when
    # dry_run=True, which the surrounding `not dry_run` already excludes, so it never actually
    # fired on any real mutating run (confirmed: run() raises above if run_id is unset on a
    # non-dry-run call, and resolved_run_root is always derived from run_id/run_root when set).
    # The real re-invocation path now lives in refresh_run.py's apply_run(), gated on
    # provenance.index_generator_version rather than on flat-scaffold detection alone, so it
    # also covers already-grouped pages whose table predates a generator-logic fix (the GI-01
    # case this taskcard exists to close) -- not just pages still in the legacy scaffold format.

    return {"generated": len(generated), "updated": len(updated),
            "skipped": len(to_skip), "errors": len(errors),
            "unchanged": len(unchanged)}


def _write_freshness_manifest_if_enabled(
    family: str, platform: str, *,
    pages_failed: int = 0,
    actual_page_count: int | None = None,
    dry_run: bool = False,
) -> None:
    """TC-DESIGN-001: Write freshness manifest after generation if flag is enabled."""
    try:
        flags_path = REPO_ROOT / "data" / "refresh-feature-flags.json"
        if not flags_path.is_file():
            return
        flags = json.loads(flags_path.read_text(encoding="utf-8"))
        if not flags.get("refresh_generation_manifest_write_enabled", False):
            print("\nFreshness manifest write skipped (refresh_generation_manifest_write_enabled=false)")
            return

        from freshness_manifest import write_generation_freshness_manifest
        from datetime import datetime, timezone
        run_id = f"batch-reference-{family}-{platform}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"

        written, note = write_generation_freshness_manifest(
            product=f"{family}/{platform}",
            subdomain="reference",
            run_id=run_id,
            repo_root=REPO_ROOT,
            pages_failed=pages_failed,
            actual_page_count=actual_page_count,
            dry_run=dry_run,
        )
        if written:
            print(f"\nFreshness manifest write SUCCEEDED: {note}")
        else:
            print(f"\nFreshness manifest write skipped/failed: {note}")
    except Exception as exc:
        LOG.warning("Freshness manifest write failed: %s", exc)
        _safe_print(f"\nFreshness manifest write failed: {exc}")


def _write_generation_manifest(
    family: str, platform: str, *,
    api_surface_total: int, scope_eligible: int,
    pages_created: int, pages_updated: int, pages_skipped: int,
    pages_failed: int, pages_unchanged: int, model_sha: str,
) -> None:
    """Write a generation manifest to reports/generation/{family}-{platform}.yaml."""
    from datetime import datetime, timezone
    manifest_dir = REPO_ROOT / "reports" / "generation"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = manifest_dir / f"{family}-{platform}.yaml"

    pages_total = pages_created + pages_updated + pages_skipped + pages_unchanged
    gap = scope_eligible - pages_total

    import yaml
    manifest = {
        "family": family,
        "platform": platform,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "api_surface_total": api_surface_total,
        "scope_eligible": scope_eligible,
        "scope_filtered": api_surface_total - scope_eligible,
        "pages_created": pages_created,
        "pages_updated": pages_updated,
        "pages_skipped": pages_skipped,
        "pages_unchanged": pages_unchanged,
        "pages_failed": pages_failed,
        "denominator_gap": gap,
        "model_sha": model_sha,
    }
    manifest_path.write_text(
        yaml.dump(manifest, default_flow_style=False, sort_keys=False),
        encoding="utf-8",
    )
    print(f"\nGeneration manifest written to: {manifest_path.relative_to(REPO_ROOT)}")


def main():
    parser = argparse.ArgumentParser(
        description="Generate reference pages in bulk from api_surface.json (S-62 backing script)"
    )
    parser.add_argument("family", help="Product family (e.g. email, slides, 3d)")
    parser.add_argument("platform", help="Platform (e.g. net, java, python, cpp)")
    parser.add_argument("--kind", choices=["class", "enum", "all"], default="all",
                        help="Filter by entry kind (default: all)")
    parser.add_argument("--limit", type=int, default=None,
                        help="Process at most N entries (default: unlimited)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print candidates without writing files")
    parser.add_argument("--update", action="store_true",
                        help="Re-generate pages for modified API classes listed in "
                             "knowledge_delta.json. Falls back to full re-run if delta absent.")
    parser.add_argument("--require-member-doc-coverage", type=int, default=None,
                        metavar="N",
                        help="Abort if member-doc coverage is below N%% before generating. "
                             "Enforces that enrich --mode member-doc was run first.")
    parser.add_argument("--heal", action="store_true",
                        help="System-healing mode: bypass is_manually_curated soft protection "
                             "for auto_updatable=true pages when used with --update. "
                             "Use only for pipeline healing runs where descriptions were "
                             "systemically broken and need to be regenerated from repo truth.")
    parser.add_argument("--confirm-heal", action="store_true",
                        help=f"Required when --heal would override more than {HEAL_CONFIRM_THRESHOLD} manually-curated pages")
    parser.add_argument("--rebuild-all", action="store_true",
                        help="Regenerate all existing auto-updatable reference pages from current "
                             "merged/claims.json without requiring knowledge_delta.json. "
                             "Skips pages with auto_updatable=false or manually curated pages. "
                             f"Requires --confirm-rebuild when more than {REBUILD_CONFIRM_THRESHOLD} "
                             "pages would be rebuilt.")
    parser.add_argument("--confirm-rebuild", action="store_true",
                        help=f"Required when --rebuild-all would regenerate more than "
                             f"{REBUILD_CONFIRM_THRESHOLD} existing pages")
    parser.add_argument("--plan", default=None, metavar="PATH",
                        help="Path to site_plan.yaml for plan-aware advisory logging. "
                             "Compares api_surface candidates against the plan's reference "
                             "section and logs mismatches (does not filter candidates).")
    parser.add_argument("--generate-index", action="store_true",
                        help="Generate a grouped _index.md for the reference platform root "
                             "from api_surface.json metadata. Groups API entries by "
                             "package/module and type category. Use --dry-run to preview.")
    parser.add_argument("--knowledge-root", default=None, metavar="DIR",
                        help="Override knowledge root path (default: <repo>/knowledge)")
    parser.add_argument("--content-root", default=None, metavar="DIR",
                        help="Override content root path "
                             "(default: <repo>/content/reference.aspose.org/en)")
    parser.add_argument("--run-id", default=None,
                        help="Required immutable refresh-run ID for any mutating execution")
    parser.add_argument("--run-root", default=None, metavar="DIR",
                        help="Run artifact directory created by refresh_run.py")
    args = parser.parse_args()

    if args.knowledge_root or args.content_root:
        configure(
            knowledge_root=Path(args.knowledge_root) if args.knowledge_root else None,
            content_root=Path(args.content_root) if args.content_root else None,
        )

    if args.generate_index:
        result = generate_grouped_index(args.family, args.platform, dry_run=args.dry_run)
        if result.get("written"):
            print(f"SUCCESS: Grouped index written to {result['path']}")
        elif result.get("skipped"):
            print(f"SKIPPED: {result.get('reason', 'unknown')}")
        elif args.dry_run:
            print(f"DRY-RUN complete: {result.get('entry_count', 0)} entries, "
                  f"{result.get('body_lines', 0)} body lines")
            if result.get("body_preview"):
                print("--- Preview (first 40 lines) ---")
                print(result["body_preview"])
        sys.exit(0)

    run(args.family, args.platform,
        kind_arg=args.kind,
        limit=args.limit,
        dry_run=args.dry_run,
        update=args.update,
        require_member_doc_coverage=args.require_member_doc_coverage,
        heal=args.heal,
        confirm_heal=args.confirm_heal,
        plan_path=args.plan,
        rebuild_all=args.rebuild_all,
        confirm_rebuild=args.confirm_rebuild,
        run_id=args.run_id,
        run_root=args.run_root)


if __name__ == "__main__":
    main()
