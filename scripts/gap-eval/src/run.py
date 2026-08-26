#!/usr/bin/env python3
"""S-43 gap-eval runner — three-tier content verification against clone cache.

Usage:
    python scripts/gap-eval/src/run.py {family} {platform} [options]

Options:
    --scope         all | products | docs | blog | kb | reference  (default: all)
    --out           Override JSON output path
    --state-dir     Override state directory
    --no-llm        Skip Tier 3 LLM verification (flag ambiguous as NEEDS_REVIEW)
    --dry-run       Run all stages but do not write output files
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import logging
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Optional

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

_DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[3]
_REPO_ROOT = _DEFAULT_REPO_ROOT
_SCRIPTS_DIR = _REPO_ROOT / "scripts"
_GAP_EVAL_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_SCRIPTS_DIR))
sys.path.insert(0, str(_GAP_EVAL_DIR))  # so `from state import` resolves state.py in this dir
sys.path.insert(0, str(_SCRIPTS_DIR / "pipeline"))

from core.env_loader import load_env  # noqa: E402
from lib.llm_router import EndpointStatus  # noqa: E402
load_env()


def configure(*, repo_root: "Path | str | None" = None) -> None:
    """Override module-level path constants for testing."""
    global _REPO_ROOT
    _REPO_ROOT = Path(repo_root) if repo_root is not None else _DEFAULT_REPO_ROOT

# ---------------------------------------------------------------------------
# Path resolution helpers
# ---------------------------------------------------------------------------

def _clone_cache_base() -> Path:
    """Resolve internal clone cache root (runs/.clone_cache/ inside this repo)."""
    sys.path.insert(0, str(_REPO_ROOT / "scripts" / "pipeline"))
    from core.clone_cache import cache_root  # noqa: PLC0415
    return cache_root()


def _clone_cache_path(family: str, platform: str) -> Path:
    return _clone_cache_base() / f"aspose_{family}_{platform}"


def _profile_path(family: str, platform: str) -> Path:
    return _REPO_ROOT / "scripts" / "gap-eval" / "profiles" / family / f"{platform}.yaml"


def _api_surface_path(family: str, platform: str) -> Path:
    return _REPO_ROOT / "knowledge" / family / platform / "merged" / "api_surface.json"


def _output_paths(family: str, platform: str, out_override: str | None) -> tuple[Path, Path]:
    """Return (markdown_path, json_path)."""
    base = _REPO_ROOT / "reports" / "gap-analysis"
    stem = f"{family}-{platform}"
    if out_override:
        p = Path(out_override)
        return p.with_suffix(".md"), p.with_suffix(".json")
    return base / f"{stem}.md", base / f"{stem}.json"


# ---------------------------------------------------------------------------
# Profile loader (minimal YAML parser — avoids PyYAML dependency)
# ---------------------------------------------------------------------------

def _load_profile(family: str, platform: str) -> dict:
    path = _profile_path(family, platform)
    if not path.exists():
        log.warning("Profile not found at %s — using minimal defaults", path)
        return {
            "family": family,
            "platform": platform,
            "discovery_hints": {},
            "discovered_actuals": {},
            "language_conventions": {},
            "expected_sections": [],
        }
    try:
        import yaml  # type: ignore
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except ImportError:
        # Fallback: very minimal YAML key:value parser (no nested structures)
        log.debug("PyYAML not available — using minimal profile parser")
        return _parse_minimal_yaml(path)


def _missing_profile_finding(family: str, platform: str) -> dict:
    """Build a blocking-severity finding for a missing profile.

    RC-tex-python-04 / Phase A (MT037-2026-08-24-FOSS-PORTFOLIO-FORENSIC-HEAL
    blind-spot audit): a missing profile used to silently fall back to
    "minimal defaults" with only a log-level warning -- the run could still
    report a clean-sounding PUBLICATION READY verdict even though most Tier 1
    checks (package-name detection, wrong-package/format-completeness
    scoping) are degraded or skipped in this mode. Emitting a real,
    "S"-severity finding here (rather than just logging) makes the degraded
    state visible in the report and caps compute_verdict() at CONDITIONAL
    instead of being silently indistinguishable from a real PUBLICATION
    READY result.
    """
    from state import make_finding_id  # type: ignore  # local import matches run()'s own pattern

    profile_path = _profile_path(family, platform)
    return {
        "id": make_finding_id(family, platform, "missing-profile-degraded-mode",
                               str(profile_path), 0, ""),
        "type": "missing-profile-degraded-mode",
        "severity": "S",
        "tier_resolved_by": 1,
        "file": f"knowledge/{family}/{platform}",
        "description": (
            f"No profile found at {profile_path} -- this run used minimal defaults. "
            "Package-name detection, wrong-package scoping, and format-completeness "
            "checks are degraded or skipped in this mode. Author a real profile before "
            "trusting this run's verdict."
        ),
        "status": "open",
    }


def _parse_minimal_yaml(path: Path) -> dict:
    """Parse top-level scalar keys only. Sufficient for reading package names."""
    result: dict = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" in line:
            key, _, val = line.partition(":")
            val = val.strip().strip('"').strip("'")
            if val:
                result[key.strip()] = val
    return result


# ---------------------------------------------------------------------------
# Site plan loader (page-level gap detection)
# ---------------------------------------------------------------------------

def load_site_plan(family: str, platform: str, repo_root: Path) -> Optional[dict]:
    """Load site_plan.yaml if it exists. Returns None if not found."""
    plan_path = repo_root / "reports" / "plans" / family / platform / "site_plan.yaml"
    if not plan_path.exists():
        return None
    try:
        import yaml  # type: ignore
        with open(plan_path, encoding="utf-8") as f:
            return yaml.safe_load(f)
    except ImportError:
        log.warning("PyYAML not available — cannot load site_plan.yaml, falling back to profile")
        return None
    except Exception as exc:
        log.warning("Failed to load site_plan.yaml at %s: %s", plan_path, exc)
        return None


def expected_pages_from_plan(site_plan: dict) -> dict:
    """Extract expected page paths from site_plan.yaml.

    Returns: {site_key: [path_str, ...], ...}
    where site_key is one of: 'products', 'docs', 'kb', 'blog', 'reference'

    Only pages with mandatory=True (or pages without a 'condition' field) are
    included as required.  Optional pages (mandatory=False) are included with
    a lower severity signal; callers distinguish by checking the original plan.

    Supports both spec-compliant wrapped format {"plan": {..., "sections": ...}}
    and legacy flat format {"sections": ...}.
    """
    root = site_plan.get("plan", site_plan)  # backward-compat: flat or wrapped
    sections = root.get("sections") or {}
    result: dict[str, list[str]] = {}
    for site_key, section_data in sections.items():
        if not isinstance(section_data, dict):
            continue
        pages = section_data.get("pages") or []
        paths: list[str] = []
        for page in pages:
            if not isinstance(page, dict):
                continue
            path = page.get("path")
            if not path:
                continue
            paths.append(path)
        if paths:
            result[site_key] = paths
    return result


# ---------------------------------------------------------------------------
# API surface loader
# ---------------------------------------------------------------------------

def _load_api_surface(family: str, platform: str) -> list[dict]:
    path = _api_surface_path(family, platform)
    if not path.exists():
        raise FileNotFoundError(
            f"PRECONDITION FAILED: api_surface.json not found at {path}. "
            f"Run /knowledge-bootstrap {family} {platform} first."
        )
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return data
    return data.get("classes", data.get("entries", []))


def _build_api_name_set(api_data: list[dict]) -> set[str]:
    """Flat set of class and member names across current and legacy schemas."""
    names: set[str] = set()
    for cls in api_data:
        cname = cls.get("name", "")
        if cname:
            names.add(cname)
        # Generated API surfaces use ``methods``/``properties`` today, while
        # older products retain ``method_details``/``property_details``.
        # Consume both; the set makes mixed-schema records idempotent.
        for field in ("method_details", "methods"):
            for member in cls.get(field, []) or []:
                mname = member.get("name", "") if isinstance(member, dict) else str(member)
                if mname:
                    names.add(f"{cname}.{mname}")
                    names.add(mname)
        for field in ("property_details", "properties"):
            for member in cls.get(field, []) or []:
                pname = member.get("name", "") if isinstance(member, dict) else str(member)
                if pname:
                    names.add(f"{cname}.{pname}")
                    names.add(pname)
    return names


# ---------------------------------------------------------------------------
# Content file discovery
# ---------------------------------------------------------------------------

SITE_GLOBS: dict[str, list[str]] = {
    "products": [
        # Platform-specific pages (e.g. en/cells/net/_index.md and subdirs)
        "content/products.aspose.org/en/{family}/{platform}/**/*.md",
        # Family overview page — shared across platforms, verified per-platform eval
        "content/products.aspose.org/en/{family}/_index.md",
    ],
    "docs": ["content/docs.aspose.org/en/{family}/{platform}/**/*.md"],
    "blog": ["content/blog.aspose.org/{family}/{platform}/**/*.md"],
    "kb": ["content/kb.aspose.org/en/{family}/{platform}/**/*.md"],
    "reference": ["content/reference.aspose.org/en/{family}/{platform}/**/*.md"],
}

# Locale blog filter — blog uses in-file locale suffixes (index.XX.md) rather
# than directory-based locales.  Locale translations inherit English verification.
_RE_LOCALE_SUFFIX = re.compile(r'^index\.[a-z]{2}\.md$')


def _is_locale_file(path: Path) -> bool:
    """True if path is a non-English locale translation (blog index.XX.md)."""
    name = path.name
    return bool(_RE_LOCALE_SUFFIX.match(name)) and name != "index.en.md"


def discover_content_files(family: str, platform: str, scope: str = "all") -> dict[str, list[Path]]:
    """Return {site: [paths]} for all matching content files."""
    sites = list(SITE_GLOBS.keys()) if scope == "all" else [scope]
    result: dict[str, list[Path]] = {}
    for site in sites:
        paths: list[Path] = []
        for pattern in SITE_GLOBS.get(site, []):
            resolved = pattern.format(family=family, platform=platform)
            if "**" in resolved:
                paths.extend(sorted(_REPO_ROOT.glob(resolved)))
            elif "*" in resolved or "?" in resolved:
                # Single-wildcard glob: expand via parent rglob (legacy path, not used by current SITE_GLOBS)
                paths.extend(sorted((_REPO_ROOT / resolved).parent.rglob("*.md")))
            else:
                # No wildcards: direct file path — include only if the file exists
                direct = _REPO_ROOT / resolved
                if direct.exists():
                    paths.append(direct)
        # Exclude locale blog translations — they inherit English verification
        if site == "blog":
            paths = [p for p in paths if not _is_locale_file(p)]
        result[site] = [p for p in paths if p.name != "_index.md" or site == "products"]
    return result


# ---------------------------------------------------------------------------
# Claim extraction
# ---------------------------------------------------------------------------

# Patterns for Tier 1 deterministic checks
_RE_CODE_BLOCK = re.compile(r"```([a-z]*)\n(.*?)```", re.DOTALL)  # group1=lang, group2=body
# TC-02/G-02 (MT009 SEED-20): the two alternatives below are ordered so that a
# Python `from X import Y[, Y2...]` statement is consumed by the first
# alternative as ONE match (capturing only the real package path X into
# from_val). Without this, the bare `import` branch previously re-matched
# independently inside the same statement and captured Y (an imported class/
# function name) as if it were itself a package -- a systematic false
# positive for every from-import code example (see pipeline-evidence.md).
_RE_PACKAGE_IMPORT = re.compile(
    r"from\s+(?P<from_val>[\w.@/\-]+)\s+import\s+[\w.,\s()*]+"
    r"|(?:pip install|npm install|poetry add)\s+"
    r"(?:--?[\w-]+(?:=[^\s]+)?\s+)*(?P<install_val>[\w.@/\-]+)"
    r"|(?:import|require|using|nuget|maven)\s+(?P<val>[\w.@/\-]+)",
    re.IGNORECASE,
)
_RE_API_TOKEN = re.compile(r"\b([A-Z][A-Za-z0-9]+)\.([a-z_][A-Za-z0-9_]*)\s*[\(\[]?")
_RE_INTERNAL_LINK = re.compile(r"\[([^\]]+)\]\((/[^\)]+)\)")
_RE_URL_TOKEN = re.compile(r"(?:https?://|git@)\S+", re.IGNORECASE)

# TIER3-TS-FP-01: TypeScript/JavaScript code block filters
# These prevent JS/TS built-in globals and bare import-binding identifiers from
# being extracted as claims and escalating to Tier 3 LLM.
_TS_JS_LANG_TAGS: frozenset[str] = frozenset({"typescript", "javascript", "ts", "js"})
_SHELL_LANG_TAGS: frozenset[str] = frozenset(
    {"bash", "shell", "sh", "powershell", "ps1", "batch", "cmd"}
)
_SHELL_FILE_EXTENSIONS: frozenset[str] = frozenset(
    {"bat", "cmd", "exe", "ps1", "sh"}
)
_TS_JS_STDLIB_CLASSES: frozenset[str] = frozenset({
    # JSON / data built-ins
    "JSON", "Math", "Date", "RegExp",
    # Collections
    "Array", "Map", "Set", "WeakMap", "WeakSet",
    # Primitives / wrappers
    "Number", "String", "Boolean", "BigInt", "Symbol",
    # I/O and runtime
    "Buffer", "console", "Promise", "Function",
    # Reflection / meta
    "Object", "Proxy", "Reflect", "Atomics",
    # Typed arrays
    "ArrayBuffer", "DataView", "SharedArrayBuffer",
    "Uint8Array", "Int8Array", "Uint16Array", "Int16Array",
    "Uint32Array", "Int32Array", "Float32Array", "Float64Array",
    "BigInt64Array", "BigUint64Array",
    # Error types
    "Error", "TypeError", "RangeError", "SyntaxError",
    "ReferenceError", "URIError", "EvalError",
    # Web / Node globals
    "WebAssembly", "Iterator", "Generator",
})


def _match_is_inside_url(block: str, match: re.Match[str]) -> bool:
    """Return True when an API-token regex match is part of a URL.

    Repository URLs such as ``Aspose.Email-FOSS-for-Cpp.git`` contain a
    syntactically API-like ``Cpp.git`` suffix.  Treating that suffix as a
    source-level API claim sends a non-claim through Tier 2 and produces a
    misleading Tier 4 ``needs-review`` result.  Limit the exclusion to URL
    spans on the same line so real ``Class.method`` tokens remain checkable.
    """
    line_start = block.rfind("\n", 0, match.start()) + 1
    line_end = block.find("\n", match.end())
    if line_end < 0:
        line_end = len(block)
    line = block[line_start:line_end]
    # Compare the semantic ``Class.member`` span, not the regex's optional
    # trailing whitespace/parenthesis.  At the end of a code-block line,
    # ``\s*`` may consume the newline and otherwise extend one character past
    # the URL span.
    relative_start = match.start(1) - line_start
    relative_end = match.end(2) - line_start
    return any(
        url.start() <= relative_start and relative_end <= url.end()
        for url in _RE_URL_TOKEN.finditer(line)
    )


def extract_claims(file_path: Path, content: str) -> list[dict]:
    """Extract checkable claims from a markdown file."""
    claims: list[dict] = []
    lines = content.splitlines()

    # Code blocks
    for m in _RE_CODE_BLOCK.finditer(content):
        lang_tag = m.group(1)   # empty string for untagged blocks (``` with no lang)
        block = m.group(2)
        # Untagged blocks: scan only when they explicitly reference aspose.
        # Rationale: untagged blocks are often shell output, config, or prose examples;
        # scanning them produces high noise (System.*, C# keywords, format names, etc.).
        if not lang_tag and "aspose" not in block.lower():
            continue
        line_no = content[: m.start()].count("\n") + 1
        # Package declarations
        for pm in _RE_PACKAGE_IMPORT.finditer(block):
            pkg_val = pm.group("from_val") or pm.group("install_val") or pm.group("val")
            # TIER3-TS-FP-01: For TS/JS code blocks, the regex `import X from 'mod'`
            # captures the binding identifier X (e.g. `is`, `buffer`) rather than the
            # module name.  Skip these bare single-word identifiers — they have no
            # package-like characters and are not competing Aspose package references.
            if lang_tag in _TS_JS_LANG_TAGS and "aspose" not in pkg_val.lower():
                if not any(c in pkg_val for c in ("@", "/", ".", "-")):
                    continue
            claims.append(
                {
                    "type": "package-declaration",
                    "value": pkg_val,
                    "file": str(file_path),
                    "line": line_no,
                    "context": block[:200],
                }
            )
        # API tokens
        for am in _RE_API_TOKEN.finditer(block):
            if _match_is_inside_url(block, am):
                continue
            cls_name = am.group(1)
            member_name = am.group(2)
            # TIER3-TS-FP-01: Skip JS/TS built-in global class names (JSON.stringify,
            # Math.floor, Buffer.from, etc.) — these are standard library calls, not
            # Aspose API tokens.  Applies only to code blocks tagged typescript/javascript.
            if lang_tag in _TS_JS_LANG_TAGS and cls_name in _TS_JS_STDLIB_CLASSES:
                continue
            if lang_tag in _TS_JS_LANG_TAGS:
                # ALL_CAPS identifiers are local constants, not exported Aspose
                # classes (for example EXTENSIONS.includes(...)).
                if cls_name.isupper():
                    continue
                # Prose such as "Express.js" matches the broad Class.member
                # pattern. Preserve an actual call/index expression if one is
                # ever present; only suppress bare language-extension labels.
                if (
                    member_name in _TS_JS_LANG_TAGS
                    and not am.group(0).rstrip().endswith(("(", "["))
                ):
                    continue
            if (
                lang_tag in _SHELL_LANG_TAGS
                and member_name.lower() in _SHELL_FILE_EXTENSIONS
                and not am.group(0).rstrip().endswith(("(", "["))
            ):
                # Shell blocks commonly mention activation scripts such as
                # Activate.ps1. A filename is not an application API claim.
                continue
            claims.append(
                {
                    "type": "api-token",
                    "value": f"{cls_name}.{member_name}",
                    "file": str(file_path),
                    "line": line_no,
                    "context": block[:200],
                }
            )

    # Internal links
    for i, line in enumerate(lines, 1):
        for lm in _RE_INTERNAL_LINK.finditer(line):
            claims.append(
                {
                    "type": "internal-link",
                    "value": lm.group(2),
                    "file": str(file_path),
                    "line": i,
                    "context": line,
                }
            )

    return claims


# ---------------------------------------------------------------------------
# Tier 1: Deterministic verification
# ---------------------------------------------------------------------------

class Tier1Status(str, Enum):
    """Terminal state at the deterministic-to-semantic verification boundary."""

    VERIFIED = "verified"
    FINDING = "finding"
    UNRESOLVED = "unresolved"


@dataclass(frozen=True)
class Tier1Result:
    """Typed Tier 1 result; avoids conflating a pass with an unresolved claim."""

    status: Tier1Status
    finding: dict | None = None


def tier1_verify(claim: dict, api_names: set[str], profile: dict, family: str, platform: str) -> dict | None:
    """Backward-compatible deterministic finding check.

    ``None`` historically meant both "verified" and "unresolved". New
    orchestration must use :func:`tier1_assess`, which makes that distinction
    explicit while preserving this function for registered test/caller
    compatibility.
    """
    ctype = claim["type"]
    value = claim["value"]

    if ctype == "package-declaration":
        # Check if declared package matches profile's known package
        expected_pkg = (profile.get("discovered_actuals") or {}).get("package_name")
        expected_import = (profile.get("discovered_actuals") or {}).get("import_path")
        if expected_pkg and value not in (expected_pkg, expected_pkg.split(":")[-1]):
            # Accept the Python import path and any sub-module of it
            if expected_import and (value == expected_import or value.startswith(expected_import + ".")):
                return None
            # Accept known class names from the API surface
            if value in api_names:
                return None
            # Skip standard library / obvious non-package tokens
            # Only flag values that look like they could be a competing Aspose package reference
            _lang = (profile.get("discovery_hints") or {}).get("language", "").lower()
            # C++ has no package declarations — CMake target names appear in code but are
            # not import statements; skip the package check entirely for C++.
            if _lang == "cpp":
                return None
            # Accept versioned forms of the expected package (e.g. @aspose/3d@24.12.0 for @aspose/3d)
            if expected_pkg and value.startswith(expected_pkg + "@"):
                return None
            # Skip values that start with a dot — format extensions, relative paths, not packages
            if value.startswith("."):
                return None
            # Accept sub-package/sub-namespace imports that start with the expected package root.
            # Example: Java "org.aspose.slides.foss.export.SaveFormat" is a valid import when
            # expected_pkg is "org.aspose.slides.foss".  Same applies to C# sub-namespaces.
            # For Java Maven coordinates (groupId:artifactId), extract groupId as the package root.
            _pkg_root = expected_pkg
            if _lang == "java" and expected_pkg and ":" in expected_pkg:
                _pkg_root = expected_pkg.split(":")[0]
                log.debug("tier1: maven coordinate %r → extracted groupId %r for sub-package check", expected_pkg, _pkg_root)
            if _pkg_root and value.startswith(_pkg_root + "."):
                return None
            # Python: accept underscore-normalized form of hyphenated package names.
            # pip install aspose-cells-foss → import aspose_cells_foss
            if _lang == "python" and expected_pkg:
                _normalized = expected_pkg.replace("-", "_")
                if value == _normalized or value.startswith(_normalized + "."):
                    log.debug("tier1: suppressed %r — underscore form of expected package %r", value, expected_pkg)
                    return None
            # Python/Java: package names are always lowercase by convention.  An uppercase-starting
            # value is a class name or a match inside a string literal (e.g. the code string
            # "Hello from Aspose.Slides FOSS!" causes the regex to match "from Aspose.Slides").
            # Skip these — they are not competing package references.
            if _lang in ("python", "java") and value[:1].isupper():
                return None
            # Language-specific stdlib / single-word filters
            if _lang == "python" and not value.lower().startswith("aspose"):
                log.debug("tier1: suppressed %r — non-aspose Python import (companion/stdlib/third-party)", value)
                return None  # Non-aspose Python import → stdlib/third-party/companion plugin, not competing
            if _lang == "java" and "aspose" not in value.lower():
                return None  # Non-aspose Java import → stdlib/third-party or comment artifact
            if _lang == "csharp" and "aspose" not in value.lower():
                return None  # System.* namespaces, C# keywords, framework refs — not competing packages
            if _lang == "csharp" and expected_pkg:
                _ctx = claim.get("context", "")
                # Suppress partial Aspose match when block context contains the expected package
                # in either its canonical form (Aspose.Cells_FOSS) or its space-separated prose
                # form (Aspose.Cells FOSS — as seen in string literals and expected-output blocks).
                if expected_pkg in _ctx or expected_pkg.replace("_", " ") in _ctx:
                    return None
            if _lang in ("typescript", "javascript") and "aspose" not in value.lower():
                return None  # Non-aspose TS/JS reference — prose word, format name, stdlib, not a package
            return {
                "type": "wrong-package",
                "severity": "M",
                "tier_resolved_by": 1,
                "file": claim["file"],
                "line": claim["line"],
                "old_value": value,
                "correct_value": expected_pkg,
                "description": f"Package declaration '{value}' does not match known package '{expected_pkg}'",
            }

    elif ctype == "api-token":
        # Check if API token exists in api_surface
        if api_names and value not in api_names:
            # Partial match — could be valid; escalate to Tier 2/3 rather than hard-fail
            return None  # not a deterministic mismatch

    elif ctype == "internal-link":
        # Resolve link target relative to repo root.
        # Strategy: try multiple candidate paths in priority order:
        # 1. Explicit subdomain prefix in the link (/blog/ → blog.aspose.org)
        # 2. Same subdomain as the source file (context-aware, with and without /en/)
        # 3. Direct content/ path (legacy fallback)
        _PREFIX_TO_SUBDOMAIN = {
            "blog/": "blog.aspose.org",
            "docs/": "docs.aspose.org",
            "kb/": "kb.aspose.org",
            "products/": "products.aspose.org",
            "reference/": "reference.aspose.org",
        }
        rel = value.lstrip("/")

        def _path_exists(p: Path) -> bool:
            if (
                p.exists()
                or (p / "index.md").exists()
                or (p / "_index.md").exists()
                or (p / "index.en.md").exists()
                or p.with_suffix(".md").exists()
            ):
                return True
            # Case-insensitive fallback (handles PascalCase files on case-sensitive FS)
            parent = p.parent
            name_lower = p.name.lower()
            try:
                for child in parent.iterdir():
                    if child.name.lower() == name_lower or child.name.lower() == name_lower + ".md":
                        return True
            except (OSError, NotADirectoryError):
                pass
            return False

        candidates: list[Path] = []
        # (1) Subdomain from explicit URL prefix
        for stripped_prefix, subdomain in _PREFIX_TO_SUBDOMAIN.items():
            if rel.startswith(stripped_prefix):
                tail = rel[len(stripped_prefix):]
                candidates.append(_REPO_ROOT / "content" / subdomain / tail)
                candidates.append(_REPO_ROOT / "content" / subdomain / "en" / tail)
        # (2) Same subdomain as source file (context-aware)
        src_path = Path(claim["file"])
        content_root = _REPO_ROOT / "content"
        _ALL_SUBDOMAINS = [
            "reference.aspose.org", "docs.aspose.org",
            "kb.aspose.org", "products.aspose.org", "blog.aspose.org",
        ]
        try:
            src_rel = src_path.relative_to(content_root)
            src_subdomain_dir = src_rel.parts[0]  # e.g. "reference.aspose.org"
            candidates.append(content_root / src_subdomain_dir / rel)
            candidates.append(content_root / src_subdomain_dir / "en" / rel)
        except (ValueError, IndexError):
            src_subdomain_dir = None
        # (3) Try all known subdomains (cross-subdomain links)
        for subdomain in _ALL_SUBDOMAINS:
            if subdomain != src_subdomain_dir:
                candidates.append(content_root / subdomain / rel)
                candidates.append(content_root / subdomain / "en" / rel)
        # (4) Direct fallback
        candidates.append(_REPO_ROOT / "content" / rel)

        if not any(_path_exists(c) for c in candidates):
            return {
                "type": "broken-link",
                "severity": "S",
                "tier_resolved_by": 1,
                "file": claim["file"],
                "line": claim["line"],
                "old_value": value,
                "correct_value": None,
                "description": f"Internal link target not found: {value}",
            }

    return None


def tier1_assess(
    claim: dict,
    api_names: set[str],
    profile: dict,
    family: str,
    platform: str,
) -> Tier1Result:
    """Return a typed deterministic disposition for one extracted claim."""
    finding = tier1_verify(claim, api_names, profile, family, platform)
    if finding is not None:
        return Tier1Result(Tier1Status.FINDING, finding)

    ctype = claim.get("type")
    if ctype == "api-token":
        status = Tier1Status.VERIFIED if claim.get("value") in api_names else Tier1Status.UNRESOLVED
        return Tier1Result(status)
    if ctype == "internal-link":
        # A missing link would already have produced a finding.
        return Tier1Result(Tier1Status.VERIFIED)
    if ctype == "package-declaration":
        expected_pkg = (profile.get("discovered_actuals") or {}).get("package_name")
        # With an authoritative expected package, Tier 1 either emitted a
        # mismatch or deliberately accepted/suppressed the declaration.
        status = Tier1Status.VERIFIED if expected_pkg else Tier1Status.UNRESOLVED
        return Tier1Result(status)
    return Tier1Result(Tier1Status.UNRESOLVED)


# ---------------------------------------------------------------------------
# Tier 2 embedding similarity thresholds
# ---------------------------------------------------------------------------
# Scores in the BAND_LOW–MATCH_HIGH range are non-deterministic due to float
# precision.  They always escalate to Tier 3 regardless of exact score.
TIER2_MATCH_HIGH = 0.75   # Above this: always MATCH (deterministic)
TIER2_MATCH_LOW = 0.70    # Original threshold (kept for reference)
TIER2_BAND_LOW = 0.65     # Below this: always UNVERIFIABLE → escalate
TIER2_MISMATCH = 0.40     # Below this: MISMATCH


# ---------------------------------------------------------------------------
# Tier 2: Vector semantic search
# ---------------------------------------------------------------------------

def _cosine(a: list[float], b: list[float]) -> float:
    """Cosine similarity between two equal-length float vectors."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


