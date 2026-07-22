"""site_planner.py — Deterministic site manifest generator.

Generates a site_plan.yaml for a given family/platform by loading knowledge
artifacts, running cluster detection, applying evidence thresholds, and
producing a structured plan covering all five site sections
(products, blog, docs, kb, reference).

Usage:
    python scripts/pipeline/commands/launch/site_planner.py {family} {platform}
        [--mode launch|update|section]
        [--section products|docs|blog|kb|reference]
        [--dry-run]
        [--detect-clusters]
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import yaml

# ---------------------------------------------------------------------------
# Repo root — always resolve from script location
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).resolve().parents[2]  # commands/launch/ -> commands/ -> pipeline/
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from core.fs import atomic_write  # noqa: E402
from core.constants import _INTERNAL_PATH_PATTERNS  # noqa: E402  (C1-SYS filter)
_LIB_DIR = str(Path(__file__).resolve().parents[2] / "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
from knowledge_core import Knowledge  # noqa: E402
REPO_ROOT = SCRIPT_DIR.parent.parent  # scripts/pipeline/ -> scripts/ -> repo root

KNOWLEDGE_ROOT = REPO_ROOT / "knowledge"
CONTENT_ROOT = REPO_ROOT / "content"
REPORTS_ROOT = REPO_ROOT / "reports" / "plans"

_REFRESH_FLAGS_PATH = REPO_ROOT / "data" / "refresh-feature-flags.json"


def _load_refresh_flags() -> dict:
    """Load refresh feature flags. Returns safe defaults if file is missing.

    TC-PROD-010A: Used to gate the per-surface decision engine at the SHA gate.
    All flags default to safe (engine not enforced, behavior unchanged).
    """
    defaults = {
        "refresh_decision_engine_enabled": False,
        "refresh_decision_engine_shadow": True,
        "refresh_reconciliation_shadow": True,
        "refresh_reconciliation_enforced": False,
        "refresh_manifest_write_enabled": False,
        "refresh_content_write_enabled": False,
        "refresh_run_type_label_enabled": True,
    }
    if not _REFRESH_FLAGS_PATH.is_file():
        return defaults
    try:
        data = json.loads(_REFRESH_FLAGS_PATH.read_text(encoding="utf-8"))
        defaults.update(data)
        return defaults
    except (OSError, json.JSONDecodeError):
        return defaults

# Site path patterns (relative to CONTENT_ROOT parent, i.e. REPO_ROOT)
SITE_PATHS = {
    "products": "content/products.aspose.org/en/{family}/{platform}",
    "reference": "content/reference.aspose.org/en/{family}/{platform}",
    "docs":      "content/docs.aspose.org/en/{family}/{platform}",
    "blog":      "content/blog.aspose.org/{family}/{platform}",
    "kb":        "content/kb.aspose.org/en/{family}/{platform}",
}

# Platform suffix used in KB how-to filenames
KB_PLATFORM_SUFFIX = {
    "python":     "python",
    "java":       "java",
    "net":        "dotnet",
    "cpp":        "cpp",
    "typescript": "typescript",
}

# Troubleshooting eligibility — platforms where a troubleshooting page is generated
# when howto_count >= 6 (see plan_kb).  net and java added 2026-04-07 healing sprint:
# these platforms produce enough how-to articles to warrant a troubleshooting page.
TROUBLE_PLATFORMS = {"typescript", "python", "cpp", "net", "java"}


# ---------------------------------------------------------------------------
# Helper: slug
# ---------------------------------------------------------------------------

def slug_from_category(category: str) -> str:
    """Convert category name to URL slug."""
    return re.sub(r"[^a-z0-9]+", "-", category.lower()).strip("-")


# ---------------------------------------------------------------------------
# Helper: KB verb detection
# ---------------------------------------------------------------------------

_VERB_KEYWORDS: list[tuple[list[str], str]] = [
    (["load", "read", "open", "import"],                      "load"),
    (["save", "write", "export"],                             "export"),
    (["convert", "transform"],                                "convert"),
    (["render"],                                              "render"),
    (["create", "generate", "construct"],                     "create"),
    (["build"],                                               "build"),
    (["add", "insert", "append"],                             "add"),
    (["parse", "extract", "inspect", "analyze"],              "extract"),
    (["traverse"],                                            "traverse"),
    (["optimize", "compress"],                                "optimize"),
    # Sub-package cluster names mapped to meaningful verbs
    (["format"],                                              "convert"),   # format-support → convert
    (["scene-manage", "scene-management"],                    "load"),      # scene-management → load
    (["scene-entit", "entities", "mesh"],                     "build"),     # scene-entities → build
    (["animation"],                                           "add"),       # animation → add
    (["material", "shading"],                                 "add"),       # materials → add
    # Cross-family cluster labels (from _SUBPKG_LABEL)
    (["message-pars", "msg"],                                 "extract"),   # message-parsing → extract
    (["compound-file", "cfb"],                                "load"),      # compound-file-support → load
    (["presentation-content", "pptx"],                        "create"),    # presentation-content → create
    (["visual-effect", "effects"],                            "add"),       # visual-effects → add
    (["export-render"],                                       "export"),    # export-rendering → export
    (["package-manage", "opc"],                               "build"),     # package-management → build
    (["drawing-shape", "drawing"],                            "add"),       # drawing-shapes → add
    (["note-document"],                                       "load"),      # note-document → load
    (["save-export", "saving"],                               "export"),    # save-export → export
    (["onestore-format", "onestore"],                         "load"),      # onestore-format → load
    (["spreadsheet-oper", "cells"],                           "create"),    # spreadsheet-operations → create
    (["xml-process"],                                         "extract"),   # xml-processing → extract
    (["app-properties"],                                      "extract"),   # app-properties → extract
    (["comment"],                                             "add"),       # comments → add
    (["core-properties"],                                     "extract"),   # core-properties → extract
    (["presentation-struct"],                                 "create"),    # presentation-structure → create
    (["presentation-manage"],                                 "create"),    # presentation-management → create
    (["spreadsheet-manage"],                                  "create"),    # spreadsheet-management → create
    (["email-process"],                                       "extract"),   # email-processing → extract
    (["document-manage"],                                     "load"),      # document-management → load
    (["core-manage"],                                         "work-with"), # core-management (generic) → work-with
    (["theme-styl"],                                          "add"),       # theme-styling → add
    # --- PDF clusters ---
    (["annotations-form"],                                    "add"),       # annotations-forms → add
    (["text-extract"],                                        "extract"),   # text-extraction → extract
    (["content-oper"],                                        "work-with"), # content-operations → work-with
    (["facades-api"],                                         "work-with"), # facades-api → work-with
    (["logical-struct"],                                      "create"),    # logical-structure → create
    (["page-generat"],                                        "create"),    # page-generation → create
    (["graphics-draw"],                                       "add"),       # graphics-drawing → add
    (["devices-render"],                                      "render"),    # devices-rendering → render
    (["conversion-optim"],                                    "convert"),   # conversion-optimization → convert
    (["security-sign"],                                       "add"),       # security-signatures → add
    (["navigation-action"],                                   "add"),       # navigation-actions → add
    (["metadata-util"],                                       "extract"),   # metadata-utilities → extract
]

# Clusters that should NOT generate KB howto pages (reference-only).
# Also excluded from docs developer-guide topic pages.
KB_SKIP_CLUSTERS = {
    "utilities", "math", "enumerations", "constants", "general",
    "internal-utilities", "core-api",
}

# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------

_SAFE_ARG_RE = re.compile(r'^[a-z0-9][a-z0-9\-]*[a-z0-9]$')


def _validate_arg(name: str, value: str) -> None:
    """Validate a family/platform argument is a safe slug (no path traversal)."""
    if not _SAFE_ARG_RE.match(value):
        print(
            f"SITE-PLAN ERROR: Invalid {name} argument {value!r}. "
            r"Must match: ^[a-z0-9][a-z0-9\-]*[a-z0-9]$",
            file=sys.stderr,
        )
        sys.exit(1)


def detect_kb_verb(category: str) -> str:
    """Map cluster category to KB how-to verb."""
    cl = category.lower()
    for keywords, verb in _VERB_KEYWORDS:
        if any(kw in cl for kw in keywords):
            return verb
    # Fallback: "work-with" is a safe generic verb for any unrecognized category.
    # Never return a raw sub-package/category name as a verb.
    return "work-with"


def _kb_noun_from_cluster(category: str, family: str, verb: str = "") -> str:
    """Derive a concise KB howto noun from the cluster category name.

    Algorithm (family-agnostic):
    1. Convert category to URL slug.
    2. Strip structural suffixes that add no meaning to a slug.
    3. Strip the verb prefix from the noun if it starts with the verb (avoids
       duplication like "export-export-rendering" → "rendering").
    4. Prefix very generic nouns with the family name for disambiguation.
    """
    base = slug_from_category(category)
    # Strip structural suffixes
    for suffix in ("-support", "-management", "-operations", "-processing", "-handling"):
        if base.endswith(suffix):
            base = base[: -len(suffix)]
            break
    # Strip verb to avoid duplication (e.g. "export-rendering" with verb "export")
    # TC-KBS-003: also strip nominal forms (-{verb}ion, -{verb}ing) to prevent
    # slugs like "how-to-extract-text-extraction" where verb "extract" appears
    # in the noun as "extraction".
    #
    # words/net launch (2026-07-23, TC-KBS-021): this dict must cover every verb
    # _VERB_KEYWORDS can produce ("load", "export", "build", "add", "traverse"
    # were missing entirely) — _validate_kb_slugs's Check 2 re-derives the verb
    # generically (verb + "ion"/"ing"/"tion"/"ation") from the slug text itself,
    # so any verb missing its regular nominal form here passes generation
    # unstripped and then fails validation as a false "duplication" (confirmed
    # live: category="loading", verb="load" — "load" had no entry, so noun
    # stayed "loading" and Check 2 correctly rejected "how-to-load-loading-dotnet").
    #
    # Every verb also gets its bare "-ing" gerund listed explicitly: unlike
    # "-ion"/"-tion"/"-ation" (whose correct spelling is verb-specific — e.g.
    # "convert" + "ion" concatenates to "convertion", not the real word
    # "conversion" — so it can't be derived generically), "-ing" is a regular
    # English nominalization for every verb, and Check 2 always tests for it.
    # Without an explicit entry, verbs whose *other* nominal form doesn't
    # happen to end in "-ing" (e.g. "extract" -> "extraction") leave a bare
    # "-ing" category (e.g. "extracting") unstripped.
    _VERB_NOMINAL_FORMS: dict[str, list[str]] = {
        "extract":   ["extraction", "extracting"],
        "convert":   ["conversion", "converting"],
        "render":    ["rendering"],
        "optimize":  ["optimization", "optimizing"],
        "parse":     ["parsing"],
        "create":    ["creation", "creating"],
        "generate":  ["generation", "generating"],
        "compress":  ["compression", "compressing"],
        "encrypt":   ["encryption", "encrypting"],
        "protect":   ["protection", "protecting"],
        "load":      ["loading"],
        "export":    ["exporting", "exportation"],
        "build":     ["building"],
        "add":       ["adding", "addition"],
        "traverse":  ["traversing", "traversal"],
    }
    if verb:
        nominal_forms = _VERB_NOMINAL_FORMS.get(verb, [])
        if base == verb or base in nominal_forms:
            # Edge case: category name IS the verb or its bare nominal form
            # (e.g. category="render"/"rendering", verb="render"; or
            # category="loading", verb="load"). Use family name as noun to
            # avoid how-to-render-render / how-to-load-loading duplication.
            # e.g. "render" + family "3d" → noun "3d" → "how-to-render-3d-dotnet".
            base = family
        elif base.startswith(f"{verb}-") and len(base) > len(verb) + 1:
            base = base[len(verb) + 1:]
        elif base.endswith(f"-{verb}") and len(base) > len(verb) + 1:
            base = base[: -(len(verb) + 1)]
        else:
            # Strip nominal forms of the verb (e.g. "-extraction" when verb="extract")
            for form in nominal_forms:
                if base.endswith(f"-{form}") and len(base) > len(form) + 1:
                    base = base[: -(len(form) + 1)]
                    break
    # Prefix generic/ambiguous nouns with family name
    _GENERIC_NOUNS = {"models", "files", "data", "objects", "items", "elements", "scenes"}
    if base in _GENERIC_NOUNS:
        base = f"{family}-{base}"
    else:
        # TC-KBS-022 (2026-07-23): self-heal _validate_kb_slugs's Check 3
        # (_KB_GENERIC_NOUNS) and Check 4 / C4 (_FAMILY_PRODUCT_KEYWORDS)
        # instead of requiring a hand-curated _FAMILY_SUBPKG_LABELS entry for
        # every new subpackage name a family's real codebase happens to
        # introduce. A static audit — driving every (family, category) pair
        # reachable from _SUBPKG_LABEL/_FAMILY_SUBPKG_LABELS/_ROOT_LABELS
        # through the real plan_kb(), across all 11 families registered in
        # data/products.json, excluding categories KB_SKIP_CLUSTERS filters
        # out before they'd ever reach validation — found 110 combinations
        # that would crash the moment any family's actual source tree
        # produced them; cross-family generic labels like "core-properties"
        # or "logical-structure" carry no family-specific word by
        # construction. Mirrors the validator's two checks exactly and
        # applies the fix the ValueError message itself already suggests
        # (option 1: prefix the noun with the family term). This can only
        # ever fire for a noun the validator would otherwise reject outright —
        # it is a strict no-op for any noun already passing both checks, so it
        # cannot change a slug any already-shipped, already-passing page uses.
        primary = base.split("-")[0]
        needs_prefix = primary in _KB_GENERIC_NOUNS
        if not needs_prefix and "-" in base:
            family_keywords = _FAMILY_PRODUCT_KEYWORDS.get(family, frozenset())
            noun_words = base.split("-")
            if family_keywords and not any(
                word.startswith(kw) for word in noun_words for kw in family_keywords
            ):
                needs_prefix = True
        if needs_prefix:
            base = f"{family}-{base}"
    return base or slug_from_category(category)


def _page_slug(path: str, family: str, platform: str) -> str:
    """Derive the slug field from a content path string.

    Strips the subdomain prefix, removes .md extension, and for blog posts
    removes the trailing /index component.
    """
    prefixes = [
        f"content/docs.aspose.org/en/{family}/{platform}/",
        f"content/kb.aspose.org/en/{family}/{platform}/",
        f"content/products.aspose.org/en/{family}/{platform}/",
        f"content/products.aspose.org/en/{family}/",
        f"content/blog.aspose.org/{family}/{platform}/",
        f"content/reference.aspose.org/en/{family}/{platform}/",
    ]
    for prefix in prefixes:
        if path.startswith(prefix):
            suffix = path[len(prefix):]
            if suffix.endswith(".md"):
                suffix = suffix[:-3]
            if suffix.endswith("/index"):
                suffix = suffix[:-6]
            return suffix
    # Fallback: stem of filename
    return Path(path).stem


# ---------------------------------------------------------------------------
# Helper: family slug convention
# ---------------------------------------------------------------------------

def detect_family_slug_convention(family: str, category: str) -> str:
    """Apply family-specific slug convention for docs topic slugs."""
    base = slug_from_category(category)
    if family in ("slides", "cells"):
        return f"working-with-{base}"
    # note, 3d, email, default → bare noun form
    return base


# ---------------------------------------------------------------------------
# Helper: license file finder
# ---------------------------------------------------------------------------

def find_license_file(clone_cache_dir: Path) -> Optional[Path]:
    """Check for license files in clone cache. Returns first found or None.

    Primary: dedicated license files at repo root.
    Secondary: README.md containing a recognised license keyword — covers repos that
    declare MIT/Apache/GPL in their README rather than a separate LICENSE file (common
    in NuGet-only packages where the license is embedded in the .csproj PackageLicenseExpression).
    """
    candidates = ["LICENSE", "LICENSE.txt", "LICENSE.md", "COPYING", "COPYING.txt"]
    for name in candidates:
        p = clone_cache_dir / name
        if p.exists():
            return p
    # Secondary: README.md mentioning a known SPDX license identifier
    readme = clone_cache_dir / "README.md"
    if readme.exists():
        try:
            text = readme.read_text(encoding="utf-8", errors="replace").lower()
            _LICENSE_KEYWORDS = (
                "mit license", "mit-license", "mit licensed", "mit-licensed",
                "apache license", "apache-2.0",
                "gpl", "lgpl", "bsd license", "bsd-2", "bsd-3",
                "unlicense", "isc license",
            )
            if any(kw in text for kw in _LICENSE_KEYWORDS):
                return readme
        except OSError:
            pass
    return None


# ---------------------------------------------------------------------------
# Helper: launch tier detection
# ---------------------------------------------------------------------------

def detect_launch_tier(family: str, platform: str) -> str:
    """Detect launch tier: placeholder | partial | full."""
    present = {}
    for section, pattern in SITE_PATHS.items():
        path = REPO_ROOT / pattern.format(family=family, platform=platform)
        present[section] = path.exists() and any(path.rglob("*.md"))

    has_products = present.get("products", False)
    secondary = [present.get(s, False) for s in ("docs", "kb", "blog", "reference")]

    if not has_products and not any(secondary):
        return "placeholder"
    if has_products and all(secondary):
        return "full"
    if has_products or any(secondary):
        return "partial"
    return "placeholder"


# ---------------------------------------------------------------------------
# Existing-content discovery (reconciliation for launched products)
# ---------------------------------------------------------------------------

def _read_frontmatter(path: Path) -> dict:
    """Read YAML frontmatter from a markdown file.  Returns {} on failure."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {}
    if not text.startswith("---"):
        return {}
    end = text.find("---", 3)
    if end < 0:
        return {}
    try:
        return yaml.safe_load(text[3:end]) or {}
    except yaml.YAMLError:
        return {}


