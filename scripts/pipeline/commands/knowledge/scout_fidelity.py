#!/usr/bin/env python3
"""scout_fidelity.py — Extraction Fidelity Gate (D-2, TC-MT040-41).

Problem this closes: AGENTS §7d gates knowledge quality by VOLUME
(class_count >= 5, total_claims >= 20, snippet_count >= 3) — a scout that
misses every abstract class, every doc comment, every format signal and
every curated example snippet passes that gate comfortably. Mission MT040's
own launch (the 3d/typescript scout, before TC-MT040-10/12 landed) is the
concrete proof: 142 classes / 2276 claims (well over the §7d thresholds)
while 0 of 8 real `export abstract class` declarations and 0 of 142 class
doc comments were captured. This module builds five cheap, language-adapted
probes that would have caught that gap BEFORE content generation, not after.

Probes (see each probe_p*() docstring for the exact algorithm):
    P1  Declaration census       — class-kind declarations in source vs
                                    api_surface.json entries of that kind.
    P2  Entry-point coverage     — the language adapter's export_surface()
                                    (barrel/`__all__`/`pub use`/...) vs
                                    api_surface.json names + reachable flags.
    P3  Doc-comment census       — declarations with a real source doc
                                    comment vs entries with a non-empty `doc`.
    P4  README/manifest format
        cross-check               — format tokens named in the README /
                                    package manifest "keywords" vs formats.json.
    P5  Snippet provenance       — collected-snippet distribution by source
                                    tier (README/examples/tests) vs whether a
                                    curated tier exists on disk.

Every probe is LANGUAGE-ADAPTED through extraction/lang/<language>.py
(export_surface, declaration_kinds, doc_anchor via
extraction.api_surface._extract_doc_comment) — none of the probes below hard-
code TypeScript; TypeScript is simply the platform with the fullest adapter
implementation today, exercised by this repo's own real gap.

THRESHOLDS ARE ADVISORY-ONLY (WARN, never FAIL) FOR EVERY PROBE, ON PURPOSE.
This is Decision 13 of the MT040 plan's D-2 section: "No probe may FAIL a
bootstrap until the fleet calibration run ... shows zero false positives for
that probe." `PROBE_FAIL_ENABLED` below is the single switch a human flips,
per probe, after reviewing `--calibrate`'s output
(reports/sprint/pdf-typescript-hardening/evidence/fidelity_calibration.json).
This module never flips its own switch. Each probe still computes and
reports `would_fail_if_enabled` so the calibration evidence is honest about
what WOULD have failed once a probe's threshold is turned on.

Outputs:
    knowledge/{family}/{platform}/scout/fidelity_report.json  (gitignored,
        same as the rest of scout/ — written by the single-product CLI path,
        never by --calibrate, which is read-only by design)
    A `fidelity_summary` block merged additively into an existing
        scout/scout_report.json, when one is already present.

Usage (library):
    from commands.knowledge.scout_fidelity import run_probes
    report = run_probes("pdf", "typescript")

Usage (CLI):
    .venv/Scripts/python scripts/pipeline/commands/knowledge/scout_fidelity.py pdf typescript
    .venv/Scripts/python scripts/pipeline/commands/knowledge/scout_fidelity.py pdf typescript --json
    .venv/Scripts/python scripts/pipeline/commands/knowledge/scout_fidelity.py --calibrate

Exit codes:
    0  overall_status in {OK, WARN, UNAVAILABLE} (advisory-only today, this
       is always the case)
    1  overall_status == FAIL (only possible once a probe's FAIL threshold
       is enabled in PROBE_FAIL_ENABLED — never happens today)
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Path guard — ensure extraction/ and core/ packages are importable
# regardless of cwd (same convention as commands/knowledge/scout.py and
# commands/diagnostics/typescript_api_completeness.py).
# ---------------------------------------------------------------------------

_HERE = Path(__file__).resolve().parent
_PIPELINE_DIR = _HERE.parent.parent  # commands/knowledge/ -> commands/ -> pipeline/
if str(_PIPELINE_DIR) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_DIR))

_DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[4]
_REPO_ROOT = _DEFAULT_REPO_ROOT


def configure(*, repo_root: "Path | str | None" = None) -> None:
    """Test seam: redirect repo-relative roots. Pass repo_root=None to reset
    to the real repo (module import time default)."""
    global _REPO_ROOT
    _REPO_ROOT = Path(repo_root) if repo_root is not None else _DEFAULT_REPO_ROOT


from core.clone_cache import clone_path  # noqa: E402
from extraction import lang  # noqa: E402
from extraction.api_surface import _extract_doc_comment  # noqa: E402
from extraction.format_signals import _KNOWN_FORMAT_TOKENS  # noqa: E402
from extraction.package_root import detect_package_root  # noqa: E402
from extraction.snippets import (  # noqa: E402
    _TIER1_EXAMPLE_DIR_NAMES,
    _TIER2_TEST_DIR_NAMES,
)
from extraction.tree_helpers import (  # noqa: E402
    PLATFORM_TO_LANG,
    _FILE_EXTENSIONS,
    _HEADER_EXTENSIONS,
    _collect_source_files,
    _node_name,
    collect_nodes,
    get_parser,
    is_public,
)

SCHEMA_VERSION = 1

# ---------------------------------------------------------------------------
# Advisory-only threshold switch (Decision 13). All False today — see module
# docstring. Flipping one of these to True is a human/mission-level decision
# made AFTER reviewing a zero-false-positive fleet calibration for that probe;
# this module never mutates this dict itself.
# ---------------------------------------------------------------------------
PROBE_FAIL_ENABLED: dict = {
    "P1": False,
    "P2": False,
    "P3": False,
    "P4": False,
    "P5": False,
}

# P3: minimum number of source-detected doc comments before a zero-capture
# result is treated as a meaningful finding at all. Reasoning (no exact value
# was specified for this per-finding threshold in the plan — the plan's own
# "N" is deliberately left to be picked with a stated reason): too low (e.g.
# 1) and a single doc comment sitting somewhere the current anchor logic
# doesn't reach (a real but narrow miss, not a systemic one) would read as a
# full "0 captured" alarm on nearly every small/early-stage product; too high
# (e.g. 50) and it would miss real, total capture failures on smaller
# products the way this exact case (3d/typescript, 142 documented-eligible
# declarations) does not need. 5 is small enough to catch a genuine total
# blind spot early while staying above "this product simply has one or two
# incidentally-commented declarations".
P3_MIN_SOURCE_DOC_COUNT = 5

_TIER1_NAMES_LOWER = {n.lower() for n in _TIER1_EXAMPLE_DIR_NAMES}
_TIER2_NAMES_LOWER = {n.lower() for n in _TIER2_TEST_DIR_NAMES}
_TIER0_README_BASENAMES = {"readme.md", "readme.rst"}

_README_LANG_ALIASES = {
    "typescript": {"typescript", "ts"},
    "javascript": {"javascript", "js"},
    "python": {"python", "py"},
    "rust": {"rust", "rs"},
    "go": {"go", "golang"},
    "java": {"java"},
    "csharp": {"csharp", "cs", "c#"},
    "cpp": {"cpp", "c++", "cxx"},
}


# ---------------------------------------------------------------------------
# Small result-shape helpers
# ---------------------------------------------------------------------------

def _status_for(would_fail: bool, probe_id: str) -> str:
    """OK when there is nothing to flag; otherwise WARN unless this probe's
    FAIL threshold has been explicitly enabled (never true today)."""
    if not would_fail:
        return "OK"
    return "FAIL" if PROBE_FAIL_ENABLED.get(probe_id) else "WARN"


def _unavailable(probe_id: str, reason: str, **details) -> dict:
    """The probe could not run at all (e.g. no clone cache, no language
    adapter) — distinct from a probe that ran and found nothing (OK) or ran
    and found something (WARN/FAIL). Never counts toward findings_count."""
    return {
        "probe": probe_id,
        "status": "UNAVAILABLE",
        "would_fail_if_enabled": False,
        "message": reason,
        "details": details,
    }


def _skip(probe_id: str, reason: str, **details) -> dict:
    """The probe is not applicable to this product/language at all (as
    opposed to merely unable to run right now)."""
    return {
        "probe": probe_id,
        "status": "SKIP",
        "would_fail_if_enabled": False,
        "message": reason,
        "details": details,
    }


# ---------------------------------------------------------------------------
# Knowledge-artifact loaders (merged/ preferred, scout/ fallback — same
# precedence as commands/diagnostics/typescript_api_completeness.py's
# load_api_surface_entries(), reimplemented locally rather than imported
# across an unrelated diagnostics module — the same "small duplicated helper
# by design" pattern content_eval/evaluators/_reachability.py already uses
# for its own small regex set).
# ---------------------------------------------------------------------------

def _knowledge_dir(family: str, platform: str) -> Path:
    return _REPO_ROOT / "knowledge" / family / platform


def _load_json(path: Path):
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def load_api_surface_entries(family: str, platform: str) -> "list[dict]":
    """Load raw api_surface.json entries (merged preferred, scout fallback)."""
    for sub in ("merged", "scout"):
        data = _load_json(_knowledge_dir(family, platform) / sub / "api_surface.json")
        if data is None:
            continue
        if isinstance(data, list):
            return [e for e in data if isinstance(e, dict)]
        if isinstance(data, dict):
            return [{"name": k, **(v if isinstance(v, dict) else {})} for k, v in data.items()]
    return []


def load_formats_entries(family: str, platform: str) -> "list[dict]":
    for sub in ("merged", "scout"):
        data = _load_json(_knowledge_dir(family, platform) / sub / "formats.json")
        if isinstance(data, list):
            return [e for e in data if isinstance(e, dict)]
    return []


def load_snippets_index(family: str, platform: str) -> "list[dict]":
    for sub in ("merged", "scout"):
        data = _load_json(_knowledge_dir(family, platform) / sub / "snippets" / "snippets_index.json")
        if isinstance(data, list):
            return [e for e in data if isinstance(e, dict)]
    return []


def _resolve_repo_and_pkg_root(family: str, platform: str):
    """Return (repo, pkg_root) or (None, None) — fail-safe when the clone
    cache doesn't hold this product (the normal case in an isolated worktree
    that never cloned any FOSS repos; every caller must, and does, guard on
    this via `.is_dir()` before trusting the result)."""
    repo = clone_path(family, platform)
    if not repo.is_dir():
        return None, None
    pkg_root = detect_package_root(repo, platform)
    return repo, pkg_root


# ---------------------------------------------------------------------------
# P1 — Declaration census
# ---------------------------------------------------------------------------

def probe_p1_declaration_census(
    family: str, platform: str, *, repo: "Path | None" = None, pkg_root: "Path | None" = None,
) -> dict:
    """Public/exported CLASS-KIND declarations (class/interface/enum/type-
    alias/abstract-class/struct/trait/... — whatever declaration_kinds()
    declares as this language's `class_types`) counted from source vs
    entries actually present in api_surface.json.

    Scoped to class_types only (not func_types) on purpose: api_surface.json
    records a class-level entry's `kind` as the LITERAL source node type
    (e.g. "abstract_class_declaration"), so source-node-type counts and
    api_surface `kind` counts are directly, 1:1 comparable. Function-shaped
    entries all collapse to the single kind "function" regardless of their
    source node type (function_declaration / arrow_function / method_
    definition / ...), so a per-kind census there would compare incomparable
    things. This exact class-kind scoping is what would have caught this
    mission's own real defect (TC-MT040-10 / G-TS-12: `abstract_class_
    declaration` absent from `_CLASS_TYPES["typescript"]`, so 3d/typescript's
    8 real abstract classes never appeared in api_surface.json under ANY
    kind) — see the module docstring. A coarse, name-diff-free function/
    method declaration COUNT is still reported under `details.functions` for
    context, but never contributes to `would_fail_if_enabled` (see its own
    comment below).
    """
    if repo is None or pkg_root is None:
        repo, pkg_root = _resolve_repo_and_pkg_root(family, platform)
    if repo is None:
        return _unavailable("P1", "clone cache not present for this product — cannot census source declarations")

    language = PLATFORM_TO_LANG.get(platform, platform)
    adapter = lang.get(language)
    if adapter is None:
        return _unavailable("P1", f"no extraction/lang/ adapter registered for language {language!r}")

    kinds = adapter.declaration_kinds()
    class_types = kinds.get("class_types") or set()
    func_types = kinds.get("func_types") or set()
    if not class_types:
        return _skip("P1", f"{language} declares no class-type declaration kinds")

    ext = _FILE_EXTENSIONS.get(language)
    if not ext:
        return _unavailable("P1", f"no source file extension mapping for language {language!r}")
    header_ext = _HEADER_EXTENSIONS.get(language, "")

    try:
        files = _collect_source_files(pkg_root, ext, header_ext)
    except OSError as exc:
        return _unavailable("P1", f"source collection failed: {exc}")

    parser = get_parser(language)
    source_by_kind: "dict[str, set[str]]" = {}
    func_source_count = 0
    for fpath in files:
        try:
            src = fpath.read_bytes()
        except OSError:
            continue
        tree = parser.parse(src)
        for node in collect_nodes(tree.root_node, class_types):
            if not is_public(node, language):
                continue
            name = _node_name(node, language)
            if not name:
                continue
            source_by_kind.setdefault(node.type, set()).add(name)
        if func_types:
            for node in collect_nodes(tree.root_node, func_types):
                if is_public(node, language):
                    func_source_count += 1

    entries = load_api_surface_entries(family, platform)
    api_names_all = {e.get("name") for e in entries if e.get("name")}
    api_by_kind: "dict[str, set[str]]" = {}
    for e in entries:
        k, n = e.get("kind"), e.get("name")
        if k in class_types and n:
            api_by_kind.setdefault(k, set()).add(n)
    api_func_count = sum(1 for e in entries if e.get("kind") == "function")
    for e in entries:
        api_func_count += sum(1 for m in (e.get("methods") or []) if isinstance(m, dict))

    per_kind: "dict[str, dict]" = {}
    missing_total = 0
    source_total = 0
    api_total = 0
    for kind, names in sorted(source_by_kind.items()):
        api_names_for_kind = api_by_kind.get(kind, set())
        missing = sorted(n for n in names if n not in api_names_all)
        kind_mismatch = sorted(n for n in names if n in api_names_all and n not in api_names_for_kind)
        per_kind[kind] = {
            "source_count": len(names),
            "api_count": len(api_names_for_kind),
            "missing_count": len(missing),
            "missing_names": missing[:50],
            "kind_mismatch_names": kind_mismatch[:50],
        }
        source_total += len(names)
        api_total += len(api_names_for_kind)
        missing_total += len(missing)

    ratio = round(api_total / source_total, 4) if source_total else None
    would_fail = missing_total > 0
    status = _status_for(would_fail, "P1")
    if would_fail:
        message = (
            f"{missing_total} public class-kind declaration(s) found in source "
            f"across {sum(1 for k in per_kind if per_kind[k]['missing_count'])} kind(s) "
            f"are entirely absent from api_surface.json"
        )
    else:
        message = f"all {source_total} public class-kind declaration(s) found in source are present in api_surface.json"

    return {
        "probe": "P1",
        "status": status,
        "would_fail_if_enabled": would_fail,
        "message": message,
        "details": {
            "language": language,
            "source_total": source_total,
            "api_total": api_total,
            "ratio": ratio,
            "per_kind": per_kind,
            "functions": {
                "source_count": func_source_count,
                "api_count": api_func_count,
                "note": "informational only (kind-collapsed on the api_surface side) — never contributes to would_fail_if_enabled",
            },
        },
    }


# ---------------------------------------------------------------------------
# P2 — Entry-point coverage
# ---------------------------------------------------------------------------

def probe_p2_entry_point_coverage(
    family: str, platform: str, *, repo: "Path | None" = None, pkg_root: "Path | None" = None,
) -> dict:
    """Names exported by the language's entry-point adapter
    (extraction/lang/<language>.py's export_surface()) should be a subset of
    api_surface.json's names; report missing names AND any
    reachable:false-but-exported inconsistency. Generalizes the barrel-
    completeness check TC-MT040-22 built TS-specifically
    (commands/diagnostics/typescript_api_completeness.py's
    compute_barrel_completeness()) to every language that has a real
    export_surface() implementation.

    Polarity note (csharp only): extraction/lang/csharp.py's export_surface()
    returns a CONFIRMED-INTERNAL denylist, not a positive reachable-name
    allowlist (csharp has no `__all__`/`pub use` equivalent — see
    extraction/lang/__init__.py's module docstring). Applying the generic
    "missing = names not in api_surface" check to that inverted set would be
    backwards, so csharp gets its own correctly-mirrored check: entries whose
    name IS in the confirmed-internal set but are NOT marked
    reachable:False.
    """
    if repo is None or pkg_root is None:
        repo, pkg_root = _resolve_repo_and_pkg_root(family, platform)
    if repo is None:
        return _unavailable("P2", "clone cache not present for this product — cannot resolve the entry-point/export surface")

    language = PLATFORM_TO_LANG.get(platform, platform)
    adapter = lang.get(language)
    if adapter is None or not hasattr(adapter, "export_surface"):
        return _unavailable("P2", f"no export_surface() adapter for language {language!r}")

    names, entry = adapter.export_surface(repo, pkg_root)
    if names is None:
        return _unavailable(
            "P2",
            "entry-point/export surface could not be positively resolved (adapter fail-safe — "
            "no unresolvable barrel/namespace-export is ever treated as a false positive)",
        )

    entries = load_api_surface_entries(family, platform)
    by_name = {e.get("name"): e for e in entries if e.get("name")}

    if language == "csharp":
        internal_names = set(names)
        inconsistent = sorted(n for n in internal_names if n in by_name and by_name[n].get("reachable") is not False)
        would_fail = bool(inconsistent)
        status = _status_for(would_fail, "P2")
        return {
            "probe": "P2",
            "status": status,
            "would_fail_if_enabled": would_fail,
            "message": (
                f"{len(inconsistent)} confirmed-internal name(s) are present in api_surface.json without reachable:false"
                if would_fail else
                f"all {len(internal_names)} confirmed-internal name(s) are correctly marked reachable:false (or absent)"
            ),
            "details": {
                "language": "csharp",
                "polarity": "internal_denylist",
                "entry_point": str(entry) if entry else None,
                "confirmed_internal_count": len(internal_names),
                "internal_but_not_marked_unreachable": inconsistent[:50],
                "internal_but_not_marked_unreachable_count": len(inconsistent),
            },
        }

    missing = sorted(n for n in names if n not in by_name)
    reachable_inconsistency = sorted(n for n in names if n in by_name and by_name[n].get("reachable") is False)
    would_fail = bool(missing) or bool(reachable_inconsistency)
    status = _status_for(would_fail, "P2")
    parts = []
    if missing:
        parts.append(f"{len(missing)} exported name(s) missing from api_surface.json entirely")
    if reachable_inconsistency:
        parts.append(f"{len(reachable_inconsistency)} exported name(s) present but marked reachable:false")
    message = "; ".join(parts) if parts else f"all {len(names)} exported name(s) are present and reachable"

    return {
        "probe": "P2",
        "status": status,
        "would_fail_if_enabled": would_fail,
        "message": message,
        "details": {
            "language": language,
            "polarity": "reachable_allowlist",
            "entry_point": str(entry) if entry else None,
            "export_count": len(names),
            "missing_from_api_surface": missing[:50],
            "missing_count": len(missing),
            "exported_but_marked_unreachable": reachable_inconsistency[:50],
            "exported_but_marked_unreachable_count": len(reachable_inconsistency),
        },
    }


# ---------------------------------------------------------------------------
# P3 — Doc-comment census
# ---------------------------------------------------------------------------

def probe_p3_doc_comment_census(
    family: str, platform: str, *, repo: "Path | None" = None, pkg_root: "Path | None" = None,
) -> dict:
    """Declarations preceded by a real doc comment in source vs entries with
    a non-empty `doc` field. Reuses extraction.api_surface._extract_doc_
    comment() directly — the exact function scout itself calls, including
    its TC-MT040-42 doc_anchor() redirection through extraction/lang/
    <language>.py — so this probe measures precisely what today's scout
    would (or, on stale knowledge, would have) captured, not a re-guessed
    approximation.

    A source with >= P3_MIN_SOURCE_DOC_COUNT real doc comments and ZERO
    captured in api_surface.json is a finding (see that constant's own
    comment for the threshold's reasoning).
    """
    if repo is None or pkg_root is None:
        repo, pkg_root = _resolve_repo_and_pkg_root(family, platform)
    if repo is None:
        return _unavailable("P3", "clone cache not present for this product — cannot census source doc comments")

    language = PLATFORM_TO_LANG.get(platform, platform)
    adapter = lang.get(language)
    kinds = adapter.declaration_kinds() if adapter is not None else {}
    class_types = kinds.get("class_types") or set()
    func_types = kinds.get("func_types") or set()
    decl_types = class_types | func_types
    if not decl_types:
        return _skip("P3", f"no declaration kinds known for language {language!r}")

    ext = _FILE_EXTENSIONS.get(language)
    if not ext:
        return _unavailable("P3", f"no source file extension mapping for language {language!r}")
    header_ext = _HEADER_EXTENSIONS.get(language, "")

    try:
        files = _collect_source_files(pkg_root, ext, header_ext)
    except OSError as exc:
        return _unavailable("P3", f"source collection failed: {exc}")

    parser = get_parser(language)
    source_total = 0
    source_doc_count = 0
    for fpath in files:
        try:
            src = fpath.read_bytes()
        except OSError:
            continue
        tree = parser.parse(src)
        for node in collect_nodes(tree.root_node, decl_types):
            if not is_public(node, language):
                continue
            source_total += 1
            try:
                doc = _extract_doc_comment(node, language)
            except Exception:
                doc = ""
            if doc:
                source_doc_count += 1

    entries = load_api_surface_entries(family, platform)
    api_total = 0
    api_doc_count = 0
    for e in entries:
        if e.get("kind") in class_types or e.get("kind") == "function":
            api_total += 1
            if e.get("doc"):
                api_doc_count += 1
        for m in (e.get("methods") or []):
            if isinstance(m, dict):
                api_total += 1
                if m.get("doc"):
                    api_doc_count += 1

    meaningful_sample = source_doc_count >= P3_MIN_SOURCE_DOC_COUNT
    would_fail = meaningful_sample and api_doc_count == 0
    status = _status_for(would_fail, "P3")
    ratio = round(api_doc_count / source_doc_count, 4) if source_doc_count else None

    if would_fail:
        message = f"{source_doc_count} source doc comment(s) found, 0 captured in api_surface.json (total capture failure)"
    elif source_doc_count == 0:
        message = "no source doc comments found for this product's public declarations"
    else:
        message = f"{api_doc_count}/{source_doc_count} source doc comment(s) captured in api_surface.json (ratio {ratio})"

    return {
        "probe": "P3",
        "status": status,
        "would_fail_if_enabled": would_fail,
        "message": message,
        "details": {
            "language": language,
            "source_total_declarations": source_total,
            "source_doc_count": source_doc_count,
            "api_total_declarations": api_total,
            "api_doc_count": api_doc_count,
            "ratio": ratio,
            "meaningful_sample_threshold": P3_MIN_SOURCE_DOC_COUNT,
        },
    }


# ---------------------------------------------------------------------------
# P4 — README/manifest format cross-check
# ---------------------------------------------------------------------------

_HEADING_RE = re.compile(r"^#{1,6}\s+(.+)$", re.MULTILINE)
_BULLET_RE = re.compile(r"^\s*[-*+]\s+(.+)$", re.MULTILINE)
_WORD_RE = re.compile(r"[A-Za-z0-9]+")


def _scan_readme_format_tokens(repo: Path) -> "set[str]":
    """Format tokens named in the README's headings and feature bullets."""
    tokens: set[str] = set()
    for name in ("README.md", "readme.md", "README.rst"):
        readme = repo / name
        if not readme.is_file():
            continue
        try:
            text = readme.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        lines = _HEADING_RE.findall(text) + _BULLET_RE.findall(text)
        for line in lines:
            for word in _WORD_RE.findall(line.lower()):
                if word in _KNOWN_FORMAT_TOKENS:
                    tokens.add(word)
        break
    return tokens


def _scan_manifest_keywords(repo: Path) -> "set[str]":
    """Format tokens named in package.json's "keywords" array, or the
    regex-extracted "keywords" array of pyproject.toml / Cargo.toml (a full
    TOML parse is not warranted for a single array field — this mirrors the
    cheap-probe posture the rest of D-2 takes)."""
    tokens: set[str] = set()

    pkg_json = repo / "package.json"
    if pkg_json.is_file():
        try:
            data = json.loads(pkg_json.read_text(encoding="utf-8", errors="replace"))
            for kw in data.get("keywords", []) or []:
                if isinstance(kw, str):
                    for word in _WORD_RE.findall(kw.lower()):
                        if word in _KNOWN_FORMAT_TOKENS:
                            tokens.add(word)
        except (json.JSONDecodeError, OSError):
            pass

    for toml_name in ("pyproject.toml", "Cargo.toml"):
        toml_path = repo / toml_name
        if not toml_path.is_file():
            continue
        try:
            text = toml_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        m = re.search(r"keywords\s*=\s*\[(.*?)\]", text, re.DOTALL)
        if not m:
            continue
        for kw in re.findall(r'"([^"]*)"|\'([^\']*)\'', m.group(1)):
            raw = (kw[0] or kw[1] or "").lower()
            for word in _WORD_RE.findall(raw):
                if word in _KNOWN_FORMAT_TOKENS:
                    tokens.add(word)

    return tokens


def probe_p4_readme_manifest_format_crosscheck(
    family: str, platform: str, *, repo: "Path | None" = None,
) -> dict:
    """Format tokens named in the product's README headings/feature bullets
    and package.json/pyproject.toml/Cargo.toml "keywords" vs formats.json.
    WARN-level with named misses — never FAIL, by design (unlike P1/P2/P3/
    P5, P4 has no `would_fail_if_enabled` escalation path at all: README
    wording is free text and varies far more than a structural declaration
    or export-surface signal, so this probe is deliberately permanent WARN-
    only advisory evidence, not a future FAIL candidate)."""
    if repo is None:
        repo, _pkg_root = _resolve_repo_and_pkg_root(family, platform)
    if repo is None:
        return _unavailable("P4", "clone cache not present for this product — cannot read README/manifest")

    readme_tokens = _scan_readme_format_tokens(repo)
    manifest_tokens = _scan_manifest_keywords(repo)
    named_tokens = readme_tokens | manifest_tokens

    formats_entries = load_formats_entries(family, platform)
    format_set = {str(e.get("format", "")).lower() for e in formats_entries if e.get("format")}

    named_misses = sorted(named_tokens - format_set)
    status = "WARN" if named_misses else "OK"
    message = (
        f"{len(named_misses)} format token(s) named in README/manifest but absent from formats.json: "
        + ", ".join(named_misses[:10])
        if named_misses else
        "every format token named in README/manifest is present in formats.json"
    )

    return {
        "probe": "P4",
        "status": status,
        "would_fail_if_enabled": False,
        "message": message,
        "details": {
            "readme_tokens": sorted(readme_tokens),
            "manifest_tokens": sorted(manifest_tokens),
            "formats_json_tokens": sorted(format_set),
            "named_misses": named_misses,
        },
    }


# ---------------------------------------------------------------------------
# P5 — Snippet provenance
# ---------------------------------------------------------------------------

def _classify_snippet_tier(entry: dict) -> str:
    src = str(entry.get("source_file", "")).replace("\\", "/").lower()
    fn = str(entry.get("source_function", ""))
    basename = src.rsplit("/", 1)[-1]
    if fn == "(readme_block)" or basename in _TIER0_README_BASENAMES:
        return "tier0_readme"
    parts = src.split("/")[:-1]
    if any(p in _TIER1_NAMES_LOWER for p in parts):
        return "tier1_examples"
    if any(p in _TIER2_NAMES_LOWER for p in parts):
        return "tier2_tests"
    return "other"


def _disk_has_example_files(repo: Path, language: str) -> bool:
    ext = _FILE_EXTENSIONS.get(language, "")
    if not ext:
        return False
    for name in _TIER1_EXAMPLE_DIR_NAMES:
        for candidate in (repo / name, repo / "src" / name):
            if candidate.is_dir():
                try:
                    if next(candidate.rglob(f"*{ext}"), None) is not None:
                        return True
                except OSError:
                    continue
    return False


def _disk_has_readme_fence(repo: Path, language: str) -> bool:
    lang_names = _README_LANG_ALIASES.get(language, {language})
    for name in ("README.md", "readme.md", "README.rst"):
        readme = repo / name
        if not readme.is_file():
            continue
        try:
            text = readme.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        fence_pattern = re.compile(
            r"```(" + "|".join(re.escape(n) for n in lang_names) + r")\s*\n", re.IGNORECASE)
        return fence_pattern.search(text) is not None
    return False


def probe_p5_snippet_provenance(family: str, platform: str, *, repo: "Path | None" = None) -> dict:
    """Distribution of collected snippets by source tier (tier0 README,
    tier1 curated examples/samples, tier2 tests — the tiers TC-MT040-44's
    deterministic tiered snippet budget, extraction/snippets.py, actually
    implements). A FAIL-shaped finding when a curated example/README tier
    exists in the repo (on disk) but contributed ZERO snippets — the real,
    verified 3d/typescript shape (100/100 snippets from tests/, 0 from
    examples/) this probe exists to catch.

    When the clone cache is unavailable, this probe still runs on the
    tracked snippets_index.json alone and reports a softer, `confidence:
    "index_only"` WARN (never would_fail_if_enabled — that flag is reserved
    for a CONFIRMED on-disk mismatch) when the index shows 100% test-tier
    with zero README/example representation at all.
    """
    snippets = load_snippets_index(family, platform)
    if not snippets:
        return _skip("P5", "no snippets_index.json found (or empty) for this product")

    dist = Counter(_classify_snippet_tier(e) for e in snippets)
    total = len(snippets)
    language = PLATFORM_TO_LANG.get(platform, platform)

    if repo is None:
        repo, _pkg_root = _resolve_repo_and_pkg_root(family, platform)

    if repo is not None:
        has_examples = _disk_has_example_files(repo, language)
        has_readme_fence = _disk_has_readme_fence(repo, language)
        findings = []
        if has_examples and dist.get("tier1_examples", 0) == 0:
            findings.append("a curated examples/samples directory with source files exists on disk but contributed 0 snippets")
        if has_readme_fence and dist.get("tier0_readme", 0) == 0:
            findings.append(f"README contains a fenced {language} code block but contributed 0 snippets")
        would_fail = bool(findings)
        status = _status_for(would_fail, "P5")
        return {
            "probe": "P5",
            "status": status,
            "would_fail_if_enabled": would_fail,
            "message": "; ".join(findings) if findings else f"snippet tier distribution matches disk contents ({dict(dist)})",
            "details": {
                "language": language,
                "confidence": "disk_confirmed",
                "total_snippets": total,
                "tier_distribution": dict(dist),
                "disk_has_examples_dir": has_examples,
                "disk_has_readme_fence": has_readme_fence,
                "findings": findings,
            },
        }

    # No clone cache: a softer, index-only signal.
    suspicious = (
        total > 0
        and dist.get("tier1_examples", 0) == 0
        and dist.get("tier0_readme", 0) == 0
        and dist.get("tier2_tests", 0) == total
    )
    status = "WARN" if suspicious else "OK"
    message = (
        "all collected snippets come from tests/ with zero README or examples representation "
        "(index-only signal — clone cache unavailable in this environment to confirm whether "
        "curated sources exist on disk; re-run with the clone cache present for a confirmed finding)"
        if suspicious else
        f"snippet tier distribution: {dict(dist)} (index-only — clone cache unavailable to cross-check disk contents)"
    )
    return {
        "probe": "P5",
        "status": status,
        "would_fail_if_enabled": False,
        "message": message,
        "details": {
            "language": language,
            "confidence": "index_only",
            "total_snippets": total,
            "tier_distribution": dict(dist),
        },
    }


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

_PROBE_IDS = ("P1", "P2", "P3", "P4", "P5")


def run_probes(family: str, platform: str, *, repo_root: "Path | str | None" = None) -> dict:
    """Run all five probes for one product and return the fidelity report
    dict (schema documented in the module docstring)."""
    if repo_root is not None:
        configure(repo_root=repo_root)

    repo, pkg_root = _resolve_repo_and_pkg_root(family, platform)
    probes = {
        "P1": probe_p1_declaration_census(family, platform, repo=repo, pkg_root=pkg_root),
        "P2": probe_p2_entry_point_coverage(family, platform, repo=repo, pkg_root=pkg_root),
        "P3": probe_p3_doc_comment_census(family, platform, repo=repo, pkg_root=pkg_root),
        "P4": probe_p4_readme_manifest_format_crosscheck(family, platform, repo=repo),
        "P5": probe_p5_snippet_provenance(family, platform, repo=repo),
    }
    findings_count = sum(1 for p in probes.values() if p["status"] in ("WARN", "FAIL"))
    fail_count = sum(1 for p in probes.values() if p["status"] == "FAIL")
    overall_status = "FAIL" if fail_count else ("WARN" if findings_count else "OK")

    return {
        "schema_version": SCHEMA_VERSION,
        "family": family,
        "platform": platform,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "clone_available": repo is not None,
        "probes": probes,
        "findings_count": findings_count,
        "fail_count": fail_count,
        "overall_status": overall_status,
    }


def write_fidelity_report(report: dict, family: str, platform: str, *, repo_root: "Path | str | None" = None) -> Path:
    """Write knowledge/{family}/{platform}/scout/fidelity_report.json.
    scout/ is gitignored (/knowledge/*/*/scout/), same as every other scout-
    phase intermediate artifact — this never touches tracked content."""
    root = Path(repo_root) if repo_root is not None else _REPO_ROOT
    out_dir = root / "knowledge" / family / platform / "scout"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "fidelity_report.json"
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return out_path


def update_scout_report_summary(family: str, platform: str, report: dict, *, repo_root: "Path | str | None" = None) -> bool:
    """Merge a small `fidelity_summary` block additively into an existing
    scout/scout_report.json (written by extraction/outputs.py's write_
    outputs() during a normal scout run). Returns False (no-op) when no
    scout_report.json exists yet — this never creates that file itself."""
    root = Path(repo_root) if repo_root is not None else _REPO_ROOT
    scout_report_path = root / "knowledge" / family / platform / "scout" / "scout_report.json"
    if not scout_report_path.is_file():
        return False
    try:
        data = json.loads(scout_report_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    if not isinstance(data, dict):
        return False
    data["fidelity_summary"] = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": report["generated_at"],
        "overall_status": report["overall_status"],
        "findings_count": report["findings_count"],
        "fail_count": report["fail_count"],
        "probe_statuses": {pid: p["status"] for pid, p in report["probes"].items()},
    }
    scout_report_path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return True


# ---------------------------------------------------------------------------
# Fleet calibration (--calibrate) — READ-ONLY: runs the probes over every
# registered product's EXISTING knowledge/ output and clone cache (where
# present); never writes fidelity_report.json or a scout_report.json summary
# for any of them. Only the single aggregate evidence file is written.
# ---------------------------------------------------------------------------

_DEFAULT_CALIBRATION_OUTPUT = Path("reports") / "sprint" / "pdf-typescript-hardening" / "evidence" / "fidelity_calibration.json"


def run_calibration(
    *,
    products_file: "Path | None" = None,
    output_path: "Path | None" = None,
    repo_root: "Path | str | None" = None,
) -> dict:
    root = Path(repo_root) if repo_root is not None else _REPO_ROOT
    products_path = products_file or (root / "data" / "products.json")
    products = json.loads(products_path.read_text(encoding="utf-8"))

    probe_status_totals = {pid: Counter() for pid in _PROBE_IDS}
    would_fail_totals = {pid: 0 for pid in _PROBE_IDS}
    per_product = []
    clone_available_count = 0

    for entry in products:
        family = entry.get("family")
        platform = entry.get("platform")
        if not family or not platform:
            continue
        report = run_probes(family, platform, repo_root=root)
        if report["clone_available"]:
            clone_available_count += 1
        per_product.append(report)
        for pid, p in report["probes"].items():
            probe_status_totals[pid][p["status"]] += 1
            if p.get("would_fail_if_enabled"):
                would_fail_totals[pid] += 1

    calibration = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "product_count": len(per_product),
        "clone_cache_available_count": clone_available_count,
        "probe_status_distribution": {pid: dict(counter) for pid, counter in probe_status_totals.items()},
        "probe_would_fail_if_enabled_count": would_fail_totals,
        "products": [
            {
                "family": r["family"],
                "platform": r["platform"],
                "clone_available": r["clone_available"],
                "overall_status": r["overall_status"],
                "findings_count": r["findings_count"],
                "probe_statuses": {pid: p["status"] for pid, p in r["probes"].items()},
                "probe_messages": {pid: p["message"] for pid, p in r["probes"].items()},
            }
            for r in per_product
        ],
    }

    out_path = Path(output_path) if output_path is not None else (root / _DEFAULT_CALIBRATION_OUTPUT)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(calibration, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    calibration["_written_to"] = str(out_path)
    return calibration


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _print_report(report: dict) -> None:
    print(f"\n# Extraction Fidelity Report — {report['family']}/{report['platform']}")
    print(f"Overall: {report['overall_status']}  (findings={report['findings_count']}, clone_available={report['clone_available']})")
    for pid in _PROBE_IDS:
        p = report["probes"][pid]
        print(f"  {pid} [{p['status']:<11}] {p['message']}")


def _print_calibration_summary(result: dict) -> None:
    print(f"\n# Fleet Fidelity Calibration ({result['product_count']} products, "
          f"{result['clone_cache_available_count']} with a clone cache present)")
    for pid in _PROBE_IDS:
        dist = result["probe_status_distribution"].get(pid, {})
        would_fail = result["probe_would_fail_if_enabled_count"].get(pid, 0)
        print(f"  {pid}: {dist}  would_fail_if_enabled={would_fail}")
    print(f"\nWritten to: {result.get('_written_to')}")


def main(argv: "list[str] | None" = None) -> int:
    parser = argparse.ArgumentParser(description="Extraction Fidelity Gate probes (D-2, TC-MT040-41)")
    parser.add_argument("family", nargs="?", help="Product family (e.g. pdf)")
    parser.add_argument("platform", nargs="?", help="Platform (e.g. typescript)")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    parser.add_argument("--calibrate", action="store_true",
                         help="Read-only: run all probes over every product in data/products.json "
                              "and write the fleet calibration evidence file")
    parser.add_argument("--products-file", type=Path, default=None,
                         help="Override data/products.json path (--calibrate only)")
    parser.add_argument("--output", type=Path, default=None,
                         help="Override the calibration output path (--calibrate only)")
    parser.add_argument("--no-update-scout-report", action="store_true",
                         help="Do not merge a fidelity_summary block into an existing scout_report.json")
    parser.add_argument("--no-write-report", action="store_true",
                         help="Do not write knowledge/{family}/{platform}/scout/fidelity_report.json -- "
                              "compute and print/return the report only. Used by readiness_gate.py's G-08 "
                              "(a status CHECK should not have the side effect of writing into knowledge/ "
                              "every time it runs; the S-54 knowledge-bootstrap path omits this flag so the "
                              "real fidelity_report.json is written as part of the normal scout pipeline).")
    parser.add_argument("--repo-root", type=Path, default=None, help="Override repo root (test seam)")
    args = parser.parse_args(argv)

    if args.repo_root:
        configure(repo_root=args.repo_root)

    if args.calibrate:
        result = run_calibration(products_file=args.products_file, output_path=args.output)
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            _print_calibration_summary(result)
        return 0

    if not args.family or not args.platform:
        parser.error("family and platform are required unless --calibrate is given")

    report = run_probes(args.family, args.platform)
    if not args.no_write_report:
        write_fidelity_report(report, args.family, args.platform)
    if not args.no_update_scout_report:
        update_scout_report_summary(args.family, args.platform, report)

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        _print_report(report)

    return 1 if report["overall_status"] == "FAIL" else 0


if __name__ == "__main__":
    sys.exit(main())