def _embed_text(text: str, required_profile=None, *, return_result: bool = False):
    """Embed a single text via LLMRouter (professionalize → Ollama fallback).

    By default, returns the embedding vector or ``None`` for backward
    compatibility.  ``return_result=True`` preserves the typed router result
    so callers can distinguish contract mismatch from runtime unavailability.
    """
    try:
        from lib.llm_router import EndpointStatus as _ES, LLMCallContext
        router = _get_router()
    except (ImportError, RuntimeError) as exc:
        log.warning("LLM router unavailable for embedding: %s", exc)
        return None

    result = router.call_embeddings(
        [text],
        timeout=15,
        required_profile=required_profile,
        context=LLMCallContext(
            consumer_id="gap-eval-tier2",
            run_id=_gaeval_run_id or "gap-eval",
            job_type="gap-eval",
            work_slice_id="tier2",
        ),
    )
    if result.metrics_events:
        _gaeval_metrics_events.extend(result.metrics_events)
    if return_result:
        return result
    if result.status == _ES.OK and result.data:
        return result.data[0]
    return None


def tier2_verify(claim: dict, family: str, platform: str) -> tuple[str, float] | None:
    """Vector search against api.vectors.json.

    Returns (verdict, confidence) or None if vectors unavailable.
    Verdict: 'MATCH' | 'MISMATCH' | 'UNVERIFIABLE'
    Thresholds: ≥0.75 → MATCH, 0.40–0.75 → escalate to Tier 3, <0.40 → MISMATCH
    """
    from lib.llm_router import EmbeddingProfile
    vectors_root = _REPO_ROOT / "knowledge" / "_vectors" / family / platform
    vectors_path = vectors_root / "api.vectors.json"
    manifest = None
    active_path = vectors_root / "active.json"
    if active_path.exists():
        try:
            active = json.loads(active_path.read_text(encoding="utf-8"))
            profile_dir = vectors_root / "profiles" / active["profile_id"]
            manifest = json.loads((profile_dir / "manifest.json").read_text(encoding="utf-8"))
            vectors_path = profile_dir / manifest.get("vector_file", "api.vectors.json")
        except Exception as exc:
            log.warning("Invalid active embedding profile for %s/%s: %s", family, platform, exc)
            return None
    if not vectors_path.exists():
        return None

    try:
        vdata = json.loads(vectors_path.read_text(encoding="utf-8"))
    except Exception:
        return None

    vectors: dict[str, list[float]] = vdata.get("vectors", {})
    if not vectors:
        return None

    claim_text = claim.get("value", "")
    if not claim_text:
        return None

    # Try to embed the claim
    required_profile = EmbeddingProfile(
        profile_id=(manifest or vdata).get("profile_id", "legacy"),
        provider=(manifest or vdata).get("provider", ""),
        model=(manifest or vdata).get("model", ""),
        dimensions=int((manifest or vdata).get("dimensions", 0)),
        config_digest=(manifest or vdata).get("registry_digest", ""),
    )
    embedding = _embed_text(claim_text, required_profile, return_result=True)
    # Tests and compatibility callers may inject a vector directly. The real
    # router path returns a typed CallResult.
    if isinstance(embedding, list):
        claim_vec = embedding
    elif embedding is not None and hasattr(embedding, "status"):
        from lib.llm_router import EndpointStatus as _ES
        if embedding.status == _ES.CONTRACT_MISMATCH:
            log.warning(
                "Embedding profile contract mismatch for %s/%s; "
                "skipping dense and lexical Tier 2 comparison",
                family,
                platform,
            )
            return ("UNVERIFIABLE", 0.0)
        claim_vec = (
            embedding.data[0]
            if embedding.status == _ES.OK and embedding.data
            else None
        )
    else:
        claim_vec = None

    if claim_vec:
        # Dimension mismatch guard — warn if query dims ≠ stored dims
        stored_dims = vdata.get("dimensions")
        query_dims = len(claim_vec)
        if stored_dims and query_dims != stored_dims:
            log.warning(
                "Dimension mismatch: query=%d, stored=%d for %s/%s. "
                "Tier 2 results will be unreliable. Re-embed with matching model.",
                query_dims, stored_dims, family, platform,
            )
            return ("UNVERIFIABLE", 0.0)

        # Dense cosine similarity against all stored vectors
        best_key = ""
        best_score = 0.0
        for key, vec in vectors.items():
            if not isinstance(vec, list):
                continue
            score = _cosine(claim_vec, vec)
            if score > best_score:
                best_score = score
                best_key = key
        if best_score >= TIER2_MATCH_HIGH:      # >= 0.75: confident match
            return ("MATCH", best_score)
        if best_score >= TIER2_MISMATCH:        # 0.40–0.75: escalate (includes uncertainty band)
            return ("UNVERIFIABLE", best_score)
        return ("MISMATCH", best_score)         # < 0.40: confident mismatch
    else:
        # TF-IDF last resort: key substring matching
        claim_lower = claim_text.lower()
        for key in vectors:
            key_lower = key.lower()
            if claim_lower in key_lower or key_lower.endswith(claim_lower):
                return ("MATCH", 0.75)
        return ("UNVERIFIABLE", 0.30)