def discover_existing_content(
    family: str, platform: str
) -> dict[str, list[dict]]:
    """Scan content directories for existing .md files.

    Returns dict keyed by section name with lists of page descriptors:
      {slug, path, frontmatter_cluster, frontmatter_evidence}
    """
    result: dict[str, list[dict]] = {}
    plat_suffix = KB_PLATFORM_SUFFIX.get(platform, platform)

    for section, pattern in SITE_PATHS.items():
        content_dir = CONTENT_ROOT.parent / pattern.format(
            family=family, platform=platform
        )
        if not content_dir.exists():
            result[section] = []
            continue

        pages: list[dict] = []
        for md_file in sorted(content_dir.rglob("*.md")):
            # Skip translated locale files (e.g. index.ar.md, _index.de.md)
            stem = md_file.stem  # e.g. "index.ar" or "index" or "faq"
            if "." in stem:
                continue  # locale variant — skip

            rel = md_file.relative_to(CONTENT_ROOT.parent).as_posix()
            fm = _read_frontmatter(md_file)

            # Derive slug from path
            slug = _page_slug(rel, family, platform)

            # Extract cluster hint from frontmatter evidence block
            evidence = fm.get("evidence", {})
            fm_cluster = ""
            if isinstance(evidence, dict):
                fm_cluster = evidence.get("cluster", "")

            provenance = fm.get("provenance", {}) if isinstance(fm, dict) else {}
            auto_updatable = bool(provenance.get("auto_updatable", True))

            pages.append({
                "slug": slug,
                "path": rel,
                "filename": md_file.name,
                "frontmatter_cluster": fm_cluster,
                "title": fm.get("title", ""),
                "auto_updatable": auto_updatable,
            })

        result[section] = pages

    return result


def _match_existing_to_cluster(
    existing_pages: list[dict],
    cluster_category: str,
    cluster_slug: str,
    cluster_class_names: list[str],
    section: str,
    family: str,
) -> dict | None:
    """Try to find an existing page that covers the given cluster.

    Matching priority:
    1. Frontmatter cluster field matches cluster_category
    2. Slug contains the cluster slug (e.g. 'format-support' in 'format-support.md')
    3. Semantic synonym mapping (e.g. 'format-support' matches 'convert-3d-models')
    4. Keyword overlap between slug and cluster category/class names
    """
    # Skip section-index and fixed pages
    skip_slugs = {"_index", "faq", "use-cases", "troubleshooting",
                  "getting-started/_index", "developer-guide/_index",
                  "getting-started/installation", "getting-started/quickstart",
                  "getting-started/license",
                  "developer-guide/features"}

    candidates = [p for p in existing_pages if p["slug"] not in skip_slugs]

    # Priority 1: frontmatter cluster match
    for page in candidates:
        if page["frontmatter_cluster"] and (
            page["frontmatter_cluster"].lower() == cluster_category.lower()
            or slug_from_category(page["frontmatter_cluster"]) == cluster_slug
        ):
            return page

    # Priority 2: slug contains cluster slug
    for page in candidates:
        slug = page["slug"]
        # For docs: slug is like 'developer-guide/scene-graph'
        if section == "docs":
            slug_part = slug.split("/")[-1] if "/" in slug else slug
        else:
            slug_part = slug
        if cluster_slug in slug_part:
            return page

    # Priority 3: semantic synonym matching
    # Maps cluster categories to known synonyms found in production slugs
    _CLUSTER_SYNONYMS: dict[str, list[str]] = {
        "format-support": ["convert", "format", "fbx", "gltf", "stl", "obj", "3ds",
                           "models", "3d-models", "formats"],
        "scene-management": ["load", "scene", "model-loading", "save", "3d-models",
                             "3d-scenes", "open"],
        "scene-entities": ["mesh", "scene-graph", "entities", "node", "geometry",
                           "build-mesh"],
        "animation": ["animation", "animate", "keyframe"],
        "materials-shading": ["material", "shading", "render", "rendering",
                              "texture", "pbr", "visual"],
        "rendering": ["render", "rendering", "export", "image", "visual"],
        # Cross-family
        "presentation-content": ["presentation", "slide", "pptx", "create-presentation"],
        "visual-effects": ["effect", "3d-effect", "visual", "transition"],
        "export-rendering": ["export", "render", "pdf", "image", "save"],
        "drawing-shapes": ["shape", "drawing", "connector", "add-shape"],
        "message-parsing": ["email", "parse", "msg", "eml", "message"],
        "note-document": ["onenote", "note", "document", "load"],
        "save-export": ["export", "save", "pdf"],
        "spreadsheet-operations": ["excel", "spreadsheet", "cell", "chart",
                                   "formula", "csv", "worksheet"],
        "comments": ["comment", "add-comment"],
        "theme-styling": ["theme", "style", "format-text"],
        # SQ-10: concat-form synonyms for pages generated before CamelCase splitting was fixed
        "javascript-extensions": ["javascriptextensions"],
        "logical-structure": ["logicalstructure"],
        # font family root cluster renamed from core-management → font-management
        "font-management": ["core", "font", "core-management"],
    }

    synonyms = _CLUSTER_SYNONYMS.get(cluster_slug, [])
    if synonyms:
        best_match = None
        best_score = 0
        for page in candidates:
            slug = page["slug"]
            if section == "docs":
                slug_part = slug.split("/")[-1] if "/" in slug else slug
            else:
                slug_part = slug
            slug_words = set(slug_part.split("-"))
            # Remove common noise words from slug
            slug_words -= {"how", "to", "in", "with", "for", "the", "a", "an",
                           "from", "and", "or"}
            # Also remove platform suffix
            slug_words -= set(KB_PLATFORM_SUFFIX.values())
            slug_words -= {"python", "java", "dotnet", "cpp", "typescript", "net"}
            score = sum(1 for syn in synonyms if syn in slug_part or syn in slug_words)
            if score > best_score:
                best_score = score
                best_match = page
        if best_score >= 1 and best_match:
            return best_match

    # Priority 4: keyword overlap (cluster category words vs slug words)
    cat_words = set(cluster_slug.split("-"))
    cat_words -= {"support", "management", "operations", "the", "and", "for", "in"}
    if len(cat_words) >= 1:
        best_match = None
        best_overlap = 0
        for page in candidates:
            slug_words = set(page["slug"].replace("/", "-").split("-"))
            overlap = len(cat_words & slug_words)
            if overlap > best_overlap:
                best_overlap = overlap
                best_match = page
        if best_overlap >= 1 and best_match:
            return best_match

    return None