# ---------------------------------------------------------------------------
# Tier 3: LLM verification
# ---------------------------------------------------------------------------

@dataclass
class Tier3Result:
    """Structured result from Tier 3 LLM verification.

    Replaces the old ``_TIER3_UNAVAILABLE`` string sentinel that collapsed
    three unrelated failure modes into one indistinguishable string.
    """
    verdict: dict | None
    status: EndpointStatus
    reason: str
    endpoint_used: str | None = None
    fallback_artifact: str | None = None


def tier3_verify(claim: dict, family: str, platform: str, clone_cache: Path) -> Tier3Result:
    """LLM verification using gpt-oss (professionalize.com) with llama3.2 fallback.

    Returns a ``Tier3Result`` on all paths — never raises.
    IMPORTANT: Evidence frontmatter is NEVER sent to LLM (AGENTS.md rule).
    """
    try:
        import requests  # type: ignore
    except ImportError:
        log.debug("requests not available — Tier 3 unavailable")
        return Tier3Result(
            verdict=None,
            status=EndpointStatus.NOT_CONFIGURED,
            reason="requests not installed",
        )

    # Gather source context from clone cache
    source_excerpt = _get_source_context(claim, clone_cache)
    if not source_excerpt:
        # This is a DATA problem (missing clone cache), not an LLM problem.
        # Do NOT attempt Ollama — the endpoint works fine, we just have no context.
        log.debug("No source context found for claim in %s", clone_cache)
        return Tier3Result(
            verdict=None,
            status=EndpointStatus.INTENTIONAL_SKIP,
            reason="no_source_context",
        )

    prompt_system = (
        "You are a technical documentation auditor. Verify whether a documentation "
        "claim is accurate given the library source code provided. Be precise and conservative."
    )
    prompt_user = (
        f"Source code evidence (from clone cache):\n---\n{source_excerpt[:2000]}\n---\n\n"
        f"Documentation claim being verified:\n"
        f"File: {claim['file']}:{claim['line']}\n"
        f"Type: {claim['type']}\n"
        f"Value: {claim['value']}\n\n"
        'Is this claim accurate? Output only valid JSON:\n'
        '{"accurate": bool, "confidence": 0.0, "issue": null, '
        '"correction": null, "severity": "M|S|O", '
        '"root_cause": "wrong-api|phantom-api|wrong-claim|wrong-package|wrong-unit|unimplemented-as-working|unverifiable"}'
    )

    full_result = _llm_call_full(prompt_system, prompt_user)
    if full_result is None:
        return Tier3Result(
            verdict=None,
            status=EndpointStatus.UNREACHABLE,
            reason="llm router unavailable",
        )

    from lib.llm_router import EndpointStatus as _ES
    if full_result.status != _ES.OK:
        return Tier3Result(
            verdict=None,
            status=full_result.status,
            reason=full_result.error or "llm call failed",
            endpoint_used=full_result.provider or None,
            fallback_artifact=full_result.fallback_artifact or None,
        )

    cr = full_result.data
    if cr is None or cr.get("accurate", True):
        return Tier3Result(
            verdict=None,
            status=EndpointStatus.OK,
            reason="claim confirmed accurate",
            endpoint_used=full_result.provider,
            fallback_artifact=full_result.fallback_artifact or None,
        )

    finding = {
        "type": cr.get("root_cause", "wrong-claim"),
        "severity": cr.get("severity", "S"),
        "tier_resolved_by": 3,
        "file": claim["file"],
        "line": claim["line"],
        "old_value": claim["value"],
        "correct_value": cr.get("correction"),
        "description": cr.get("issue", "LLM found claim inaccurate"),
        "llm_confidence": cr.get("confidence", 0.0),
    }
    return Tier3Result(
        verdict=finding,
        status=EndpointStatus.OK,
        reason="claim inaccurate",
        endpoint_used=full_result.provider,
        fallback_artifact=full_result.fallback_artifact or None,
    )


def _get_source_context(claim: dict, clone_cache: Path) -> str:
    """Retrieve relevant source excerpt from clone cache for a claim."""
    value = claim.get("value", "")
    if not value or not clone_cache.exists():
        return ""
    # Search clone cache for the claim value
    try:
        result = subprocess.run(
            ["grep", "-r", "--include=*.java", "--include=*.py", "--include=*.cs",
             "--include=*.ts", "--include=*.cpp", "--include=*.h", "--include=*.rs",
             "-l", value, str(clone_cache)],
            capture_output=True, text=True, timeout=10
        )
        files = sorted(result.stdout.strip().splitlines())[:3]
        if not files:
            return ""
        excerpts: list[str] = []
        for fpath in files:
            try:
                text = Path(fpath).read_text(encoding="utf-8", errors="replace")
                # Find surrounding context (up to 30 lines)
                lines = text.splitlines()
                for i, line in enumerate(lines):
                    if value in line:
                        start = max(0, i - 5)
                        end = min(len(lines), i + 25)
                        excerpts.append("\n".join(lines[start:end]))
                        break
            except OSError:
                continue
        return "\n\n---\n\n".join(excerpts)[:2000]
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return ""


_router = None  # lazy singleton — avoids YAML re-read per call
_gaeval_metrics_events: list = []  # CS-001 events from LLM calls; reset per run_gap_eval()
_gaeval_run_id: str | None = None