# ---------------------------------------------------------------------------
# Cluster detection
# ---------------------------------------------------------------------------

def _extract_class_from_claim(text: str) -> str:
    """Extract class name from 'ClassName.method(...)' claim text."""
    dot = text.find(".")
    if dot > 0:
        return text[:dot]
    return ""


# Sub-package → human-readable capability cluster label.
# Keys are the directory component immediately inside the top-level package dir
# (e.g. "formats", "entities", "animation").  The sentinel "" covers root-level classes.
# Cross-family: covers 3D, slides, cells, email, note sub-packages observed in real repos.
_SUBPKG_LABEL: dict[str, str] = {
    # --- 3D family ---
    "formats":    "format-support",
    "entities":   "scene-entities",
    "animation":  "animation",
    "utilities":  "utilities",
    "shading":    "materials-shading",
    "rendering":  "rendering",
    "threed":     "scene-management",
    # --- Email family ---
    "msg":        "message-parsing",
    "cfb":        "compound-file-support",
    # --- Slides family ---
    "pptx":       "presentation-content",
    "effects":    "visual-effects",
    "export":     "export-rendering",
    "opc":        "package-management",
    "drawing":    "drawing-shapes",
    "internal":   "internal-utilities",
    "private":    "internal-utilities",  # C1-SYS: _private/_internal/_impl → skip cluster
    "foss":       "core-api",
    "apppropertiespart":   "app-properties",
    "commentspart":        "comments",
    "corepropertiespart":  "core-properties",
    "presentationpart":    "presentation-structure",
    "xml":        "xml-processing",
    "theme":      "theme-styling",
    # --- Note family ---
    "note":       "note-document",
    "saving":     "save-export",
    "onestore":   "onestore-format",
    # --- Cells family ---
    "cells":      "spreadsheet-operations",
    # --- Sentinel ---
    "_unknown":   "general",
}

# Family-specific sub-package label overrides.
# Applied in _subpkg_to_label() before the generic slug_from_category() fallback.
# Prevents generic sub-package names (e.g. "core") from producing bad cluster labels.
# Maps family name to the cluster label used for root-level (package-less) classes.
# Promoted to module level (was a local in _subpkg_to_label) so promote.py can hash it
# for extractor config provenance (config_sha in model.yaml).
_ROOT_LABELS: dict[str, str] = {
    "3d": "scene-management",
    "barcode": "barcode-generation",
    "slides": "presentation-management",
    "cells": "spreadsheet-management",
    "email": "email-processing",
    "font": "font-management",
    "note": "document-management",
    "pdf": "document-management",
    # words/net launch (2026-07-23, TC-KBS-021): without an entry here, words'
    # root-level classes fell to the generic default "core-management", whose
    # noun "core" is in _KB_GENERIC_NOUNS — confirmed live, this crashed
    # `words python` site-plan regeneration (a pre-existing, already-shipped
    # product) too, independent of the words/net launch.
    "words": "word-processing",
}

_FAMILY_SUBPKG_LABELS: dict[str, dict[str, str]] = {
    "barcode": {
        "":          "barcode-generation",   # Root-level Barcode/BarcodeService classes
        "encoders":  "barcode-generation",   # Encoder implementation classes
        "models":    "encode-options",       # Options/model classes (EncodeOptions, etc.)
        "renderers": "barcode-rendering",    # SvgRenderer, PngRenderer, PdfRenderer
        "parsers":   "input-parsing",        # Parser implementation classes
        "profiles":  "symbology-profiles",   # Symbology profile registry
        "standards": "barcode-standards",    # Standards/validation classes
        "text":      "text-rendering",       # Text rendering classes
        "qr":        "qr-generation",        # QR-specific classes
        # Note: "_internal" direct children fall through to
        # _SUBPKG_LABEL["internal"] = "internal-utilities" → KB_SKIP_CLUSTERS
    },
    "cells": {
        "core":       "cells-foss-model",    # Value-object/model classes in cells_foss core/
        "packaging":  "xlsx-packaging",      # OPC/XLSX packaging classes in cells_foss packaging/
        "cells_foss": "spreadsheet-management",  # Root-level cells_foss classes
        "validation": "data-validation",     # Data validation rules (TC-KBS-005)
    },
    "pdf": {
        # RC-5 fix (TC-KBS-015): merged labels now include "pdf" product qualifier
        # so slugs are self-contained without URL path context.
        "annotations":          "pdf-annotations",   # was "annotations-forms"
        "forms":                "pdf-annotations",   # was "annotations-forms"
        "text":                 "text-extraction",
        "content":              "content-operations",
        "facades":              "facades-api",
        "logicalstructure":     "logical-structure",
        "tagged":               "logical-structure",
        "structure":            "logical-structure",
        # words/net launch (2026-07-23, TC-KBS-021): "page-generation" had no
        # pdf qualifier, confirmed live to crash `pdf net` site-plan
        # regeneration (a pre-existing, already-shipped product), independent
        # of the words/net launch — same C4 gap as this family's other
        # already-qualified labels below ("pdf-annotations", "pdf-graphics",
        # "pdf-metadata"). No existing content matched this cluster's slug via
        # frontmatter/exact-substring at the time of this fix (still matches
        # via the keyword-overlap fallback — verified empirically).
        "generator":            "pdf-page-generation",   # was "page-generation"
        "stamps":               "pdf-page-generation",   # was "page-generation"
        "drawing":              "pdf-graphics",      # was "graphics-drawing"
        "shading":              "pdf-graphics",      # was "graphics-drawing"
        "color":                "pdf-graphics",      # was "graphics-drawing"
        "vector":               "pdf-graphics",      # was "graphics-drawing"
        "devices":              "devices-rendering",
        "printing":             "devices-rendering",
        "converters":           "conversion-optimization",
        "optimization":         "conversion-optimization",
        "html":                 "conversion-optimization",
        "security":             "security-signatures",
        "navigation":           "navigation-actions",
        "actions":              "navigation-actions",
        "xmp":                  "pdf-metadata",      # was "metadata-utilities"
        "collections":          "pdf-metadata",      # was "metadata-utilities"
        "artifacts":            "pdf-metadata",      # was "metadata-utilities"
        "functions":            "pdf-metadata",      # was "metadata-utilities"
        "geometry":             "pdf-metadata",      # was "metadata-utilities"
        "interop":              "pdf-metadata",      # was "metadata-utilities"
        "groupprocessor":       "pdf-metadata",      # was "metadata-utilities"
        "javascriptextensions": "javascript-extensions",  # TC-KBS-001: C# namespace fix
    },
    "words": {
        # words/net launch (2026-07-23): Aspose.Words.NET has real namespaces
        # ("Drawing", "LinksAndReferences", "IndexAndTables") that either fall
        # through to a generic cross-family _SUBPKG_LABEL entry (built for
        # slides' PowerPoint-shape "drawing" namespace) or the CamelCase-split
        # fallback — neither includes a words-specific qualifier, so C4
        # (_FAMILY_PRODUCT_KEYWORDS) rejects the resulting KB slug as
        # ambiguous without URL context. Mirrors pdf's RC-5/TC-KBS-015 fix:
        # add the product qualifier at the label level rather than loosen
        # the keyword allowlist.
        "drawing":            "word-drawing-shapes",       # was generic "drawing-shapes" (slides)
        "linksandreferences": "word-links-and-references",
        "indexandtables":     "word-index-and-tables",
    },
}


def _class_to_subpackage(file_path: str) -> str:
    """Derive sub-package label from a class file path.

    'aspose/threed/entities/Mesh.py'       → 'entities'
    'aspose/threed/formats/fbx/Foo.py'     → 'formats'   (flatten all format sub-pkgs)
    'aspose/threed/Scene.py'               → ''           (root-level → 'scene-management')
    '' or None                             → '_unknown'   (sentinel; maps to 'general' cluster)
    """
    if not file_path:
        return "_unknown"
    parts = file_path.replace("\\", "/").split("/")
    # Expected structure: org_ns / top_pkg [/ subpkg [/ sub_subpkg]] / ClassName.py
    # parts[-1] is always ClassName.py
    # parts[-2] is either a subpkg dir or the top-level package root dir.
    if len(parts) >= 4:
        # At least 4 components: org / top_pkg / subpkg / ClassName.py
        subpkg = parts[-2]
        # Flatten all format sub-sub-packages (fbx, obj, stl, etc.) → "formats"
        # by checking if any ancestor component is "formats"
        ancestors = parts[:-1]
        if "formats" in ancestors:
            return "formats"
        if "." not in subpkg:
            return subpkg
    elif len(parts) == 3 and parts[0].lower() == "src":
        # C# flat-src layout: src/{SubDir}/Class.cs (3 parts)
        # PascalCase directory names (Annotations, Text, Forms) are sub-packages.
        # Dotted names (Aspose.Slides.Foss) or underscored names (cells_foss)
        # are namespace roots, not sub-packages.
        # Guard: parts[0] must be "src" to distinguish from Python layouts
        # like aspose/threed/Scene.py where parts[1] is a package root.
        candidate = parts[1]
        if "." not in candidate and "_" not in candidate:
            return candidate
    # Root-level → return ""
    return ""


def _subpkg_to_label(subpkg: str, family: str) -> str:
    """Map sub-package directory name to capability cluster label."""
    # Normalize: strip leading underscores, lowercase for lookup
    key = subpkg.lstrip("_").lower()
    # Family-specific override first (prevents cross-family label collisions)
    if family in _FAMILY_SUBPKG_LABELS and key in _FAMILY_SUBPKG_LABELS[family]:
        return _FAMILY_SUBPKG_LABELS[family][key]
    if key in _SUBPKG_LABEL:
        return _SUBPKG_LABEL[key]
    if key == "" or subpkg == "":
        # Root-level classes → family-specific core capability
        return _ROOT_LABELS.get(family, "core-management")
    # TC-KBS-002: For unmapped PascalCase names (e.g. C# namespace dirs like
    # "JavaScriptExtensions"), split on CamelCase word boundaries before
    # slugifying. Without this, "JavaScriptExtensions" → "javascriptextensions"
    # (an opaque token). With it → "javascript-extensions" (readable slug).
    _camel_boundary = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")
    split = _camel_boundary.sub("-", subpkg).lower().strip("-")
    split = re.sub(r"-{2,}", "-", split)
    return slug_from_category(split)