def _get_router():
    """Return cached LLMRouter instance (lazy init)."""
    global _router
    if _router is None:
        from lib.llm_router import LLMRouter
        _router = LLMRouter()
    return _router


def _llm_call(system: str, user: str) -> dict | None:
    """Call LLM with professionalize.com → Ollama fallback.

    Returns parsed JSON dict or None on failure.
    Delegates to shared LLMRouter.
    """
    try:
        from lib.llm_router import EndpointStatus as _ES
        router = _get_router()
    except (ImportError, RuntimeError) as exc:
        log.warning("LLM router unavailable: %s", exc)
        return None

    result = router.call_chat(
        system, user,
        temperature=0.1,
        timeout=30,
        json_extract=True,
        json_array=False,
        context=__import__("lib.llm_router", fromlist=["LLMCallContext"]).LLMCallContext(
            consumer_id="gap-eval-tier3",
            run_id=_gaeval_run_id or "gap-eval",
            job_type="gap-eval",
            work_slice_id="tier3",
        ),
    )

    # CS-001: collect MetricsEvents
    if hasattr(result, 'metrics_events') and result.metrics_events:
        _gaeval_metrics_events.extend(result.metrics_events)
    if result.status == _ES.OK:
        log.info("LLM call via %s", result.provider)
        return result.data
    return None


def _llm_call_full(system: str, user: str):
    """Like _llm_call but returns the full CallResult for metadata extraction."""
    try:
        from lib.llm_router import EndpointStatus as _ES, CallResult
        router = _get_router()
    except (ImportError, RuntimeError) as exc:
        log.warning("LLM router unavailable: %s", exc)
        return None

    result = router.call_chat(
        system, user,
        temperature=0.1,
        timeout=30,
        json_extract=True,
        json_array=False,
        context=__import__("lib.llm_router", fromlist=["LLMCallContext"]).LLMCallContext(
            consumer_id="gap-eval-tier3",
            run_id=_gaeval_run_id or "gap-eval",
            job_type="gap-eval",
            work_slice_id="tier3",
        ),
    )
    # CS-001: collect MetricsEvents from full call
    if result is not None and hasattr(result, 'metrics_events') and result.metrics_events:
        _gaeval_metrics_events.extend(result.metrics_events)
    return result


# ---------------------------------------------------------------------------
# Publication verdict
# ---------------------------------------------------------------------------

def _load_false_positives() -> list[dict]:
    """Load known_false_positives.yaml from the gap-eval directory.

    Returns a list of suppression rule dicts (empty list if file absent or
    unparseable so callers can always iterate safely).
    """
    fp_path = _GAP_EVAL_DIR / "known_false_positives.yaml"
    if not fp_path.exists():
        return []
    try:
        import yaml  # type: ignore
        data = yaml.safe_load(fp_path.read_text(encoding="utf-8")) or {}
        return data.get("false_positives", [])
    except Exception as exc:  # pragma: no cover
        log.warning("Could not load known_false_positives.yaml: %s", exc)
        return []


def _apply_false_positives(
    findings: list[dict],
    family: str,
    platform: str,
    fp_rules: list[dict],
) -> int:
    """Mark findings that match a known-false-positive rule as suppressed.

    Mutates findings in place; returns the count of suppressed findings.
    Match fields within a rule are ANDed; omitted fields match any value.
    """
    suppressed = 0
    for finding in findings:
        if finding.get("status") in ("fixed", "wontfix", "suppressed"):
            continue
        for rule in fp_rules:
            m = rule.get("matches", {})
            if m.get("family") and m["family"] != family:
                continue
            if m.get("platform") and m["platform"] != platform:
                continue
            if m.get("type") and m["type"] != finding.get("type"):
                continue
            needle = m.get("description_contains", "")
            if needle and needle not in finding.get("description", ""):
                continue
            # All present match fields passed — suppress this finding
            finding["status"] = "suppressed"
            finding["suppressed_by"] = rule.get("id", "unknown")
            log.warning("[SUPPRESSED] finding id=%s matched known false positive rule=%s",
                        finding.get("id", "?"), finding["suppressed_by"])
            suppressed += 1
            break
    return suppressed


def compute_verdict(findings: list[dict]) -> str:
    """Determine publication verdict from open findings.

    Tier 3 (LLM) findings are advisory-only — they appear in the report
    but never block the verdict. This is because Tier 3 has a structural
    12%+ false positive rate (see known_false_positives.yaml).

    FIX (forensic audit): findings auto-marked "fixed" by state.py merge
    (because they weren't re-detected in a subsequent run) are counted as
    "unverified fixes". If there are many unverified M-severity fixes,
    the verdict is downgraded to CONDITIONAL to prevent false PUBLICATION
    READY verdicts. A finding is considered verified-fixed only if it has
    a "fixed_verified" flag set by a human or re-verification pass.
    """
    open_findings = [f for f in findings if f.get("status") not in ("fixed", "wontfix", "suppressed")]

    # Tier 3 findings are advisory — exclude from blocking verdict
    blocking_findings = [f for f in open_findings if f.get("tier_resolved_by") != 3]

    m_in_core = any(
        f.get("severity") == "M"
        for f in blocking_findings
        if not _is_blog_only(f.get("file", ""))
    )
    m_in_blog = any(
        f.get("severity") == "M"
        for f in blocking_findings
        if _is_blog_only(f.get("file", ""))
    )
    has_s = any(f.get("severity") == "S" for f in blocking_findings)

    if m_in_core:
        return "NOT PUBLISHABLE"
    if m_in_blog or has_s:
        return "CONDITIONAL"

    # Count unverified "fixed" M-severity findings: auto-marked fixed by
    # state merge but never confirmed by re-verification or human review.
    unverified_fixed_m = sum(
        1 for f in findings
        if f.get("status") == "fixed"
        and f.get("severity") == "M"
        and not f.get("fixed_verified")
        and not _is_blog_only(f.get("file", ""))
    )
    if unverified_fixed_m > 0:
        log.warning(
            "Verdict downgraded: %d M-severity findings are auto-fixed but "
            "not verified. Set fixed_verified: true after manual confirmation.",
            unverified_fixed_m,
        )
        return "CONDITIONAL — unverified fixes"

    # Content-eval grade gate: if any evaluated page has grade D or F,
    # downgrade verdict to CONDITIONAL. Uses fast regex read — no evaluator
    # execution, no knowledge loading, sub-millisecond per file.
    try:
        from lib.grade_writer import read_grade
        for finding in findings:
            filepath = Path(finding.get("file", ""))
            if not filepath.is_absolute():
                filepath = _REPO_ROOT / filepath
            if filepath.exists():
                stored = read_grade(filepath)
                if stored and stored.get("grade") in ("D", "F"):
                    log.warning(
                        "Verdict downgraded: %s has content-eval grade %s",
                        finding.get("file", "?"), stored["grade"],
                    )
                    return "CONDITIONAL — content-eval grade gate"
    except ImportError:
        log.debug("grade_writer not available — skipping content-eval gate")

    return "PUBLICATION READY"


def _is_blog_only(file_path: str) -> bool:
    return "blog.aspose.org" in file_path or "/blog/" in file_path


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

def generate_report(
    family: str,
    platform: str,
    findings: list[dict],
    verdict: str,
    delta_section: str,
    clone_sha: str,
    llm_tier: str,
) -> str:
    """Generate the 8-section gap analysis report."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    terminal_statuses = {"fixed", "wontfix", "suppressed"}
    open_findings = [f for f in findings if f.get("status") not in terminal_statuses]
    m_findings = [f for f in open_findings if f.get("severity") == "M"]
    s_findings = [f for f in open_findings if f.get("severity") == "S"]
    needs_review = [f for f in open_findings if f.get("type") == "needs-review"]

    def finding_block(f: dict) -> str:
        return (
            f"- **{f.get('id', '?')}** `{f.get('type', '?')}` "
            f"[{f.get('severity', '?')}] `{Path(f.get('file', '?')).name}:{f.get('line', '?')}`  \n"
            f"  {f.get('description', '')}  \n"
            f"  Old: `{f.get('old_value', '')}` → Correct: `{f.get('correct_value', 'N/A')}`\n"
        )

    report = [
        f"# Gap Analysis: {family}/{platform}",
        f"**Date**: {today}  **Clone SHA**: {clone_sha[:12]}  **LLM tier**: {llm_tier}  **Verdict**: {verdict}",
        "",
    ]

    if delta_section:
        report.append(delta_section)
        report.append("")

    report += [
        "## Section 1: Executive Summary",
        f"Verdict: **{verdict}**  |  M-findings: {len(m_findings)}  |  S-findings: {len(s_findings)}",
        "",
        "## Section 2: M-Severity Findings",
    ]
    if m_findings:
        for f in m_findings:
            report.append(finding_block(f))
    else:
        report.append("_None_")

    report += [
        "",
        "## Section 3: S-Severity Findings",
    ]
    if s_findings:
        for f in s_findings:
            report.append(finding_block(f))
    else:
        report.append("_None_")

    report += [
        "",
        "## Section 4: Knowledge Model Check",
        "_Run completed — see findings for knowledge-model-wrong entries if any._",
        "",
        "## Section 5: Missing Mandatory Sections",
        "_See findings with type=missing-section._",
        "",
        "## Section 6: Clone Cache Baseline",
        f"- Family: {family}, Platform: {platform}",
        f"- Clone cache SHA: {clone_sha}",
        "",
        "## Section 7: LLM Verification Summary",
        f"- Tier used: {llm_tier}",
        f"- Tier 1 (deterministic): {sum(1 for f in open_findings if f.get('tier_resolved_by') == 1)} findings",
        f"- Tier 2 (vector): {sum(1 for f in open_findings if f.get('tier_resolved_by') == 2)} findings",
        f"- Tier 3 (LLM): {sum(1 for f in open_findings if f.get('tier_resolved_by') == 3)} findings",
        f"- NEEDS_REVIEW: {len(needs_review)} findings",
        "",
        "## Section 8: Publication Verdict",
        f"**{verdict}**",
        "",
        "_Generated by S-43 gap-eval._",
    ]

    return "\n".join(report)


# ---------------------------------------------------------------------------
# Clone cache SHA helper
# ---------------------------------------------------------------------------

def get_clone_sha(clone_path: Path) -> str:
    """Get HEAD SHA of clone cache git repo."""
    try:
        result = subprocess.run(
            ["git", "-C", str(clone_path), "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return "unknown"


# ---------------------------------------------------------------------------
# Stage 1: Clone cache baseline
# ---------------------------------------------------------------------------

def _read_build_package(clone_path: Path, profile: dict) -> str | None:
    """Read the actual package name from the clone cache build file."""
    hints = profile.get("discovery_hints") or {}
    source_file = hints.get("package_source_file", "")
    extraction = hints.get("package_extraction", "")
    if not source_file:
        return None
    build_file = clone_path / source_file
    if not build_file.exists():
        # Try common alternatives
        for alt in ("pom.xml", "setup.py", "pyproject.toml", "package.json", "*.csproj", "Cargo.toml"):
            candidates = list(clone_path.rglob(alt))
            if candidates:
                build_file = candidates[0]
                break
        else:
            return None
    try:
        text = build_file.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    # Handle xpath-style Maven coordinate concatenation: xpath://groupId + ':' + //artifactId
    if "xpath:" in extraction and "groupId" in extraction and "artifactId" in extraction:
        gid_m = re.search(r"<groupId>([\w.]+)</groupId>", text)
        aid_m = re.search(r"<artifactId>([\w.\-]+)</artifactId>", text)
        if gid_m and aid_m:
            return f"{gid_m.group(1)}:{aid_m.group(1)}"
    # CMake target extraction used by C++ profiles.  Match the first real
    # add_library target and stop before later ALIAS declarations.
    if extraction.strip().lower() == "cmake:add_library":
        target_m = re.search(
            r"(?im)^\s*add_library\s*\(\s*([A-Za-z_][A-Za-z0-9_.+\-]*)",
            text,
        )
        if target_m:
            return target_m.group(1)
    # Try regex extraction from hint
    if "regex:" in extraction:
        pat = extraction.split("regex:", 1)[1].strip()
        m = re.search(pat, text)
        if m:
            return m.group(1)
    # Heuristic fallbacks
    for pat in [
        r"<groupId>([\w.]+)</groupId>",
        r"<artifactId>([\w.\-]+)</artifactId>",
        r"""name\s*=\s*['"]([^'"]+)['"]""",
        r'"name":\s*"([^"]+)"',
        r'<PackageId>([\w.]+)</PackageId>',
    ]:
        m = re.search(pat, text)
        if m:
            return m.group(1)
    return None


def stage1_baseline(family: str, platform: str, clone_path: Path, profile: dict,
                    make_id_fn) -> list[dict]:
    """Stage 1: Clone Cache Baseline — verify build file matches profile."""
    findings: list[dict] = []
    actual_pkg = _read_build_package(clone_path, profile)
    if actual_pkg is None:
        log.warning("Stage 1: could not read package name from clone cache %s", clone_path)
        return findings
    expected_pkg = (profile.get("discovered_actuals") or {}).get("package_name", "")
    if expected_pkg and actual_pkg != expected_pkg:
        log.info("Stage 1: package mismatch — profile says '%s', build file says '%s'",
                 expected_pkg, actual_pkg)
        findings.append({
            "id": make_id_fn(family, platform, "knowledge-model-wrong",
                             str(clone_path), 0, expected_pkg),
            "type": "knowledge-model-wrong",
            "severity": "S",
            "tier_resolved_by": 1,
            "file": str(clone_path),
            "line": 0,
            "old_value": expected_pkg,
            "correct_value": actual_pkg,
            "description": (
                f"Profile package_name '{expected_pkg}' does not match "
                f"build file '{actual_pkg}' in clone cache"
            ),
        })
    log.info("Stage 1 complete: actual package='%s'", actual_pkg)
    return findings


# ---------------------------------------------------------------------------
# Stage 2: Knowledge model validation
# ---------------------------------------------------------------------------

def stage2_knowledge_validation(family: str, platform: str, clone_path: Path,
                                api_data: list[dict], make_id_fn, *,
                                max_entries: int = 0, seed: int = 42) -> list[dict]:
    """Stage 2: Verify api_surface entries against clone cache grep.

    Args:
        max_entries: 0 = check all entries (default).  >0 = deterministic
                     sample of N entries using *seed*.
        seed: Random seed used when *max_entries* > 0.
    """
    import random
    findings: list[dict] = []
    if not api_data or not clone_path.exists():
        return findings
    if max_entries > 0:
        if max_entries > len(api_data):
            log.warning("max_entries=%d exceeds api_data size=%d — checking all entries",
                        max_entries, len(api_data))
        rng = random.Random(seed)
        sample = rng.sample(api_data, min(max_entries, len(api_data)))
    else:
        sample = api_data
    for entry in sample:
        name = entry.get("name", "")
        if not name:
            continue
        try:
            result = subprocess.run(
                ["grep", "-r", "--include=*.java", "--include=*.py",
                 "--include=*.cs", "--include=*.ts", "--include=*.cpp", "--include=*.h",
                 "--include=*.rs",
                 "-l", name, str(clone_path)],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode != 0 and not result.stdout.strip():
                log.info("Stage 2: '%s' not found in clone cache source", name)
                findings.append({
                    "id": make_id_fn(family, platform, "knowledge-model-wrong",
                                     str(clone_path), 0, name),
                    "type": "knowledge-model-wrong",
                    "severity": "S",
                    "tier_resolved_by": 1,
                    "file": str(clone_path),
                    "line": 0,
                    "old_value": name,
                    "correct_value": None,
                    "description": (
                        f"api_surface entry '{name}' not found in clone cache source — "
                        "may be phantom API or renamed class"
                    ),
                })
        except (subprocess.TimeoutExpired, FileNotFoundError):
            continue
    log.info("Stage 2 complete: checked %d entries, %d possible phantom APIs",
             len(sample), len(findings))
    return findings


# ---------------------------------------------------------------------------
# Stage 7: Missing content detection
# ---------------------------------------------------------------------------

def stage7_missing_sections(family: str, platform: str, content_files: dict[str, list],
                             profile: dict, make_id_fn,
                             repo_root: Path | None = None) -> list[dict]:
    """Stage 7: Verify mandatory content exists.

    When a site_plan.yaml is present for the family/platform, performs
    page-level detection (checks each expected path individually).  This
    supersedes the coarser section-level detection from the profile.

    Falls back to section-level detection (original behaviour) when no
    site_plan.yaml is found.
    """
    findings: list[dict] = []
    _repo_root = repo_root or _REPO_ROOT

    # --- Try page-level detection via site_plan.yaml ---
    site_plan = load_site_plan(family, platform, _repo_root)

    if site_plan:
        log.info("Stage 7: site_plan.yaml found — using page-level detection")
        # Support both wrapped {"plan": {...}} and legacy flat format
        _sp_root = site_plan.get("plan", site_plan)
        sections = _sp_root.get("sections") or {}
        for site_key, section_data in sections.items():
            if not isinstance(section_data, dict):
                continue
            pages = section_data.get("pages") or []
            for page in pages:
                if not isinstance(page, dict):
                    continue
                path_str = page.get("path")
                if not path_str:
                    continue
                mandatory = page.get("mandatory", False)
                # Resolve the path relative to the repo root
                abs_path = _repo_root / path_str
                if not abs_path.exists():
                    severity = "medium" if mandatory else "low"
                    findings.append({
                        "id": make_id_fn(family, platform, "missing-page",
                                         path_str, 0, path_str),
                        "type": "missing-page",
                        "severity": severity,
                        "tier_resolved_by": 1,
                        "file": path_str,
                        "line": 0,
                        "old_value": "",
                        "correct_value": None,
                        "description": f"Expected page not found: {path_str}",
                        "wave": 3,
                        "strategy": "page-generation",
                        "section": site_key,
                        "mandatory": mandatory,
                    })
        mandatory_missing = sum(1 for f in findings if f.get("mandatory"))
        optional_missing = len(findings) - mandatory_missing
        log.info(
            "Stage 7 complete (page-level): %d missing pages "
            "(%d mandatory, %d optional)",
            len(findings), mandatory_missing, optional_missing,
        )
    else:
        # --- Fallback: section-level detection from profile ---
        log.info("Stage 7: no site_plan.yaml — using section-level detection from profile")
        for section in profile.get("expected_sections") or []:
            if not section.get("mandatory", False):
                continue
            site = section.get("site", "")
            if not site:
                continue
            files = content_files.get(site, [])
            if not files:
                log.info("Stage 7: mandatory site '%s' has no content files for %s/%s",
                         site, family, platform)
                findings.append({
                    "id": make_id_fn(family, platform, "missing-section",
                                     f"content/{site}.aspose.org", 0, site),
                    "type": "missing-section",
                    "severity": "M",
                    "tier_resolved_by": 1,
                    "file": f"content/{site}.aspose.org/en/{family}/{platform}/",
                    "line": 0,
                    "old_value": "",
                    "correct_value": None,
                    "description": (
                        f"Mandatory {site} section has no content files for {family}/{platform}"
                    ),
                })
        log.info("Stage 7 complete (section-level): %d missing mandatory sections", len(findings))

    return findings


# ---------------------------------------------------------------------------
# Main evaluation runner
# ---------------------------------------------------------------------------

def run_gap_eval(
    family: str,
    platform: str,
    scope: str = "all",
    out_override: str | None = None,
    state_dir: Path | None = None,
    no_llm: bool = False,
    no_embed: bool = False,
    dry_run: bool = False,
    seed: int = 42,
    max_stage2_entries: int = 0,
    no_tier3_cache: bool = False,
) -> dict:
    """Run S-43 gap evaluation for a family/platform.

    Args:
        seed: Random seed for deterministic Stage 2 sampling.
        max_stage2_entries: 0 = check all (default).  >0 = sample N entries.

    Returns the findings dict suitable for JSON serialisation.
    """
    global _gaeval_metrics_events, _gaeval_run_id
    import time as _geval_time
    t_start = _geval_time.monotonic()
    _gaeval_metrics_events = []
    try:
        from commands.ops.metrics_schema import generate_run_id as _gen_run_id
        _gaeval_run_id = _gen_run_id()
    except Exception:
        _gaeval_run_id = None

    from state import load_state, save_state, make_finding_id, merge_findings, build_delta_section  # type: ignore
    from tier3_cache import Tier3Cache  # type: ignore

    log.info("=== S-43 gap-eval: %s/%s (scope=%s) ===", family, platform, scope)

    # Stage 0: Pre-flight
    clone_path = _clone_cache_path(family, platform)
    if not clone_path.exists():
        raise FileNotFoundError(f"Clone cache not found: {clone_path}")

    profile = _load_profile(family, platform)
    profile_missing = not _profile_path(family, platform).exists()
    api_data = _load_api_surface(family, platform)
    api_names = _build_api_name_set(api_data)
    if not api_names:
        log.error("PRECONDITION FAILED: api_surface.json exists but contains no API names for %s/%s. "
                  "Knowledge bootstrap may have produced incomplete artifacts.", family, platform)
        raise ValueError(
            f"PRECONDITION FAILED: api_surface.json for {family}/{platform} contains no API names. "
            f"Re-run /knowledge-bootstrap {family} {platform}."
        )
    clone_sha = get_clone_sha(clone_path)

    # --no-llm implies --no-embed: both Tier 3 (LLM) and Tier 2 (embeddings) require network.
    _no_embed = no_embed or no_llm

    llm_tier = "none" if no_llm else "not-used"

    prior_state = load_state(family, platform, state_dir)
    log.info("Prior state: verdict=%s, %d prior findings", prior_state.get("verdict"), len(prior_state.get("findings", [])))

    # Initialise Tier 3 cache (noop when no_llm=True or no_tier3_cache=True)
    _t3_cache = Tier3Cache(prior_state, _profile_path(family, platform), clone_sha)

    # Stage 1: Clone cache baseline
    raw_findings: list[dict] = []
    if profile_missing:
        raw_findings.append(_missing_profile_finding(family, platform))
    raw_findings.extend(stage1_baseline(family, platform, clone_path, profile, make_finding_id))

    # Safety: if Stage 1 detected a package name mismatch, override profile
    # in-memory so Tier 1 doesn't generate false wrong-package findings.
    for f in raw_findings:
        if f["type"] == "knowledge-model-wrong" and f.get("correct_value"):
            corrected_pkg = f["correct_value"]
            log.warning(
                "Stage 1 detected package mismatch — overriding profile "
                "package_name with '%s' for Tier 1", corrected_pkg,
            )
            profile = copy.deepcopy(profile)  # deep copy to avoid mutating original
            profile.setdefault("discovered_actuals", {})["package_name"] = corrected_pkg
            break

    # Stage 2: Knowledge model validation
    raw_findings.extend(stage2_knowledge_validation(
        family, platform, clone_path, api_data, make_finding_id,
        max_entries=max_stage2_entries, seed=seed,
    ))

    # Stage 3: Content discovery
    content_files = discover_content_files(family, platform, scope)
    total_files = sum(len(v) for v in content_files.values())
    log.info("Discovered %d content files across %d sites", total_files, len(content_files))
    for site, paths in content_files.items():
        for fpath in paths:
            try:
                content = fpath.read_text(encoding="utf-8", errors="replace")
            except OSError as exc:
                log.warning("Cannot read %s: %s", fpath, exc)
                continue
            claims = extract_claims(fpath, content)

            # Tier 3 cache: check before processing claims for this file.
            # A cache hit means all Tier 3 findings for this file are already known
            # from a prior run with the same content, profile, and clone SHA.
            _t3_cache_hit = False
            _file_t3_findings: list[dict] = []  # accumulates fresh Tier 3 results (miss path)
            if not no_llm and not no_tier3_cache:
                _t3_cache_hit, _cached_t3 = _t3_cache.get(fpath, content)
                if _t3_cache_hit:
                    raw_findings.extend(_cached_t3)
                    log.debug("Tier3Cache HIT: %s (%d findings)", fpath.name, len(_cached_t3))

            for claim in claims:
                # Tier 1
                tier1 = tier1_assess(claim, api_names, profile, family, platform)
                if tier1.status is Tier1Status.FINDING:
                    finding = tier1.finding
                    assert finding is not None
                    finding["id"] = make_finding_id(
                        family, platform, finding["type"],
                        claim["file"], claim["line"], claim["value"]
                    )
                    raw_findings.append(finding)
                    continue
                if tier1.status is Tier1Status.VERIFIED:
                    continue

                # Tier 2 (skipped when --no-embed or --no-llm: embedding endpoint required)
                if api_names and not _no_embed:
                    t2 = tier2_verify(claim, family, platform)
                    if t2:
                        verdict_t2, conf_t2 = t2
                        if verdict_t2 == "MATCH":
                            continue  # confirmed good
                        if conf_t2 >= TIER2_MATCH_HIGH:
                            # Confident mismatch
                            f = {
                                "type": "wrong-api-name",
                                "severity": "S",
                                "tier_resolved_by": 2,
                                "file": claim["file"],
                                "line": claim["line"],
                                "old_value": claim["value"],
                                "correct_value": None,
                                "description": f"Tier 2 vector: '{claim['value']}' not found in API surface",
                                "id": make_finding_id(family, platform, "wrong-api-name",
                                                      claim["file"], claim["line"], claim["value"]),
                            }
                            raw_findings.append(f)
                            continue
                        # Confidence < 0.70 → escalate to Tier 3

                # Tier 3 (skipped on cache hit — results already injected above)
                if not no_llm and not _t3_cache_hit and claim["type"] in ("api-token", "package-declaration"):
                    t3 = tier3_verify(claim, family, platform, clone_path)
                    if t3.status not in (EndpointStatus.OK,):
                        # LLM unavailable or skipped — flag as NEEDS_REVIEW (Tier 4)
                        raw_findings.append({
                            "id": make_finding_id(family, platform, "needs-review",
                                                  claim["file"], claim["line"], claim.get("value", "")),
                            "type": "needs-review",
                            "severity": "O",
                            "tier_resolved_by": 4,
                            "status": "needs_review",
                            "endpoint_status": t3.status.value,
                            "endpoint_used": t3.endpoint_used,
                            "file": claim["file"],
                            "line": claim["line"],
                            "old_value": claim["value"],
                            "correct_value": None,
                            "description": f"LLM {t3.status.value} ({t3.reason}) — manual review required for: {claim['value']}",
                        })
                    elif t3.verdict is not None:
                        # LLM found a real problem
                        finding = t3.verdict
                        finding["id"] = make_finding_id(
                            family, platform, finding["type"],
                            claim["file"], claim["line"], claim.get("value", "")
                        )
                        finding["endpoint_status"] = t3.status.value
                        finding["endpoint_used"] = t3.endpoint_used
                        raw_findings.append(finding)
                        _file_t3_findings.append(finding)  # accumulate for cache write
                    # else t3.verdict is None and status OK: LLM confirmed claim is accurate

            # Cache miss path: store Tier 3 findings for this file (empty list = all accurate)
            if not no_llm and not _t3_cache_hit and not no_tier3_cache:
                _t3_cache.put(fpath, content, _file_t3_findings)

    # Stage 7: Missing mandatory sections / pages
    raw_findings.extend(stage7_missing_sections(
        family, platform, content_files, profile, make_finding_id, repo_root=_REPO_ROOT
    ))

    log.info("Raw findings before merge: %d", len(raw_findings))

    # Stage 6: Merge with prior state
    merged_findings, delta = merge_findings(prior_state.get("findings", []), raw_findings)

    # Stage 6b: Suppress known false positives
    _fp_rules = _load_false_positives()
    _n_suppressed = _apply_false_positives(merged_findings, family, platform, _fp_rules)
    if _n_suppressed:
        log.warning("[SUPPRESSED] %d known false positive(s) suppressed at verdict time", _n_suppressed)

    # Stage 8: Verdict
    verdict = compute_verdict(merged_findings)
    log.info("Verdict: %s", verdict)

    # Tier 3 advisory summary (these findings do not affect the verdict)
    tier3_findings = [f for f in merged_findings if f.get("tier_resolved_by") == 3
                      and f.get("status") not in ("fixed", "wontfix", "suppressed")]
    if tier3_findings:
        log.info("Tier 3 advisory: %d findings (not blocking verdict)", len(tier3_findings))

    used_providers = [
        event.provider for event in _gaeval_metrics_events
        if getattr(event, "provider", None) and event.status == "success"
    ]
    if used_providers:
        llm_tier = used_providers[-1]

    # Delta section for report
    delta_section = build_delta_section(prior_state, clone_sha, merged_findings, delta, llm_tier)

    # Stage 9: Report
    report_md = generate_report(family, platform, merged_findings, verdict, delta_section, clone_sha, llm_tier)

    # Build output dict
    output = {
        "family": family,
        "platform": platform,
        "run_date": datetime.now(timezone.utc).isoformat(),
        "clone_sha": clone_sha,
        "verdict": verdict,
        "llm_tier_used": llm_tier,
        "scope": scope,
        "findings": merged_findings,
        "delta": delta,
        "tier3_advisory": {
            "count": len(tier3_findings),
            "note": "Tier 3 (LLM) findings are advisory only and do not affect the verdict.",
            "findings": tier3_findings,
        },
    }

    if not dry_run:
        md_path, json_path = _output_paths(family, platform, out_override)
        md_path.parent.mkdir(parents=True, exist_ok=True)
        md_path.write_text(report_md, encoding="utf-8")
        json_path.write_text(json.dumps(output, indent=2), encoding="utf-8")
        log.info("Report written to %s", md_path)
        log.info("Findings JSON written to %s", json_path)

        # Update state (include tier3_cache so it persists across runs)
        new_state = {
            "family": family,
            "platform": platform,
            "last_run_sha": clone_sha,
            "last_run_date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "verdict": verdict,
            "llm_tier_used": llm_tier,
            "findings": merged_findings,
            "tier3_cache": _t3_cache.export(),
        }
        save_state(new_state, family, platform, state_dir)

        # Stage 10: Profile self-update (write discovered_actuals if not already set)
        _update_profile_actuals(family, platform, profile, clone_sha)

    _try_write_gaeval_metrics(family, platform, _gaeval_run_id, _gaeval_metrics_events,
                              output.get("findings", []), output.get("verdict", "UNKNOWN"), t_start)
    return output


def _try_write_gaeval_metrics(
    family: str,
    platform: str,
    run_id,
    events: list,
    merged_findings: list,
    verdict: str,
    t_start: float,
) -> None:
    """Write metrics dry-run JSON for one run_gap_eval() call. Never raises."""
    if run_id is None:
        return
    try:
        import json as _json
        import time as _time
        from commands.ops.run_metrics import RunMetrics
        from commands.ops.metrics_schema import row_to_dict
        dry_dir = _REPO_ROOT / "reports" / "metrics" / "dry"
        dry_dir.mkdir(parents=True, exist_ok=True)
        dur_ms = max(0, int((_time.monotonic() - t_start) * 1000))
        disc = len(merged_findings) if merged_findings else 1
        successful_verdicts = {"PASS", "PUBLICATION READY"}
        succ = 1 if verdict in successful_verdicts else 0
        fail = 0 if verdict in successful_verdicts else 1
        with RunMetrics(
            run_id=run_id,
            agent_name="aspose-org-gap-evaluation",
            job_type="gap_evaluation",
            product=family,
            platform=platform,
            website="aspose.org",
            website_section="Docs",
            ledger_root=_REPO_ROOT / "reports" / "metrics" / "events",
        ) as rm:
            if events:
                rm.record_events(events)
            row = rm.to_row(
                items_discovered=disc,
                items_failed=fail,
                items_succeeded=succ,
                run_duration_ms=dur_ms,
            )
        dry_path = dry_dir / f"{run_id}.dry.json"
        dry_path.write_text(_json.dumps(row_to_dict(row), indent=2), encoding="utf-8")
        log.info("Metrics dry-run: %s", dry_path)
        # Slice 16: production submit if AGENT_METRICS_PRODUCTION=1
        from commands.ops.metrics_submitter import try_production_submit
        try_production_submit(row)
    except Exception as exc:
        log.debug("Metrics dry-run skipped: %s", exc)


def _update_profile_actuals(family: str, platform: str, profile: dict, clone_sha: str) -> None:
    """Write discovered_actuals back to profile YAML if they were empty."""
    path = _profile_path(family, platform)
    if not path.exists():
        return
    actuals = profile.get("discovered_actuals") or {}
    if actuals.get("last_baseline_sha") == clone_sha:
        return  # already current
    try:
        text = path.read_text(encoding="utf-8")
        text = re.sub(
            r"(last_baseline_sha:\s*)null",
            f"last_baseline_sha: {clone_sha}",
            text,
        )
        path.write_text(text, encoding="utf-8")
        log.debug("Profile updated with clone SHA %s", clone_sha[:8])
    except Exception as exc:
        log.debug("Profile self-update skipped: %s", exc)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="S-43 gap-eval: content verification against clone cache.")
    parser.add_argument("family", help="Product family (e.g. slides)")
    parser.add_argument("platform", help="Platform (e.g. java)")
    parser.add_argument("--scope", default="all",
                        choices=["all", "products", "docs", "blog", "kb", "reference"])
    parser.add_argument("--out", default=None, help="Override output path stem (no extension)")
    parser.add_argument("--state-dir", type=Path, default=None)
    parser.add_argument("--no-llm", action="store_true",
                        help="Skip Tier 3 LLM verification and Tier 2 embeddings (implies --no-embed). "
                             "Safe for offline/disconnected operation.")
    parser.add_argument("--no-embed", action="store_true",
                        help="Skip Tier 2 embedding-based vector search. "
                             "Use when embedding endpoints are unavailable. Implied by --no-llm.")
    parser.add_argument("--dry-run", action="store_true", help="Run without writing output files")
    parser.add_argument("--seed", type=int, default=42,
                        help="Random seed for deterministic Stage 2 sampling (default: 42)")
    parser.add_argument("--max-stage2-entries", type=int, default=0,
                        help="Stage 2 entries to check: 0=all (default), >0=sample N")
    parser.add_argument("--deterministic", action="store_true",
                        help="Fully reproducible run: exhaustive Stage 2, no LLM (Tier 1+2 only)")
    parser.add_argument("--no-tier3-cache", action="store_true",
                        help="Force fresh Tier 3 LLM calls, bypassing the per-file cache. "
                             "Use when suspecting stale cache results or testing Tier 3 directly.")
    parser.add_argument("--reset-state", action="store_true",
                        help="Delete the persisted state file for this family/platform before "
                             "running, so all findings start fresh with no prior history.")
    parser.add_argument("--reset-state-dry-run", action="store_true",
                        help="Print the state file path that --reset-state would delete "
                             "and exit without making any changes.")
    args = parser.parse_args()

    no_llm = args.no_llm
    no_embed = args.no_embed or no_llm  # --no-llm implies --no-embed
    max_stage2 = args.max_stage2_entries
    if args.deterministic:
        no_llm = True
        no_embed = True
        max_stage2 = 0

    if args.reset_state_dry_run:
        from state import _state_path  # type: ignore
        preview_path = _state_path(args.family, args.platform, state_dir=args.state_dir)
        print(f"Would delete state file: {preview_path}")
        sys.exit(0)

    if args.reset_state:
        from state import reset_state  # type: ignore
        from tier3_cache import clear_cache  # type: ignore
        log.warning(
            "--reset-state: permanently deleting finding history for %s/%s — "
            "this cannot be undone. Pass --reset-state-dry-run to preview.",
            args.family,
            args.platform,
        )
        cleared = clear_cache(args.family, args.platform, state_dir=args.state_dir)
        if cleared:
            log.info("--reset-state: Tier 3 cache cleared for %s/%s", args.family, args.platform)
        reset_state(args.family, args.platform, state_dir=args.state_dir)

    # Prerequisite check — clear error messages instead of cryptic tracebacks
    try:
        from core.prereqs import require_all
        require_all(args.family, args.platform, needs_clone_cache=True)
    except SystemExit:
        raise
    except Exception:
        pass  # prereqs is best-effort; run_gap_eval has its own checks

    try:
        result = run_gap_eval(
            args.family,
            args.platform,
            scope=args.scope,
            out_override=args.out,
            state_dir=args.state_dir,
            no_llm=no_llm,
            no_embed=no_embed,
            dry_run=args.dry_run,
            seed=args.seed,
            max_stage2_entries=max_stage2,
            no_tier3_cache=args.no_tier3_cache,
        )
        verdict = result.get("verdict", "UNKNOWN")
        n_findings = len(result.get("findings", []))
        log.info("Complete: %d findings, verdict=%s", n_findings, verdict)
        if verdict == "NOT PUBLISHABLE":
            sys.exit(2)  # Non-zero exit for CI integration
    except (FileNotFoundError, ValueError) as exc:
        log.error("%s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