def detect_clusters(
    claims: list[dict],
    api_surface: list[dict],
    snippet_index: list[dict],
    limitations_text: str,
    family: str = "",
) -> list[dict]:
    """Detect capability-area content clusters from api_surface sub-packages.

    Groups API classes by their source sub-package directory (e.g. 'formats',
    'entities', 'animation'), then aggregates claim counts from claims.json.
    This yields ~4–8 high-level clusters per product (matching the real
    developer-guide page count) rather than one cluster per class.

    Returns list of cluster dicts sorted by claim_count descending:
        {
          category: str,          # e.g. "format-support", "scene-management"
          slug: str,              # URL-safe cluster name
          claim_count: int,
          api_method_count: int,
          snippet_count: int,
          in_limitations: bool,
          class_names: list[str], # classes belonging to this cluster
        }
    """
    # ----- 0. Build class → visibility lookup for S-2 weighting -----
    _VISIBILITY_WEIGHT = {"exported": 3.0, "public": 2.0, "conventional": 1.0}
    class_visibility: dict[str, str] = {}
    for entry in api_surface:
        if isinstance(entry, dict) and "name" in entry:
            class_visibility[entry["name"]] = entry.get("visibility", "conventional")

    # ----- 1. Build class → sub-package map from api_surface file paths -----
    class_to_subpkg: dict[str, str] = {}
    for entry in api_surface:
        if not isinstance(entry, dict):
            continue
        cls_name = entry.get("name", "")
        file_path = entry.get("file", "")
        if not cls_name:
            continue
        # C1-SYS: Exclude classes in private implementation subtrees
        # (_internal/, _private/, _impl/) that are NOT explicitly re-exported
        # via package __init__.py.__all__ (exported_via_package_init field set
        # by scout PY-INIT-001).  This ensures implementation-private helper
        # classes (encoders, parsers, strategy objects, etc.) do not pollute
        # content clusters across all future families and platforms.
        if (any(pat in file_path for pat in _INTERNAL_PATH_PATTERNS)
                and not entry.get("exported_via_package_init")):
            continue
        class_to_subpkg[cls_name] = _class_to_subpackage(file_path)

    # ----- 2. Build sub-package → cluster label map -----
    subpkg_label: dict[str, str] = {
        sp: _subpkg_to_label(sp, family)
        for sp in set(class_to_subpkg.values())
    }

    # ----- 3. Build snippet → cluster mapping -----
    # snippet_index entries have optional 'classes_used' list
    snippet_to_clusters: dict[str, set[str]] = defaultdict(set)
    for entry in snippet_index:
        if not isinstance(entry, dict):
            continue
        snip_id = entry.get("id", "")
        for cls_name in entry.get("classes_used", []):
            sp = class_to_subpkg.get(cls_name, "")
            label = subpkg_label.get(sp, _subpkg_to_label(sp, family))
            snippet_to_clusters[snip_id].add(label)

    # ----- 4. Aggregate claims by cluster label -----
    by_cluster: dict[str, dict] = {}

    def _ensure(label: str) -> None:
        if label not in by_cluster:
            by_cluster[label] = {
                "total": 0,
                "raw_total": 0,
                "api_method": 0,
                "classes": set(),
            }

    for claim in claims:
        kind = claim.get("kind", "")
        text = claim.get("text", "")

        if kind == "api_method":
            cls_name = _extract_class_from_claim(text)
            if not cls_name or cls_name not in class_to_subpkg:
                continue
            sp = class_to_subpkg[cls_name]
            label = subpkg_label.get(sp, _subpkg_to_label(sp, family))
            _ensure(label)
            weight = _VISIBILITY_WEIGHT.get(class_visibility.get(cls_name, "conventional"), 1.0)
            by_cluster[label]["total"] += weight
            by_cluster[label]["raw_total"] += 1
            by_cluster[label]["api_method"] += 1
            by_cluster[label]["classes"].add(cls_name)

        elif kind in ("api_class", "api", "feature", "format_support", "format"):
            # Attribute to any matching class
            for cls_name in class_to_subpkg:
                if cls_name and len(cls_name) > 3 and cls_name in text:
                    sp = class_to_subpkg[cls_name]
                    label = subpkg_label.get(sp, _subpkg_to_label(sp, family))
                    _ensure(label)
                    weight = _VISIBILITY_WEIGHT.get(class_visibility.get(cls_name, "conventional"), 1.0)
                    by_cluster[label]["total"] += weight
                    by_cluster[label]["raw_total"] += 1
                    by_cluster[label]["classes"].add(cls_name)
                    break  # first match only

    # ----- 4b. Warn on orphaned claims -----
    total_in_clusters = sum(d["raw_total"] for d in by_cluster.values())
    orphaned = len(claims) - total_in_clusters
    if orphaned > 0:
        pct = orphaned / max(len(claims), 1) * 100
        logging.getLogger(__name__).warning(
            "stats-consistency: %d/%d claims (%.1f%%) not allocated to any "
            "cluster. These may be enriched claims without a matching "
            "api_surface class.",
            orphaned, len(claims), pct,
        )

    # ----- 5. Count snippets per cluster -----
    cluster_snippets: dict[str, int] = defaultdict(int)
    for snip_id, cluster_set in snippet_to_clusters.items():
        for label in cluster_set:
            cluster_snippets[label] += 1

    # ----- 6. Check limitations: a cluster is blocked only if its classes are
    # predominantly listed in limitations (>50% of classes with NotImplementedError).
    # Simple substring matching is avoided to prevent false positives from path names.
    lim_lines = limitations_text.lower().splitlines()
    # Build set of class names that appear in limitations table entries
    lim_classes: set[str] = set()
    for line in lim_lines:
        if "notimplementederror" in line or "not implemented" in line:
            # Extract class name from '| ClassName |' markdown table row
            parts_ln = [p.strip() for p in line.split("|") if p.strip()]
            if len(parts_ln) >= 1:
                lim_classes.add(parts_ln[0].lower())

    clusters = []
    for label, data in sorted(by_cluster.items(), key=lambda x: -x[1]["total"]):
        # Mark in_limitations only if >50% of this cluster's classes are limited
        cls_list = [c.lower() for c in data["classes"]]
        lim_count = sum(1 for c in cls_list if c in lim_classes)
        in_lim = bool(cls_list) and (lim_count / len(cls_list)) > 0.5
        clusters.append(
            {
                "category": label,
                "slug": slug_from_category(label),
                "claim_count": int(data["total"]),
                "raw_claim_count": data["raw_total"],
                "api_method_count": data["api_method"],
                "snippet_count": cluster_snippets.get(label, 0),
                "in_limitations": in_lim,
                "class_names": sorted(data["classes"]),
            }
        )

    return clusters


# ---------------------------------------------------------------------------
# Knowledge artifact loader (lightweight — no Knowledge class dependency)
# ---------------------------------------------------------------------------

class PlannerKnowledge:
    """Lightweight knowledge loader for site_planner (no token_ops dependency)."""

    def __init__(self, family: str, platform: str) -> None:
        self.family = family
        self.platform = platform
        merged = KNOWLEDGE_ROOT / family / platform / "merged"

        if not merged.exists():
            print(
                f"SITE-PLAN ERROR: Knowledge merged directory not found: {merged}",
                file=sys.stderr,
            )
            sys.exit(1)

        # model.yaml — required
        model_path = merged / "model.yaml"
        if not model_path.exists():
            print(
                f"SITE-PLAN ERROR: model.yaml not found at {model_path}",
                file=sys.stderr,
            )
            sys.exit(1)
        try:
            self.model = yaml.safe_load(model_path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as exc:
            print(
                f"SITE-PLAN ERROR: model.yaml is malformed: {exc}",
                file=sys.stderr,
            )
            sys.exit(1)
        self.repo_sha: str = self.model.get("repo_sha", "")
        self.stale_since = self.model.get("stale_since")
        self.version: str = str(self.model.get("version", ""))

        # index.json — required
        idx_path = merged / "index.json"
        if not idx_path.exists():
            print(
                f"SITE-PLAN ERROR: index.json not found at {idx_path}\n"
                f"  Fix: python scripts/pipeline/commands/knowledge/index.py {family} {platform}\n"
                f"  This usually means the knowledge bootstrap chain "
                f"(S-31 truth-index) did not complete.",
                file=sys.stderr,
            )
            sys.exit(1)
        self.index: dict = json.loads(idx_path.read_text(encoding="utf-8"))
        stats = self.index.get("stats", {})
        self.total_claim_count: int = stats.get("total_claims", 0)
        self.snippet_count: int = stats.get("snippet_count", 0)
        self.class_count: int = stats.get("class_count", 0)
        forbidden = self.index.get("forbidden_claims", [])
        self.forbidden_claims: list[str] = forbidden if isinstance(forbidden, list) else []
        self.api_confidence: str = self.index.get("api_confidence", "")

        # claims.json — required
        claims_path = merged / "claims.json"
        if not claims_path.exists():
            print(
                f"SITE-PLAN ERROR: claims.json not found at {claims_path}",
                file=sys.stderr,
            )
            sys.exit(1)
        self.claims: list[dict] = json.loads(claims_path.read_text(encoding="utf-8"))

        # api_surface.json — required
        api_path = merged / "api_surface.json"
        if not api_path.exists():
            print(
                f"SITE-PLAN ERROR: api_surface.json not found at {api_path}",
                file=sys.stderr,
            )
            sys.exit(1)
        self.api_surface: list[dict] = json.loads(api_path.read_text(encoding="utf-8"))

        # limitations.md — optional but used for cluster filtering
        lim_path = merged / "limitations.md"
        self.limitations_text: str = ""
        if lim_path.exists():
            self.limitations_text = lim_path.read_text(encoding="utf-8")

        # formats.json — optional
        fmt_path = merged / "formats.json"
        self.formats: dict = {}
        if fmt_path.exists():
            try:
                self.formats = json.loads(fmt_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                pass

        # snippets index — optional
        snip_idx_path = merged / "snippets" / "snippets_index.json"
        self.snippet_index: list[dict] = []
        if snip_idx_path.exists():
            try:
                self.snippet_index = json.loads(
                    snip_idx_path.read_text(encoding="utf-8")
                )
            except json.JSONDecodeError:
                pass


# ---------------------------------------------------------------------------
# Blog slug validator
# ---------------------------------------------------------------------------

_BANNED_SLUG_RE = re.compile(r"^[a-z0-9]+-key-features(?:-[a-z]|$)")


def _validate_blog_slugs(pages: list[dict]) -> None:
    """Raise ValueError if any source=derived blog post uses a banned generic slug.

    source=discovered posts are exempt — existing deployed URLs must not be broken.
    """
    for page in pages:
        if page.get("source") != "derived":
            continue
        slug = page.get("slug", "")
        if _BANNED_SLUG_RE.match(slug):
            raise ValueError(
                f"Banned generic slug (source=derived): {slug!r}\n"
                "The features post slug must be cluster-derived. "
                "Check kf_candidates in plan_blog()."
            )


# ---------------------------------------------------------------------------
# Section planners
# ---------------------------------------------------------------------------


def _family_index_entry(site: str, family: str) -> dict:
    """Return a family-level _index.md plan entry for a site section.

    Hugo branch bundles require an _index.md at each directory level for
    the section to appear in {{< docs-families >}} listings and sidebars.
    Weight is derived from data/families_order.json using (index + 1) * 10.
    """
    families_order_path = REPO_ROOT / "data" / "families_order.json"
    try:
        order = json.loads(families_order_path.read_text(encoding="utf-8"))
        weight = (order.index(family) + 1) * 10 if family in order else 100
    except (FileNotFoundError, json.JSONDecodeError):
        weight = 100
    return {
        "slug": "_family_index",
        "path": f"content/{site}/en/{family}/_index.md",
        "type": "family-home",
        "page_class": "structural",
        "layout": "wide",
        "weight": weight,
        "mandatory": True,
        "note": "Family landing page — created by platform index skill if missing",
        "source": "skill",
    }


def plan_products(family: str, platform: str, tier: str) -> list[dict]:
    """Plan products section pages."""
    pages = []
    pages.append(
        {
            "slug": "_index",
            "path": f"content/products.aspose.org/en/{family}/_index.md",
            "layout": "family",
            "weight": 1,
            "mandatory": True,
            "page_class": "structural",
            "note": "Family landing page",
        }
    )
    if tier != "placeholder":
        pages.append(
            {
                "slug": f"{platform}/_index",
                "path": f"content/products.aspose.org/en/{family}/{platform}/_index.md",
                "layout": "plugin",
                "weight": 2,
                "mandatory": True,
                "page_class": "structural",
                "note": "Platform plugin page",
            }
        )
    return pages


def plan_blog(
    family: str,
    platform: str,
    total_claims: int,
    snippet_count: int,
    clusters: list[dict],
    existing: list[dict] | None = None,
    force_replan: bool = False,
) -> tuple[list[dict], bool, list[dict]]:
    """Plan blog section pages.

    Returns (pages, justified, pages_to_retire) tuple.
    pages_to_retire is non-empty only when force_replan replaces an existing slug.
    When *existing* content is provided, adopts discovered slugs for mandatory
    posts instead of deriving new ones.
    """
    justified = total_claims >= 200 and snippet_count >= 5
    if not justified:
        return [], False, []

    existing = existing or []
    base = f"content/blog.aspose.org/{family}/{platform}"

    # --- Mandatory post 1: intro ---
    intro_derived_slug = f"introducing-{family}-foss-{platform}"
    intro_path = f"{base}/{intro_derived_slug}/index.md"
    # Check if an existing blog dir matches the intro pattern
    intro_match = None
    for ep in existing:
        s = ep["slug"]
        if "introducing" in s and family in s:
            intro_match = ep
            break
    if intro_match:
        intro_slug = intro_match["slug"]
        intro_path = intro_match["path"]
    else:
        intro_slug = intro_derived_slug

    pages: list[dict] = []
    pages.append(
        {
            "slug": intro_slug,
            "path": intro_path,
            "type": "blog-post",
            "weight": 1,
            "mandatory": True,
            "page_class": "generated",
            "blog_role": "announcement",
            "note": "Introductory announcement post",
            "source": "discovered" if intro_match else "derived",
        }
    )

    # --- Mandatory post 2: features (cluster-derived slug) ---
    # Select the primary cluster: highest claim_count, not in limitations.
    kf_candidates = [
        c for c in clusters
        if c["claim_count"] >= 5 and not c["in_limitations"]
    ]
    pages_to_retire: list[dict] = []

    if kf_candidates:
        kf_primary = kf_candidates[0]   # clusters sorted by claim_count desc
        primary_slug_val = kf_primary["slug"]
        # Avoid duplicate prefix: e.g. email-email-processing → email-processing
        if primary_slug_val.startswith(f"{family}-"):
            kf_derived_slug = f"{primary_slug_val}-{platform}"
        else:
            kf_derived_slug = f"{family}-{primary_slug_val}-{platform}"
        kf_cluster_cat = kf_primary["category"]
        kf_cluster_class_names = kf_primary.get("class_names", [])
    else:
        kf_primary = None
        kf_derived_slug = f"{family}-features-{platform}"
        kf_cluster_cat = ""
        kf_cluster_class_names = []

    kf_path = f"{base}/{kf_derived_slug}/index.md"

    # Exclude the intro post from discovery candidates to prevent false matches
    # from _match_existing_to_cluster Priority 4 keyword overlap.
    existing_excl_intro = [p for p in existing if p["slug"] != intro_slug]

    # Phase 1: cluster-aware matching.
    # Finds future posts where the cluster name is in the slug (Priority 2),
    # or posts with a matching frontmatter_cluster field (Priority 1).
    kf_match: dict | None = None
    if kf_primary:
        kf_match = _match_existing_to_cluster(
            existing_excl_intro, kf_cluster_cat, primary_slug_val,
            kf_cluster_class_names, section="blog", family=family,
        )

    # Phase 2: keyword fallback for legacy *-key-features-* posts.
    # This is NOT optional — it preserves all currently deployed products whose
    # slugs contain "key-features" but not any cluster label.
    if kf_match is None:
        for ep in existing_excl_intro:
            if "key-features" in ep["slug"] or "key-feature" in ep["slug"]:
                kf_match = ep
                break

    # Opt-in replan: if the matched slug matches the banned pattern and the post
    # was auto-generated (auto_updatable: true), drop the match and force
    # re-derivation. The old post path is added to pages_to_retire so the caller
    # can retire it. Only active when force_replan=True.
    if kf_match and force_replan:
        _slug_has_key_features = (
            _BANNED_SLUG_RE.match(kf_match["slug"])
            or "key-features" in kf_match["slug"]
            or "key-feature" in kf_match["slug"]
        )
        if _slug_has_key_features and kf_match.get("auto_updatable", True):
            pages_to_retire.append({
                "slug": kf_match["slug"],
                "path": kf_match["path"],
                "reason": f"Replaced by cluster-derived slug: {kf_derived_slug}",
            })
            kf_match = None

    if kf_match:
        kf_slug = kf_match["slug"]
        kf_path = kf_match["path"]
    else:
        kf_slug = kf_derived_slug

    kf_record: dict = {
        "slug": kf_slug,
        "path": kf_path,
        "type": "blog-post",
        "weight": 2,
        "mandatory": True,
        "page_class": "generated",
        "blog_role": "features",
        "note": "Key features overview post",
        "source": "discovered" if kf_match else "derived",
    }
    if kf_cluster_cat:
        kf_record["cluster"] = kf_cluster_cat
    pages.append(kf_record)

    # --- Optional deep-dive post(s) ---
    # Exclude the cluster already used by Post 2 to prevent topical overlap.
    _kf_cat = kf_cluster_cat  # may be "" when fallback path was taken
    eligible = [
        c
        for c in clusters
        if c["claim_count"] >= 20
        and c["snippet_count"] >= 3
        and not c["in_limitations"]
        and c["category"] != _kf_cat
    ]
    # SH-01: sliding-scale threshold for whether ANY deep-dive post exists at
    # all. Unchanged — HARDEN-A13 only scales HOW MANY once this gate passes
    # (was hard-capped at exactly 1 regardless of product size; see
    # _deep_dive_post_cap docstring).
    # Large APIs (500+ claims): always eligible
    # Medium APIs (200-499 claims): eligible if snippets and topic clusters exist
    deep_dive_eligible = (
        total_claims >= 500
        or (total_claims >= 200 and snippet_count >= 5 and len(eligible) >= 1)
    )
    if eligible and deep_dive_eligible:
        deep_dive_cap = _deep_dive_post_cap(total_claims)
        deep_dive_weight = 3
        for top in eligible[:deep_dive_cap]:
            # Mirror the features slug prefix-deduplication: ensure family identity is present.
            if top['slug'].startswith(f"{family}-"):
                dive_derived_slug = f"{top['slug']}-in-{platform}"
            else:
                dive_derived_slug = f"{family}-{top['slug']}-in-{platform}"
            dive_path = f"{base}/{dive_derived_slug}/index.md"
            # Check existing for a deep-dive match
            dive_match = _match_existing_to_cluster(
                existing, top["category"], top["slug"], top["class_names"],
                section="blog", family=family,
            )
            if dive_match:
                dive_slug = dive_match["slug"]
                dive_path = dive_match["path"]
            else:
                dive_slug = dive_derived_slug

            pages.append(
                {
                    "slug": dive_slug,
                    "path": dive_path,
                    "type": "blog-post",
                    "weight": deep_dive_weight,
                    "mandatory": False,
                    "page_class": "generated",
                    "blog_role": "deep-dive",
                    "note": f"Deep-dive post for cluster: {top['category']}",
                    "cluster": top["category"],
                    "source": "discovered" if dive_match else "derived",
                }
            )
            deep_dive_weight += 1

    # Include existing blog pages not yet matched (source: existing).
    # Exclude paths already in pages_to_retire — these were deliberately cleared
    # from the plan and must not re-enter as preserved entries.
    retired_paths = {r["path"] for r in pages_to_retire}
    matched_paths = {p["path"] for p in pages}
    for ep in existing:
        if ep["path"] not in matched_paths and ep["path"] not in retired_paths and ep["slug"] != "_index":
            # Check it's a blog post (has /index in path or ends with .md)
            pages.append({
                "slug": ep["slug"],
                "path": ep["path"],
                "type": "blog-post",
                "weight": 100,
                "mandatory": False,
                "page_class": "preserved",
                "note": "Existing blog post (not planner-derived)",
                "source": "existing",
            })

    _validate_blog_slugs(pages)
    return pages, True, pages_to_retire


def plan_docs(
    family: str,
    platform: str,
    clusters: list[dict],
    has_license: bool,
    license_path: Optional[Path],
    existing: list[dict] | None = None,
) -> list[dict]:
    """Plan docs section pages.

    When *existing* content is provided (launched products), adopts discovered
    slugs for cluster-derived topic pages instead of deriving new ones.
    """
    existing = existing or []
    base = f"content/docs.aspose.org/en/{family}/{platform}"
    pages: list[dict] = []

    # Family-level landing page — created by /new-docs-index (S-70) if missing
    pages.append(_family_index_entry("docs.aspose.org", family))

    # Root section landing page — generated by /new-docs-index skill (S-70)
    pages.append(
        {
            "slug": "_index",
            "path": f"{base}/_index.md",
            "type": "section-home",
            "page_class": "structural",
            "weight": 0,
            "mandatory": True,
            "note": "Hugo section landing page — generated by /new-docs-index skill (S-70)",
            "source": "skill",
        }
    )

    # Getting started — always (fixed slugs, no discovery needed)
    pages.append(
        {
            "slug": _page_slug(f"{base}/getting-started/_index.md", family, platform),
            "path": f"{base}/getting-started/_index.md",
            "type": "docs",
            "page_role": "toc",
            "weight": 10,
            "mandatory": True,
            "page_class": "fixed",
        }
    )
    pages.append(
        {
            "slug": _page_slug(f"{base}/getting-started/installation.md", family, platform),
            "path": f"{base}/getting-started/installation.md",
            "type": "docs",
            "page_role": "howto_article",
            "weight": 11,
            "mandatory": True,
            "page_class": "fixed",
            "note": "Installation guide",
        }
    )
    # C2-SYS: Quickstart is mandatory for every product on docs.aspose.org.
    # Every docs.aspose.org/{family}/{platform}/getting-started/quickstart page
    # provides the minimal working code example for the product.
    pages.append(
        {
            "slug": _page_slug(f"{base}/getting-started/quickstart.md", family, platform),
            "path": f"{base}/getting-started/quickstart.md",
            "type": "docs",
            "page_role": "howto_article",
            "weight": 12,
            "mandatory": True,
            "page_class": "fixed",
            "note": "Quickstart guide — first working example",
        }
    )
    if has_license and license_path:
        try:
            lic_src = license_path.relative_to(REPO_ROOT).as_posix()
        except ValueError:
            lic_src = str(license_path)
            print(
                f"WARN: license_source path is outside repo root: {lic_src}",
                file=sys.stderr,
            )
        lic_slug = _page_slug(f"{base}/getting-started/license.md", family, platform)
        pages.append(
            {
                "slug": lic_slug,
                "path": f"{base}/getting-started/license.md",
                "type": "docs",
                "page_role": "howto_article",
                "weight": 15,
                "mandatory": False,
                "page_class": "fixed",
                "note": f"License page (source: {license_path.name})",
                "license_source": lic_src,
            }
        )

    # Developer guide — always
    pages.append(
        {
            "slug": _page_slug(f"{base}/developer-guide/_index.md", family, platform),
            "path": f"{base}/developer-guide/_index.md",
            "type": "docs",
            "page_role": "toc",
            "weight": 1,
            "mandatory": True,
            "page_class": "fixed",
        }
    )
    pages.append(
        {
            "slug": _page_slug(f"{base}/developer-guide/features.md", family, platform),
            "path": f"{base}/developer-guide/features.md",
            "type": "docs",
            "page_role": "howto_article",
            "weight": 10,
            "mandatory": True,
            "page_class": "fixed",
            "note": "Features overview (mandatory, not cluster-derived)",
        }
    )

    # Cluster-derived topic pages (with existing-content discovery)
    topic_weight = 20
    matched_existing: set[str] = set()  # paths already adopted
    for cluster in clusters:
        if (
            cluster["claim_count"] >= 5
            and cluster["api_method_count"] >= 1
            and not cluster["in_limitations"]
            and cluster["category"].lower() not in KB_SKIP_CLUSTERS
        ):
            # Try to find an existing page that covers this cluster
            match = _match_existing_to_cluster(
                existing, cluster["category"], cluster["slug"],
                cluster["class_names"], section="docs", family=family,
            )
            if match and match["path"] not in matched_existing:
                # Adopt existing slug/path
                matched_existing.add(match["path"])
                pages.append(
                    {
                        "slug": match["slug"],
                        "path": match["path"],
                        "type": "docs",
                        "page_role": "howto_article",
                        "weight": topic_weight,
                        "mandatory": False,
                        "page_class": "generated",
                        "cluster": cluster["category"],
                        "claim_count": cluster["claim_count"],
                        "api_method_count": cluster["api_method_count"],
                        "source": "discovered",
                    }
                )
            else:
                # Derive new slug
                topic_slug = detect_family_slug_convention(family, cluster["category"])
                page_path = f"{base}/developer-guide/{topic_slug}.md"
                pages.append(
                    {
                        "slug": _page_slug(page_path, family, platform),
                        "path": page_path,
                        "type": "docs",
                        "page_role": "howto_article",
                        "weight": topic_weight,
                        "mandatory": False,
                        "page_class": "generated",
                        "cluster": cluster["category"],
                        "claim_count": cluster["claim_count"],
                        "api_method_count": cluster["api_method_count"],
                        "source": "derived",
                    }
                )
            topic_weight += 10

    # Include existing docs pages not matched to any cluster
    fixed_paths = {p["path"] for p in pages}
    for ep in existing:
        if ep["path"] not in fixed_paths and ep["path"] not in matched_existing:
            # Skip section indexes already handled
            if ep["slug"] in ("_index", "getting-started/_index",
                              "developer-guide/_index"):
                continue
            pages.append(
                {
                    "slug": ep["slug"],
                    "path": ep["path"],
                    "type": "docs",
                    "page_role": "howto_article",
                    "weight": 900,
                    "mandatory": False,
                    "page_class": "preserved",
                    "note": "Existing page (not planner-derived)",
                    "source": "existing",
                }
            )

    return pages


# ---------------------------------------------------------------------------
# KB slug quality validator (TC-KBS-004)
# ---------------------------------------------------------------------------

# Nouns that are meaningful only with a domain qualifier — "core", "content",
# "utilities" etc. reveal nothing about the product feature being described.
_KB_GENERIC_NOUNS = frozenset({
    "core", "content", "utilities", "util", "base", "common",
    "general", "data", "model", "helpers", "services",
})

# C4: Product-family keyword sets for compound-noun context check (TC-KBS-016).
# A compound noun (noun with hyphens) passes C4 if at least one of its
# hyphen-separated words appears in the family keyword set — confirming
# the slug identifies the product without URL path context.
_FAMILY_PRODUCT_KEYWORDS: dict[str, frozenset[str]] = {
    # Only include terms that are specific to this product family.
    # Generic terms ("annotation", "form", "text", "page", "document") are
    # intentionally excluded — they apply to many families and would cause
    # ambiguous slugs to pass C4 incorrectly.
    # TC-KBS-020 calibration (2026-06-20) — confirmed false positives removed:
    #   pdf   → added "facades"  (Aspose.PDF.Facades namespace — pdf-specific)
    #   email → added "eml", "msg", "attachment"
    #             (.eml/.msg are email-format file extensions; "attachment" is
    #             email-specific — email attachments are distinct from other APIs)
    #   words → added "doc"  (.doc is the Word binary file format — words-specific)
    "pdf":    frozenset({"pdf", "xmp", "javascript", "facades"}),
    "cells":  frozenset({"cell", "workbook", "worksheet", "xlsx", "excel",
                         "formula", "chart", "ooxml", "spreadsheet"}),
    "slides": frozenset({"slide", "presentation", "powerpoint", "pptx",
                         "shape"}),
    "words":  frozenset({"word", "docx", "paragraph", "doc"}),
    "email":  frozenset({"email", "mailbox", "mime", "smtp", "imap", "calendar",
                         "eml", "msg", "attachment"}),
    "3d":     frozenset({"3d", "scene", "mesh", "material", "animation",
                         "geometry", "node", "fbx", "gltf", "obj"}),
    "font":   frozenset({"font", "glyph", "cff", "eot", "type1", "ttf",
                         "woff", "opentype"}),
}


def _validate_kb_slugs(
    pages: list[dict],
    family: str,
    platform: str,
) -> None:
    """Raise ValueError if any source=derived KB how-to slug is defective.

    Three checks (applied only to source=derived pages):
    1. Single-token noun with no hyphens and length > 12 — likely a CamelCase
       namespace name that was not split (e.g. "javascriptextensions").
    2. Verb-noun duplication — verb appears as the start of the noun
       (e.g. "extract" → noun starts with "extract" or "extraction").
    3. Generic noun — primary noun word is in _KB_GENERIC_NOUNS.

    For source=discovered pages (existing deployed URLs), a warning is logged
    but no exception is raised — live URLs must not be broken.
    """
    # Build verb list (longest first) so compound verbs like "work-with" are
    # matched before their single-word prefixes ("work").
    _known_verbs: list[str] = sorted(
        {v for _, v in _VERB_KEYWORDS} | {"work-with"},
        key=len,
        reverse=True,
    )

    plat_suffix = KB_PLATFORM_SUFFIX.get(platform, platform)
    for page in pages:
        slug = page.get("slug", "")
        source = page.get("source", "")
        if not slug.startswith("how-to-"):
            continue
        # Strip leading "how-to-" and trailing "-{plat_suffix}"
        inner = slug[7:]
        if inner.endswith(f"-{plat_suffix}"):
            inner = inner[: -(len(plat_suffix) + 1)]
        # Find verb by matching known verb prefixes (longest first to handle
        # compound verbs like "work-with" before single-word "work").
        verb = ""
        noun = inner
        for kv in _known_verbs:
            if inner.startswith(kv + "-") and len(inner) > len(kv) + 1:
                verb = kv
                noun = inner[len(kv) + 1:]
                break
        if not noun:
            continue

        _log = logging.getLogger(__name__)

        def _fail_or_warn(msg: str) -> None:
            if source == "derived":
                raise ValueError(msg)
            _log.warning("KB slug quality warning (source=%s): %s", source, msg)

        # Check 1: single-token noun (no hyphens, length > 12) — CamelCase leak
        if "-" not in noun and len(noun) > 12:
            _fail_or_warn(
                f"KB slug noun appears to be an unsplit CamelCase token: {slug!r}\n"
                f"  noun={noun!r} — add label to "
                f"_FAMILY_SUBPKG_LABELS[{family!r}] or rely on TC-KBS-002 splitter"
            )
            continue

        # Check 2: verb-noun duplication — verb appears at the start OR end of
        # the noun, including nominal forms (e.g. "extract" matches "extraction").
        verb_forms = [verb] + [verb + s for s in ("ion", "ing", "tion", "ation")]
        noun_parts = noun.split("-")
        if (any(noun.startswith(f) for f in verb_forms)
                or any(noun.endswith("-" + f) for f in verb_forms)
                or any(part in verb_forms for part in noun_parts)):
            _fail_or_warn(
                f"KB slug has verb-noun duplication: {slug!r}\n"
                f"  verb={verb!r} appears in noun={noun!r}"
            )
            continue

        # Check 3: generic noun (primary word only)
        primary = noun.split("-")[0]
        if primary in _KB_GENERIC_NOUNS:
            _fail_or_warn(
                f"KB slug noun is too generic: {slug!r}\n"
                f"  primary noun word {primary!r} is in _KB_GENERIC_NOUNS — "
                f"add a specific label to _FAMILY_SUBPKG_LABELS[{family!r}]"
            )
            continue

        # Check 4 (C4): compound noun without product-family keyword (TC-KBS-016).
        # A hyphenated noun that contains no family-specific keyword is
        # context-dependent — its meaning changes with the URL path prefix.
        # Prefix matching handles plurals: "materials" matches keyword "material".
        # Only enforced for source=derived; warn for source=discovered.
        if "-" in noun:
            family_keywords = _FAMILY_PRODUCT_KEYWORDS.get(family, frozenset())
            noun_words = noun.split("-")
            if family_keywords and not any(
                word.startswith(kw) for word in noun_words for kw in family_keywords
            ):
                _fail_or_warn(
                    f"KB slug compound noun lacks product-family qualifier: {slug!r}\n"
                    f"  noun={noun!r} contains no word from the {family!r} "
                    f"keyword set — slug is ambiguous without URL context.\n"
                    f"  Prefix noun with family term (e.g. '{family}-{noun}') "
                    f"or update label in _FAMILY_SUBPKG_LABELS[{family!r}]"
                )


def _kb_howto_cap(total_claims: int) -> int:
    """HARDEN-A13: how many eligible clusters get a KB how-to page.

    Was a hard `eligible[:7]` slice regardless of product size — empirically
    proven flat by a dedicated audit: pdf/net (5.85x the classes, 8.9x the
    claims of words/python) got only 1.08x the KB pages, vs. 2.1x for docs
    (whose cluster loop is genuinely uncapped) and 5.9x for reference (1:1
    with the API surface via batch_reference.py). Mirrors the existing
    `min_faq_items` step-scaling idiom in this same function. The floor (7)
    is unchanged from today's behavior for every product under 300 claims —
    zero regression risk for any currently-shipped small/medium product.
    """
    if total_claims >= 1000:
        return 20
    if total_claims >= 500:
        return 12
    if total_claims >= 300:
        return 9
    return 7


def _deep_dive_post_cap(total_claims: int) -> int:
    """HARDEN-A13: how many optional deep-dive blog posts a product's size
    justifies, once SH-01's `deep_dive_eligible` gate (unchanged) says at
    least one is warranted. Was hard-capped at exactly 1 post ever
    (`top = eligible[0]`), regardless of how many eligible clusters remained
    — the same flat-regardless-of-size shape as the KB cap above. The floor
    (1) is unchanged for every product under 1000 claims.
    """
    if total_claims >= 2000:
        return 3
    if total_claims >= 1000:
        return 2
    return 1


def plan_kb(
    family: str,
    platform: str,
    clusters: list[dict],
    total_claims: int,
    snippet_count: int,
    tier: str,
    existing: list[dict] | None = None,
) -> list[dict]:
    """Plan KB section pages.

    When *existing* content is provided (launched products), adopts discovered
    slugs for how-to pages instead of deriving new ones.
    """
    existing = existing or []
    base = f"content/kb.aspose.org/en/{family}/{platform}"
    plat_suffix = KB_PLATFORM_SUFFIX.get(platform, platform)
    pages: list[dict] = []

    # Family-level landing page — created by /new-kb-index (S-69) if missing
    pages.append(_family_index_entry("kb.aspose.org", family))

    # Root section landing page — generated by /new-kb-index skill (S-69)
    pages.append(
        {
            "slug": "_index",
            "path": f"{base}/_index.md",
            "type": "section-home",
            "page_class": "structural",
            "weight": 0,
            "mandatory": True,
            "note": "Hugo section landing page — generated by /new-kb-index skill (S-69)",
            "source": "skill",
        }
    )

    # FAQ — always; min_faq_items scales with knowledge volume (SH-06)
    # More claims → more FAQ items (200-499: 5, 500-999: 6, 1000+: 8)
    _min_faq = 5
    if total_claims >= 1000:
        _min_faq = 8
    elif total_claims >= 500:
        _min_faq = 7
    elif total_claims >= 300:
        _min_faq = 6
    pages.append(
        {
            "slug": "faq",
            "path": f"{base}/faq.md",
            "type": "topic",
            "weight": 1,
            "mandatory": True,
            "page_class": "fixed",
            "note": "Frequently asked questions",
            "min_faq_items": _min_faq,
        }
    )

    # How-to pages — up to _kb_howto_cap(total_claims) eligible clusters
    # (reference-only clusters excluded). HARDEN-A13: cap scales with product
    # size (was a flat 7 regardless of size — see _kb_howto_cap docstring).
    eligible = [
        c
        for c in clusters
        if c["claim_count"] >= 3
        and c["api_method_count"] >= 1
        and not c["in_limitations"]
        and c["category"].lower() not in KB_SKIP_CLUSTERS
    ]
    howto_cap = _kb_howto_cap(total_claims)
    howto_weight = 10
    howto_count = 0
    matched_existing: set[str] = set()
    for cluster in eligible[:howto_cap]:
        # Try to find an existing KB page for this cluster
        match = _match_existing_to_cluster(
            existing, cluster["category"], cluster["slug"],
            cluster["class_names"], section="kb", family=family,
        )
        if match and match["path"] not in matched_existing:
            matched_existing.add(match["path"])
            pages.append(
                {
                    "slug": match["slug"],
                    "path": match["path"],
                    "type": "topic",
                    "weight": howto_weight,
                    "mandatory": False,
                    "page_class": "generated",
                    "cluster": cluster["category"],
                    "verb": detect_kb_verb(cluster["category"]),
                    "claim_count": cluster["claim_count"],
                    "api_method_count": cluster["api_method_count"],
                    "source": "discovered",
                }
            )
        else:
            # Derive new slug
            verb = detect_kb_verb(cluster["category"])
            noun = _kb_noun_from_cluster(cluster["category"], family, verb=verb)
            howto_path = f"{base}/how-to-{verb}-{noun}-{plat_suffix}.md"
            pages.append(
                {
                    "slug": _page_slug(howto_path, family, platform),
                    "path": howto_path,
                    "type": "topic",
                    "weight": howto_weight,
                    "mandatory": False,
                    "page_class": "generated",
                    "cluster": cluster["category"],
                    "verb": verb,
                    "claim_count": cluster["claim_count"],
                    "api_method_count": cluster["api_method_count"],
                    "source": "derived",
                }
            )
        howto_weight += 10
        howto_count += 1

    # TC-KBS-004: validate derived KB how-to slugs — raises ValueError on bad slugs
    _validate_kb_slugs(pages, family, platform)

    # Troubleshooting — conditional (derived only when threshold met)
    trouble_derived = False
    # SH-02: lowered from 6 to 3 — any product with 3+ how-tos has enough
    # surface area for a troubleshooting page
    if howto_count >= 3 and platform in TROUBLE_PLATFORMS:
        trouble_derived = True
        pages.append(
            {
                "slug": "troubleshooting",
                "path": f"{base}/troubleshooting.md",
                "type": "topic",
                "weight": 2,
                "mandatory": False,
                "page_class": "generated",
                "note": "Troubleshooting guide",
            }
        )

    # Use cases — conditional
    # SH-03: lowered from 500/8 — small-API products with 200+ claims
    # and 3+ snippets have enough material for a use-cases overview
    if total_claims >= 200 and snippet_count >= 3:
        pages.append(
            {
                "slug": "use-cases",
                "path": f"{base}/use-cases.md",
                "type": "topic",
                "weight": 10,
                "mandatory": False,
                "page_class": "fixed",
                "note": "Use-cases overview",
            }
        )

    # Include existing KB pages not matched to any cluster
    fixed_paths = {p["path"] for p in pages}
    for ep in existing:
        if (ep["path"] not in fixed_paths
                and ep["path"] not in matched_existing
                and ep["slug"] not in ("_index", "faq", "use-cases")):
            # Troubleshooting: if it exists on disk but wasn't derived above,
            # include as preserved content (not generated, not deletable)
            if ep["slug"] == "troubleshooting" and not trouble_derived:
                pages.append(
                    {
                        "slug": ep["slug"],
                        "path": ep["path"],
                        "type": "topic",
                        "weight": 2,
                        "mandatory": False,
                        "page_class": "preserved",
                        "note": "Preserved KB entry — outside cluster generation threshold",
                        "source": "existing",
                    }
                )
            elif ep["slug"] == "troubleshooting":
                # Already derived above — skip duplicate
                continue
            else:
                pages.append(
                    {
                        "slug": ep["slug"],
                        "path": ep["path"],
                        "type": "topic",
                        "weight": 900,
                        "mandatory": False,
                        "page_class": "preserved",
                        "note": "Existing page (not planner-derived)",
                        "source": "existing",
                    }
                )

    return pages


def plan_reference(
    family: str,
    platform: str,
    api_surface: list[dict],
) -> list[dict]:
    """Plan reference section pages."""
    base = f"content/reference.aspose.org/en/{family}/{platform}"
    pages: list[dict] = []

    # Family-level landing page — created by /new-reference-index (S-71) if missing
    pages.append(_family_index_entry("reference.aspose.org", family))

    pages.append(
        {
            "slug": "_index",
            "path": f"{base}/_index.md",
            "layout": "reference-home",
            "weight": 1,
            "mandatory": True,
            "page_class": "structural",
            "note": "Reference home — generated by /new-reference-index skill (S-71)",
            "source": "skill",
            "candidate_class_count": len(api_surface),
            "grouped_index_required": len(api_surface) >= 5,
        }
    )
    return pages


# ---------------------------------------------------------------------------
# Plan builder
# ---------------------------------------------------------------------------

def build_plan(
    family: str,
    platform: str,
    mode: str,
    section: Optional[str],
    existing_plan: Optional[dict],
    force_replan: bool = False,
) -> dict:
    """Build the full site plan dict."""
    kn = PlannerKnowledge(family, platform)

    # Staleness gate
    if kn.stale_since is not None:
        print(
            f"SITE-PLAN STOP: Knowledge is stale since {kn.stale_since}.",
            file=sys.stderr,
        )
        sys.exit(1)

    # Cluster detection
    clusters = detect_clusters(
        kn.claims,
        kn.api_surface,
        kn.snippet_index,
        kn.limitations_text,
        family=family,
    )
    # Orphaned claim count for evidence_summary. Must sum raw_claim_count
    # (unweighted), not claim_count (visibility-weighted up to 3x per claim,
    # see _VISIBILITY_WEIGHT in detect_clusters) — comparing a weighted sum
    # against len(kn.claims) (an unweighted raw count) produced nonsensical
    # negative values (confirmed live for both words/net and words/python).
    _claims_in_clusters = sum(c["raw_claim_count"] for c in clusters)
    orphaned_claim_count = len(kn.claims) - _claims_in_clusters

    # Launch tier
    tier = detect_launch_tier(family, platform)

    # Clone cache — for license detection
    clone_cache_env = os.environ.get("CLONE_CACHE_DIR")
    if clone_cache_env:
        clone_cache_dir = Path(clone_cache_env)
    else:
        clone_cache_dir = REPO_ROOT / "runs" / ".clone_cache" / f"aspose_{family}_{platform}"
    license_file = find_license_file(clone_cache_dir)
    has_license = license_file is not None

    # Build sections
    sections_to_build = (
        [section] if section else ["products", "blog", "docs", "kb", "reference"]
    )

    # Discover existing content for launched products (tier != placeholder)
    existing_content: dict[str, list[dict]] = {}
    if tier != "placeholder":
        existing_content = discover_existing_content(family, platform)

    products_pages: list[dict] = []
    blog_pages: list[dict] = []
    blog_justified = False
    docs_pages: list[dict] = []
    kb_pages: list[dict] = []
    reference_pages: list[dict] = []

    if "products" in sections_to_build:
        products_pages = plan_products(family, platform, tier)

    blog_to_retire: list[dict] = []
    if "blog" in sections_to_build:
        blog_pages, blog_justified, blog_to_retire = plan_blog(
            family,
            platform,
            kn.total_claim_count,
            kn.snippet_count,
            clusters,
            existing=existing_content.get("blog"),
            force_replan=force_replan,
        )

    if "docs" in sections_to_build:
        docs_pages = plan_docs(
            family,
            platform,
            clusters,
            has_license,
            license_file,
            existing=existing_content.get("docs"),
        )

    if "kb" in sections_to_build:
        kb_pages = plan_kb(
            family,
            platform,
            clusters,
            kn.total_claim_count,
            kn.snippet_count,
            tier,
            existing=existing_content.get("kb"),
        )

    if "reference" in sections_to_build:
        reference_pages = plan_reference(family, platform, kn.api_surface)

    # Excluded topics count (clusters that failed threshold for docs or kb)
    excluded_topics = sum(
        1
        for c in clusters
        if (
            c["claim_count"] < 5
            or c["api_method_count"] < 1
            or c["in_limitations"]
        )
    )

    # Plan version / delta for update mode
    plan_version = 1
    pages_to_add: list[str] = []
    pages_to_update: list[str] = []
    pages_to_remove: list[str] = []
    pages_renamed: list[dict] = []

    if mode == "update" and existing_plan:
        # Support both wrapped {"plan": {...}} and flat legacy format
        _ep = existing_plan.get("plan", existing_plan)
        plan_version = (_ep.get("plan_version") or 1) + 1

        # Build cluster→path maps from old and new plans for rename detection
        old_cluster_to_path: dict[str, str] = {}
        existing_paths = set()
        for sec in ("products", "blog", "docs", "kb", "reference"):
            for p in _ep.get("sections", {}).get(sec, {}).get("pages", []):
                path = p.get("path", "")
                existing_paths.add(path)
                cluster = p.get("cluster", "")
                if cluster:
                    old_cluster_to_path[cluster] = path

        new_cluster_to_path: dict[str, str] = {}
        new_paths = set()
        for page_list in [products_pages, blog_pages, docs_pages, kb_pages, reference_pages]:
            for p in page_list:
                path = p.get("path", "")
                new_paths.add(path)
                cluster = p.get("cluster", "")
                if cluster:
                    new_cluster_to_path[cluster] = path

        # Detect renames: same cluster, different path
        renamed_old_paths: set[str] = set()
        renamed_new_paths: set[str] = set()
        for cluster, old_path in old_cluster_to_path.items():
            new_path = new_cluster_to_path.get(cluster)
            if new_path and new_path != old_path:
                pages_renamed.append({
                    "old_path": old_path,
                    "new_path": new_path,
                    "cluster": cluster,
                })
                renamed_old_paths.add(old_path)
                renamed_new_paths.add(new_path)

        # Collect paths of protected pages (structural/preserved) from old plan
        protected_old_paths: set[str] = set()
        for sec in ("products", "blog", "docs", "kb", "reference"):
            for p in _ep.get("sections", {}).get(sec, {}).get("pages", []):
                if p.get("page_class") in ("structural", "preserved"):
                    protected_old_paths.add(p.get("path", ""))

        # Exclude renamed pages from add/remove to avoid false deltas
        pages_to_add = sorted((new_paths - existing_paths) - renamed_new_paths)
        pages_to_remove = sorted(
            (existing_paths - new_paths) - renamed_old_paths - protected_old_paths
        )

        # pages_to_update: existing pages whose cluster/claim stats changed
        # (simplified: mark all retained pages as updated when repo_sha changed)
        old_sha = _ep.get("repo_sha", "")
        if old_sha and old_sha != kn.repo_sha:
            pages_to_update = sorted(new_paths & existing_paths)

        if pages_renamed and tier == "full":
            print(
                f"WARN: Plan would rename {len(pages_renamed)} existing content "
                f"file(s). Review required before applying.",
                file=sys.stderr,
            )

    now_iso = datetime.now(timezone.utc).isoformat()

    # Compute page_class_summary across all sections
    all_pages = products_pages + blog_pages + docs_pages + kb_pages + reference_pages
    _class_counts: dict[str, int] = {}
    for _p in all_pages:
        _cls = _p.get("page_class", "generated")
        _class_counts[_cls] = _class_counts.get(_cls, 0) + 1

    plan: dict = {
        "schema_version": 1,
        "plan_version": plan_version,
        "family": family,
        "platform": platform,
        "generated_at": now_iso,
        "repo_sha": kn.repo_sha,
        "knowledge_version": kn.version,
        "launch_tier": tier,
        "evidence_summary": {
            "total_claim_count": kn.total_claim_count,
            "snippet_count": kn.snippet_count,
            "class_count": kn.class_count,
            "api_confidence": kn.api_confidence,
            "cluster_count": len(clusters),
            "orphaned_claim_count": orphaned_claim_count,
            "excluded_topics": excluded_topics,
            "blog_justified": blog_justified,
        },
        "page_class_summary": {
            "generated": _class_counts.get("generated", 0),
            "fixed": _class_counts.get("fixed", 0),
            "structural": _class_counts.get("structural", 0),
            "preserved": _class_counts.get("preserved", 0),
        },
        "sections": {
            "products": {
                "page_count": len(products_pages),
                "pages": products_pages,
            },
            "blog": {
                "page_count": len(blog_pages),
                "justified": blog_justified,
                "pages": blog_pages,
                **({"pages_to_retire": blog_to_retire} if blog_to_retire else {}),
            },
            "docs": {
                "page_count": len(docs_pages),
                "pages": docs_pages,
            },
            "kb": {
                "page_count": len(kb_pages),
                "pages": kb_pages,
            },
            "reference": {
                "page_count": len(reference_pages),
                "class_count": len(kn.api_surface),
                "pages": reference_pages,
            },
        },
    }

    if mode == "update":
        plan["delta"] = {
            "pages_to_add": pages_to_add,
            "pages_to_update": pages_to_update,
            "pages_to_remove": pages_to_remove,
            "pages_renamed": pages_renamed,
        }

    return plan, clusters, excluded_topics


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------

def print_summary(
    family: str,
    platform: str,
    plan: dict,
    clusters: list[dict],
    excluded_topics: int,
    output_path: Optional[Path],
    dry_run: bool,
) -> None:
    """Print the post-write summary."""
    tier = plan.get("launch_tier", "unknown")
    mode_label = "launch" if plan.get("plan_version", 1) == 1 else "update"
    secs = plan.get("sections", {})

    ref_class_count = secs.get("reference", {}).get("class_count", 0)
    blog_justified = secs.get("blog", {}).get("justified", False)
    blog_note = " (justified)" if blog_justified else " (below threshold)"

    print(f"\nSITE-PLAN: {family}/{platform} [{mode_label}]", file=sys.stderr)
    print(f"  launch_tier: {tier}", file=sys.stderr)
    print(f"  products: {secs.get('products', {}).get('page_count', 0)} pages", file=sys.stderr)
    print(
        f"  blog: {secs.get('blog', {}).get('page_count', 0)} pages{blog_note}",
        file=sys.stderr,
    )
    print(f"  docs: {secs.get('docs', {}).get('page_count', 0)} pages", file=sys.stderr)
    print(f"  kb: {secs.get('kb', {}).get('page_count', 0)} pages", file=sys.stderr)
    print(
        f"  reference: {ref_class_count} classes"
        f" + {secs.get('reference', {}).get('page_count', 0)} home",
        file=sys.stderr,
    )
    print(
        f"  excluded_topics: {excluded_topics}"
        f" (below threshold or in limitations.md)",
        file=sys.stderr,
    )
    if dry_run:
        print(f"  output: <dry-run — stdout only>", file=sys.stderr)
    else:
        print(f"  output: {output_path}", file=sys.stderr)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate a deterministic site manifest (site_plan.yaml) for a product.",
    )
    parser.add_argument("family", help="Product family (e.g. 3d, cells, slides)")
    parser.add_argument("platform", help="Platform (e.g. python, java, net, cpp, typescript)")
    parser.add_argument(
        "--mode",
        choices=["launch", "update", "section"],
        default="launch",
        help="Planning mode: launch (new plan), update (diff), section (single section)",
    )
    parser.add_argument(
        "--section",
        choices=["products", "docs", "blog", "kb", "reference"],
        default=None,
        help="Section to plan (only used with --mode section)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Print plan YAML to stdout instead of writing to file",
    )
    parser.add_argument(
        "--detect-clusters",
        action="store_true",
        default=False,
        help="Print cluster JSON list to stdout and exit",
    )
    parser.add_argument(
        "--replan-blog",
        action="store_true",
        default=False,
        help=(
            "Override discovered features blog slug if it matches the banned "
            "*-key-features-* pattern and was auto-generated (auto_updatable: true). "
            "Adds the old post to pages_to_retire. Never used automatically by "
            "launch-product or refresh-product."
        ),
    )
    args = parser.parse_args()

    family = args.family
    platform = args.platform
    _validate_arg("family", family)
    _validate_arg("platform", platform)
    mode = args.mode
    section = args.section if mode == "section" else None

    # If --detect-clusters: load knowledge, run detection, print JSON, exit
    if args.detect_clusters:
        kn = PlannerKnowledge(family, platform)
        if kn.stale_since is not None:
            print(
                f"SITE-PLAN STOP: Knowledge is stale since {kn.stale_since}.",
                file=sys.stderr,
            )
            sys.exit(1)
        clusters = detect_clusters(
            kn.claims,
            kn.api_surface,
            kn.snippet_index,
            kn.limitations_text,
            family=family,
        )
        print(json.dumps(clusters, indent=2, ensure_ascii=False))
        return

    # Resolve output path
    output_dir = REPORTS_ROOT / family / platform
    output_path = output_dir / "site_plan.yaml"

    # Load existing plan if update mode
    existing_plan: Optional[dict] = None
    if mode == "update" and output_path.exists():
        try:
            existing_plan = yaml.safe_load(output_path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError:
            existing_plan = None

    # Check if update mode has a change to process
    if mode == "update" and existing_plan:
        # Quick SHA comparison before full build
        kn_model_path = KNOWLEDGE_ROOT / family / platform / "merged" / "model.yaml"
        if kn_model_path.exists():
            kn_model = yaml.safe_load(kn_model_path.read_text(encoding="utf-8")) or {}
            current_sha = kn_model.get("repo_sha", "")
            # Support both wrapped {"plan": {...}} and flat legacy format
            _ep = existing_plan.get("plan", existing_plan)
            stored_sha = _ep.get("repo_sha", "")
            if current_sha and stored_sha and current_sha == stored_sha:
                print(
                    "SITE-PLAN: No repo change detected. Plan is current.",
                    file=sys.stderr,
                )
                # TC-PROD-010A: Feature-flag-gated per-surface decision engine.
                # refresh_reconciliation_enforced=false (default) → advisory mode:
                #   SHA gate preserved exactly as before; sys.exit(0) fires.
                # refresh_reconciliation_enforced=true → enforced mode:
                #   sys.exit(0) bypassed; per-surface decisions govern.
                _flags = _load_refresh_flags()
                if not _flags.get("refresh_reconciliation_enforced", False):
                    sys.exit(0)
                # Enforced mode: SHA match is an optimization hint only.
                # Execution continues; per-surface decisions are computed below.
                print(
                    "SITE-PLAN: refresh_reconciliation_enforced=true — "
                    "SHA gate bypassed; per-surface decision engine governs.",
                    file=sys.stderr,
                )

    # Build plan
    plan, clusters, excluded_topics = build_plan(
        family, platform, mode, section, existing_plan,
        force_replan=args.replan_blog,
    )

    # Surface enrichment degradation in the plan (TC-4).
    _enrich_status = Knowledge(family, platform, knowledge_root=str(KNOWLEDGE_ROOT)).enrichment_status or "full"
    if _enrich_status != "full":
        plan["enrichment_warning"] = (
            f"knowledge enrichment incomplete: {_enrich_status} — "
            "claim-based coverage may be shallow"
        )
        print(
            f"SITE-PLAN: WARNING enrichment_status={_enrich_status!r} for"
            f" {family}/{platform}",
            file=sys.stderr,
        )

    # Wrap in {"plan": ...} per spec schema, then serialize
    plan_wrapped = {"plan": plan}
    plan_yaml = yaml.dump(
        plan_wrapped,
        default_flow_style=False,
        allow_unicode=True,
        sort_keys=False,
    )

    if args.dry_run:
        sys.stdout.write(plan_yaml)
        print_summary(
            family, platform, plan, clusters, excluded_topics,
            output_path=None, dry_run=True,
        )
        return

    # Write to file (atomic: tmp + os.replace avoids partial-write corruption)
    output_dir.mkdir(parents=True, exist_ok=True)
    atomic_write(output_path, plan_yaml)

    print_summary(
        family, platform, plan, clusters, excluded_topics,
        output_path=output_path, dry_run=False,
    )


if __name__ == "__main__":
    main()