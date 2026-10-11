"""propagation_analyzer.py -- unrefreshed-product capability analysis and discovery ranking (MT074 card B16).

CONTRACT: scripts/pipeline/lib/propagation_analyzer.py
  purpose: For a product whose KNOWLEDGE IS NOT REFRESHED (knowledge sha != upstream head, or no
           content was ever propagated) answer, read-only and without refreshing anything:
             (L2) which capability units did upstream ADD since the product's baseline,
             (L3) is each unit already present in the product's ENGLISH aspose.org content, per
                  surface (reference, docs, kb, blog, products),
             (L4) how do products rank against each other (deterministic).
           Used by Wave E discovery (AC-3) and by B4's blind calibration.
  baseline (analyze_product):
           explicit base_ref  >  state record `content_propagated_sha`  >  the knowledge sha in
           knowledge/<family>/<platform>/merged/model.yaml, flagged `baseline.assumed = true`
           (criterion 1a: UNRECORDED products -- the content-presence scan is the arbiter).
           With `bundles=(old_dir, new_dir)` the delta comes from two knowledge bundles instead
           (the pilot product is analysed this way) and no repository is needed.
  head:    explicit head_ref > the clone's remote-tracking head (refs/remotes/origin/HEAD) > HEAD,
           resolved READ-ONLY (`git rev-parse`), recorded as `head.source`.
  reachability: the baseline is made reachable ONLY through core.clone_cache's tri-state
           probe_baseline_reachability_at (injectable seam `ensure_reachable`, returning
           reachable | orphaned | unknown; a legacy bool seam maps True/False to reachable/orphaned).
           UNKNOWN (network, lock, timeout, fetch cap) => `status: BASELINE_UNVERIFIABLE`: never an
           orphan, never OK. Only a REACHABLE verdict proceeds; only ORPHANED yields ORPHANED_BASELINE.
           Unreachable =>
           result `status: ORPHANED_BASELINE` -- never a crash, never a guess. This module never
           checks anything out, never writes inside a clone's working tree, never writes the
           propagation state file.
  ground truth: GT-1 (compiled-API adapter) gives symbol-level units; GT-2 (file-level) gives NO
           symbols, so capability units are unavailable and the analysis carries `file_hints`
           instead: the stems of ADDED API-path source files. Hints are weaker evidence (recorded
           as such; lowercase stems only match inside code spans to avoid dictionary-word false
           presence) and an adapter card is the way to raise the tier. `KNOWLEDGE` = symbol-level
           units derived from two knowledge bundles (extractor output, not compiled truth).
  L3 scan: ENGLISH content only -- locale-suffixed files (`x.fr.md`, `index.zh.md`) and top-level
           locale directories are excluded; YAML/TOML frontmatter is stripped first (evidence
           `apis`/`claims` are internal metadata and never count as presence). Terms: type simple
           names, format names, and member / enum-constant names (a member only counts when its
           owner type is also named in the same file). Case-sensitive match on whole identifiers;
           qualified-name hits are recorded separately. Capability keywords (informative title
           tokens) are reported per surface but never decide `content_gap`.
  criteria: every threshold is data (DEFAULT_CRITERIA, or YAML via load_criteria(path); the file
           config/discovery_criteria.yaml is owned by the coordinator). Code names no product,
           family, language or format.
  determinism: every list is sorted; wall-clock / machine values live only under `volatile`.

Usage::

    import propagation_analyzer as pa
    result = pa.analyze_product("<family>", "<platform>", repo_path=clone, content_root=content,
                                state_reader=cps.read_state)
    ev = pa.evaluate_candidate(result, pa.load_criteria())
    ranked = pa.rank_candidates([result, ...], pa.load_criteria())
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any, Callable, Iterable

_LIB_DIR = Path(__file__).resolve().parent
_PIPELINE_DIR = _LIB_DIR.parent
for _p in (str(_LIB_DIR), str(_PIPELINE_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import yaml  # noqa: E402

import availability as _av  # noqa: E402
import capability_delta as cd  # noqa: E402
import language_adapters as la  # noqa: E402

SCHEMA_VERSION = 1
ANALYSIS_KIND = "propagation_analysis"
CANDIDATES_KIND = "propagation_candidates"
SURFACES = cd.SURFACES
ACTION_RANK = {"none": 0, "mention": 1, "update": 2, "create": 3}

STATUS_OK = "OK"
STATUS_ORPHANED = "ORPHANED_BASELINE"
STATUS_NO_BASELINE = "NO_BASELINE"
STATUS_UNVERIFIABLE = "BASELINE_UNVERIFIABLE"
STATUS_ERROR = "ERROR"
STATUS_DEFERRED = "DEFERRED"

TIER_KNOWLEDGE = "KNOWLEDGE"

_REPO_ROOT = _PIPELINE_DIR.parent.parent

# ── criteria ─────────────────────────────────────────────────────────────────────────────────────

DEFAULT_LOCALE_CODES = (
    "ar", "bg", "ca", "cs", "da", "de", "el", "es", "fa", "fi", "fr", "he", "hi", "hr", "hu", "id", "it", "ja",
    "ko", "lt", "lv", "ms", "nl", "no", "pl", "pt", "ro", "ru", "sk", "sl", "sr", "sv", "th", "tr", "uk", "vi", "zh",
)

DEFAULT_CRITERIA: "dict[str, Any]" = {
    "schema_version": 1,
    "drift": {
        # criterion 1: not PROPAGATED AND (new published release OR API-touching main)
        # `unknown` is included: about half of a fleet has no usable release evidence (registry entry without a
        # release sha, unsupported registry type, unpublished); such a product is still a candidate when main
        # touches the API, it just ranks below every unreleased_main candidate (ranking.release_state_order).
        "main_release_states": ["unreleased_main", "unknown"],
        "require_api_touched_for_main": True,
    },
    "worth_mentioning": {
        # criterion 2: >= min_units units whose placement is >= min_action on any of `surfaces`
        "surfaces": ["docs", "kb", "blog", "products"],
        "min_action": "mention",
        "min_units": 1,
    },
    "content_gap": {
        # criterion 3: coverage = share of the unit's NEW public types (all new symbols when it has none) named
        # in the English content of ANY gap surface (union). A unit is a gap when that share is strictly
        # below max_coverage_ratio; it is covered only when a substantial share is present.
        "gap_surfaces": ["docs", "kb", "blog", "products"],
        "max_coverage_ratio": 0.5,
        "min_gap_units": 1,
    },
    "analysable": {
        # criterion 4: ground-truth tier must be one of these (never skipped for lack of an adapter)
        "tiers": ["GT-1", "GT-2", TIER_KNOWLEDGE],
    },
    "gt2": {
        # GT-2 carries no symbols: this many ADDED API-path source files stand in for "a unit"
        "min_added_api_files": 1,
    },
    "scan": {
        "extensions": [".md", ".mdx", ".html"],
        "min_term_length": 3,
        "keyword_min_length": 4,
        "max_keywords_per_unit": 12,
        "max_files_per_surface": 5,
        "locale_codes": list(DEFAULT_LOCALE_CODES),
        "surface_paths": {
            "reference": ["reference.aspose.org/en/{family}/{platform}"],
            "docs": ["docs.aspose.org/en/{family}/{platform}"],
            "kb": ["kb.aspose.org/en/{family}/{platform}"],
            "blog": ["blog.aspose.org/{family}/{platform}"],
            "products": ["products.aspose.org/en/{family}/{platform}"],
        },
    },
    "ranking": {
        # sort keys, most significant first; must be a permutation of RANK_KEYS
        "order": ["release_triggered", "api_touched", "release_state", "gap_units", "product"],
        # position = priority of a candidate's release_state (a state not listed ranks last)
        "release_state_order": ["unreleased_main", "unknown"],
    },
    "output": {
        "max_absent_symbols": 25,
    },
}

RANK_KEYS = ("release_triggered", "api_touched", "release_state", "gap_units", "product")
RELEASE_STATES = ("released", "unreleased_main", "unknown")

_SCHEMA: "dict[str, Any]" = {
    "schema_version": int,
    "drift": {"main_release_states": list, "require_api_touched_for_main": bool},
    "worth_mentioning": {"surfaces": list, "min_action": str, "min_units": int},
    "content_gap": {"gap_surfaces": list, "max_coverage_ratio": (int, float), "min_gap_units": int},
    "analysable": {"tiers": list},
    "gt2": {"min_added_api_files": int},
    "scan": {"extensions": list, "min_term_length": int, "keyword_min_length": int, "max_keywords_per_unit": int,
             "max_files_per_surface": int, "locale_codes": list, "surface_paths": dict},
    "ranking": {"order": list, "release_state_order": list},
    "output": {"max_absent_symbols": int},
}


class CriteriaError(ValueError):
    """The criteria YAML has an unknown key, a wrong type, or an out-of-range value."""


def _validate(node: Any, schema: Any, where: str, errors: "list[str]") -> None:
    if isinstance(schema, dict):
        if not isinstance(node, dict):
            errors.append(f"{where or '<root>'}: expected a mapping")
            return
        for key in sorted(set(node) - set(schema)):
            errors.append(f"{where + '.' if where else ''}{key}: unknown key")
        for key in sorted(set(node) & set(schema)):
            _validate(node[key], schema[key], f"{where + '.' if where else ''}{key}", errors)
        return
    expected = schema if isinstance(schema, tuple) else (schema,)
    ok = isinstance(node, expected) and not (isinstance(node, bool) and bool not in expected)
    if not ok:
        errors.append(f"{where}: expected {'/'.join(t.__name__ for t in expected)}, got {type(node).__name__}")


def _deep_merge(base: "dict[str, Any]", over: "dict[str, Any]") -> "dict[str, Any]":
    out = copy.deepcopy(base)
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict) and k != "surface_paths":
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def validate_criteria(criteria: "dict[str, Any]") -> "list[str]":
    """Sorted list of schema / range problems ([] = valid)."""
    errors: "list[str]" = []
    _validate(criteria, _SCHEMA, "", errors)
    if errors:
        return sorted(errors)
    if criteria.get("schema_version") != 1:
        errors.append(f"schema_version must be 1, got {criteria.get('schema_version')!r}")
    wm = criteria["worth_mentioning"]
    if wm["min_action"] not in ACTION_RANK or wm["min_action"] == "none":
        errors.append(f"worth_mentioning.min_action must be one of mention|update|create, got {wm['min_action']!r}")
    for s in wm["surfaces"]:
        if s not in SURFACES:
            errors.append(f"worth_mentioning.surfaces: unknown surface {s!r}")
    for s in criteria["content_gap"]["gap_surfaces"]:
        if s not in SURFACES:
            errors.append(f"content_gap.gap_surfaces: unknown surface {s!r}")
    if not 0 < float(criteria["content_gap"]["max_coverage_ratio"]) <= 1:
        errors.append("content_gap.max_coverage_ratio must be within (0, 1]")
    for s in criteria["drift"]["main_release_states"]:
        if s not in RELEASE_STATES:
            errors.append(f"drift.main_release_states: unknown release state {s!r}")
    rk = criteria["ranking"]
    if sorted(map(str, rk["order"])) != sorted(RANK_KEYS):
        errors.append(f"ranking.order must be a permutation of {list(RANK_KEYS)}")
    for s in rk["release_state_order"]:
        if s not in RELEASE_STATES:
            errors.append(f"ranking.release_state_order: unknown release state {s!r}")
    if len(set(map(str, rk["release_state_order"]))) != len(rk["release_state_order"]):
        errors.append("ranking.release_state_order: duplicate state")
    for key in ("min_units",):
        if wm[key] < 1:
            errors.append(f"worth_mentioning.{key} must be >= 1")
    if criteria["content_gap"]["min_gap_units"] < 1:
        errors.append("content_gap.min_gap_units must be >= 1")
    if criteria["gt2"]["min_added_api_files"] < 1:
        errors.append("gt2.min_added_api_files must be >= 1")
    for s in sorted(set(criteria["scan"]["surface_paths"]) - set(SURFACES)):
        errors.append(f"scan.surface_paths: unknown surface {s!r}")
    for s, tpls in criteria["scan"]["surface_paths"].items():
        if not isinstance(tpls, list) or not all(isinstance(t, str) for t in tpls):
            errors.append(f"scan.surface_paths.{s}: expected a list of path templates")
    return sorted(errors)


def load_criteria(path: "Path | str | None" = None) -> "dict[str, Any]":
    """DEFAULT_CRITERIA, overlaid with the YAML at `path` when given (a missing file is an error;
    callers that treat the file as optional pass None). Unknown keys / wrong types raise
    CriteriaError listing every problem."""
    crit = copy.deepcopy(DEFAULT_CRITERIA)
    if path is not None:
        p = Path(path)
        try:
            raw = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        except (OSError, yaml.YAMLError) as exc:
            raise CriteriaError(f"cannot read criteria {p}: {exc}") from exc
        errors: "list[str]" = []
        _validate(raw, _SCHEMA, "", errors)
        if errors:
            raise CriteriaError(f"{p}: " + "; ".join(sorted(errors)))
        crit = _deep_merge(crit, raw)
    problems = validate_criteria(crit)
    if problems:
        raise CriteriaError("; ".join(problems))
    return crit


def criteria_digest(criteria: "dict[str, Any]") -> str:
    return hashlib.sha256(json.dumps(criteria, sort_keys=True, default=str).encode("utf-8")).hexdigest()


# ── model / versions ─────────────────────────────────────────────────────────────────────────────

def read_model_fields(model_path: "Path | str") -> "dict[str, Any]":
    """{exists, repo_sha, version} from a model.yaml (top-level line scan: model files are large)."""
    p = Path(model_path)
    out: "dict[str, Any]" = {"exists": p.is_file(), "repo_sha": None, "version": None}
    if not out["exists"]:
        return out
    try:
        for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
            for key in ("repo_sha", "version"):
                if line.startswith(key + ":") and out[key] is None:
                    value = line.split(":", 1)[1].strip().strip("'\"")
                    out[key] = value or None
    except OSError:
        pass
    return out


def version_key(version: "str | None") -> "tuple[int, ...] | None":
    """Numeric release tuple of a version string ('v1.2.3-rc1' -> (1, 2, 3)); None when it has no digits."""
    if not version:
        return None
    core = re.split(r"[-+ ]", str(version).strip().lstrip("vV"), maxsplit=1)[0]
    parts = re.findall(r"\d+", core)
    return tuple(int(x) for x in parts) if parts else None


def compute_new_release(published_version: "str | None", baseline_version: "str | None") -> "bool | None":
    """True iff the published version is strictly newer than the baseline's; None when either is unknown."""
    a, b = version_key(published_version), version_key(baseline_version)
    if a is None or b is None:
        return None
    width = max(len(a), len(b))
    return (a + (0,) * (width - len(a))) > (b + (0,) * (width - len(b)))


# ── git (read-only) ──────────────────────────────────────────────────────────────────────────────

def _git(runner: Callable[..., Any], repo: "Path | str", *args: str) -> Any:
    return runner(["git", "-C", str(repo), *args])


def _rev(runner: Callable[..., Any], repo: "Path | str", ref: str) -> "str | None":
    res = _git(runner, repo, "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}")
    out = (getattr(res, "stdout", "") or "").strip()
    return out if res.returncode == 0 and out else None


def resolve_head(repo_path: "Path | str", runner: Callable[..., Any]) -> "tuple[str | None, str]":
    """(sha, source). The clone's remote-tracking head first, then HEAD. Read-only."""
    for ref in ("refs/remotes/origin/HEAD", "HEAD"):
        sha = _rev(runner, repo_path, ref)
        if sha:
            return sha, ref
    return None, "unresolved"


REACHABLE = "reachable"
ORPHANED = "orphaned"
UNKNOWN = "unknown"


def default_ensure_reachable(repo_path: "Path | str", sha: str) -> str:
    """Seam default: core.clone_cache.probe_baseline_reachability_at (the ONLY sanctioned deepening path).
    Returns the tri-state verdict: reachable | orphaned | unknown."""
    from core.clone_cache import probe_baseline_reachability_at  # noqa: PLC0415 -- lazy: keeps the lib importable

    return str(probe_baseline_reachability_at(repo_path, sha))


def normalize_reachability(verdict: Any) -> str:
    """A seam result as reachable | orphaned | unknown. The tri-state strings pass through; a legacy bool
    seam maps True -> reachable and False -> orphaned (the caller asserted a definitive answer); anything
    else is `unknown` -- an unrecognised answer must never be read as an orphan or as success."""
    if isinstance(verdict, bool):
        return REACHABLE if verdict else ORPHANED
    if isinstance(verdict, str) and verdict.lower() in (REACHABLE, ORPHANED, UNKNOWN):
        return verdict.lower()
    return UNKNOWN


class RecordedAdapter(la.LanguageAdapter):
    """Adapter that replays a recorded api_delta result (offline fixtures); never touches git."""

    def __init__(self, result: "dict[str, Any]"):
        self._result = copy.deepcopy(result)
        self.ground_truth_tier = str(result.get("ground_truth_tier") or la.GT2)

    def api_delta(self, old_ref, new_ref, *, repo_path, runner):  # noqa: ARG002 -- contract signature
        return copy.deepcopy(self._result)


# ── knowledge bundles ────────────────────────────────────────────────────────────────────────────

def _read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _hidden(entry: "dict[str, Any]") -> bool:
    return str(entry.get("visibility") or "").casefold() in ("private", "internal")


def load_api_surface(bundle_dir: "Path | str") -> "list[dict[str, Any]]":
    data = _read_json(Path(bundle_dir) / "api_surface.json", [])
    return [e for e in data if isinstance(e, dict) and "name" in e] if isinstance(data, list) else []


def _format_names(bundle_dir: Path) -> "dict[str, str]":
    out: "dict[str, str]" = {}
    data = _read_json(bundle_dir / "formats.json", [])
    for e in data if isinstance(data, list) else []:
        if not isinstance(e, dict):
            continue
        name = str(e.get("format") or e.get("name") or "").strip()
        if name and str(e.get("direction") or "").casefold() in ("import", "export") and e.get("functional", True):
            out.setdefault(name.casefold(), name)
    return out


def knowledge_delta_from_bundles(old_dir: "Path | str", new_dir: "Path | str"
                                 ) -> "tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]], dict[str, int]]":
    """(knowledge_delta, format_delta, new_api_surface, counts) from two merged knowledge bundles,
    in the shape capability_delta.from_knowledge_delta consumes. Additions only drive units;
    removals are counted (api_surface_touched). Formats: functional import/export names new in
    the NEW bundle (an approximation of refresh_knowledge's format_delta, which needs a .bak copy)."""
    old, new = Path(old_dir), Path(new_dir)
    old_idx = {_av.qualified_name(e): e for e in load_api_surface(old) if not _hidden(e)}
    new_surface = load_api_surface(new)
    new_idx = {_av.qualified_name(e): e for e in new_surface if not _hidden(e)}
    new_q = sorted(set(new_idx) - set(old_idx))
    removed_q = sorted(set(old_idx) - set(new_idx))
    modified: "list[str]" = []
    changes: "dict[str, dict[str, list[str]]]" = {}
    for q in sorted(set(new_idx) & set(old_idx)):
        o, n = old_idx[q], new_idx[q]
        add_m = sorted(set(_av._member_names(n, "methods")) - set(_av._member_names(o, "methods")))  # noqa: SLF001
        add_p = sorted(set(_av._member_names(n, "properties")) - set(_av._member_names(o, "properties")))  # noqa: SLF001
        add_e = sorted(set(_av._member_names(n, "enum_members")) - set(_av._member_names(o, "enum_members")))  # noqa: SLF001
        if add_m or add_p or add_e:
            modified.append(q)
            slot = changes.setdefault(cd.simple_name(q), {"added_methods": [], "added_properties": [],
                                                           "enum_members_added": []})
            slot["added_methods"] = sorted(set(slot["added_methods"]) | set(add_m))
            slot["added_properties"] = sorted(set(slot["added_properties"]) | set(add_p))
            slot["enum_members_added"] = sorted(set(slot["enum_members_added"]) | set(add_e))
    old_f, new_f = _format_names(old), _format_names(new)
    formats_added = [{"name": new_f[k], "ext": None} for k in sorted(set(new_f) - set(old_f))]
    kd = {"new_apis_qualified": new_q, "modified_apis_qualified": modified, "api_signature_changes": changes}
    counts = {"new_types": len(new_q), "removed_types": len(removed_q), "modified_types": len(modified)}
    return kd, {"formats_added": formats_added}, new_surface, counts


# ── content scan (L3) ────────────────────────────────────────────────────────────────────────────

_FM_RE = re.compile(
    r"\A﻿?(?:---[ \t]*\r?\n(?:.*?\r?\n)?---[ \t]*(?:\r?\n|\Z)|\+\+\+[ \t]*\r?\n(?:.*?\r?\n)?\+\+\+[ \t]*(?:\r?\n|\Z))",
    re.S)
_IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_WORD_RE = re.compile(r"[a-z0-9]+")
_FENCE_RE = re.compile(r"(```|~~~).*?(?:\1|\Z)", re.S)
_INLINE_RE = re.compile(r"`[^`\n]+`|<code[^>]*>.*?</code>|<pre[^>]*>.*?</pre>", re.S | re.I)
_LOCALE_FILE_RE = re.compile(r"\.([A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})?)\.[A-Za-z]+$")
_LOCALE_DIR_RE = re.compile(r"^[a-z]{2,3}(?:-[A-Za-z0-9]{2,8})?$")


def strip_frontmatter(text: str) -> str:
    """The page body: a leading YAML (---) or TOML (+++) frontmatter block is removed."""
    return _FM_RE.sub("", text, count=1)


def _code_text(body: str) -> str:
    parts = [m.group(0) for m in _FENCE_RE.finditer(body)]
    rest = _FENCE_RE.sub(" ", body)
    parts += [m.group(0) for m in _INLINE_RE.finditer(rest)]
    return "\n".join(parts)


def _is_strong(term: str) -> bool:
    """Strong terms are unmistakably identifiers: an inner uppercase letter (two or more humps), a digit
    or an underscore. They match anywhere, case-sensitively. A single-word term (`Value`, `parser`) is
    also a dictionary word, so it matches only inside code spans (case-insensitively)."""
    return any(c.isupper() or c.isdigit() or c == "_" for c in term[1:])


class _FileEntry:
    __slots__ = ("path", "text", "idents", "code_idents_lower", "words")

    def __init__(self, path: str, body: str):
        self.path = path
        self.text = body
        self.idents = set(_IDENT_RE.findall(body))
        self.code_idents_lower = {i.lower() for i in _IDENT_RE.findall(_code_text(body))}
        self.words = set(_WORD_RE.findall(body.lower()))


def discover_locale_codes(content_root: "Path | str", criteria: "dict[str, Any]") -> "set[str]":
    """Configured locale codes plus the locale directories found under locale-rooted sites
    (a surface path template whose second segment is the literal English locale)."""
    codes = {str(c).casefold() for c in criteria["scan"]["locale_codes"]}
    root = Path(content_root)
    for tpls in criteria["scan"]["surface_paths"].values():
        for tpl in tpls:
            segs = tpl.split("/")
            if len(segs) >= 2 and segs[1] == "en":
                site = root / segs[0]
                if site.is_dir():
                    codes |= {c.name.casefold() for c in site.iterdir()
                              if c.is_dir() and _LOCALE_DIR_RE.match(c.name)}
    codes.discard("en")
    return codes


def surface_roots(content_root: "Path | str", family: str, platform: str, criteria: "dict[str, Any]"
                  ) -> "dict[str, list[Path]]":
    """surface -> existing English content directories of the product (see docs/reference/content-contracts.md)."""
    root = Path(content_root)
    out: "dict[str, list[Path]]" = {}
    for surface in SURFACES:
        dirs = []
        for tpl in criteria["scan"]["surface_paths"].get(surface, []):
            p = root / tpl.format(family=family, platform=platform)
            if p.is_dir():
                dirs.append(p)
        out[surface] = dirs
    return out


def _is_locale_file(name: str, locales: "set[str]") -> bool:
    m = _LOCALE_FILE_RE.search(name)
    return bool(m) and m.group(1).casefold() in locales


class ContentIndex:
    """English, frontmatter-stripped content of one product, indexed once per surface."""

    def __init__(self, roots: "dict[str, list[Path]]", criteria: "dict[str, Any]", locales: "set[str]"):
        scan = criteria["scan"]
        exts = tuple(str(e).casefold() for e in scan["extensions"])
        self.surfaces: "dict[str, list[_FileEntry]]" = {}
        for surface in SURFACES:
            entries: "list[_FileEntry]" = []
            for root in roots.get(surface, []):
                for f in sorted(p for p in root.rglob("*") if p.is_file()):
                    if not f.name.casefold().endswith(exts) or _is_locale_file(f.name, locales):
                        continue
                    rel = f.relative_to(root)
                    if rel.parts and rel.parts[0].casefold() in locales:
                        continue
                    try:
                        text = f.read_text(encoding="utf-8", errors="replace")
                    except OSError:
                        continue
                    entries.append(_FileEntry(rel.as_posix(), strip_frontmatter(text)))
            self.surfaces[surface] = entries

    def file_counts(self) -> "dict[str, int]":
        return {s: len(self.surfaces.get(s, [])) for s in SURFACES}


def build_content_index(content_root: "Path | str", family: str, platform: str, criteria: "dict[str, Any] | None" = None
                        ) -> ContentIndex:
    crit = criteria or load_criteria()
    return ContentIndex(surface_roots(content_root, family, platform, crit), crit,
                        discover_locale_codes(content_root, crit))


def unit_terms(unit: "dict[str, Any]", *, min_length: int = 3) -> "list[dict[str, Any]]":
    """Searchable terms of a unit / file hint: [{term, requires}] sorted. Types and formats stand
    alone; a member or enum constant `Owner.name` requires its owner's simple name in the same file."""
    if unit.get("terms"):
        raw = [{"term": str(t["term"]), "requires": t.get("requires")} for t in unit["terms"]]
    else:
        raw = []
        for s in unit.get("symbols") or []:
            if cd.is_member_symbol(s):
                raw.append({"term": cd.simple_name(s), "requires": cd.simple_name(cd.type_of_symbol(s))})
            else:
                raw.append({"term": cd.simple_name(s), "requires": None})
        for f in unit.get("formats") or []:
            raw.append({"term": str(f), "requires": None})
    seen: "set[tuple[str, str | None]]" = set()
    out = []
    for t in sorted(raw, key=lambda x: (x["term"], x["requires"] or "")):
        key = (t["term"], t["requires"])
        if len(t["term"]) >= min_length and key not in seen:
            seen.add(key)
            out.append(t)
    return out


def unit_keywords(unit: "dict[str, Any]", *, placement_config: "dict[str, Any]", criteria: "dict[str, Any]"
                  ) -> "list[str]":
    """Informative title tokens (type / member / format names; generic tokens and short tokens dropped)."""
    scan = criteria["scan"]
    generic = {str(g).casefold() for g in ((placement_config.get("grouping") or {}).get("token_affinity") or {})
               .get("generic_tokens") or []}
    toks: "set[str]" = set()
    for t in unit_terms(unit, min_length=1):
        for tok in cd.tokens(t["term"]):
            if len(tok) >= int(scan["keyword_min_length"]) and tok not in generic and not tok.isdigit():
                toks.add(tok)
    return sorted(toks)[: int(scan["max_keywords_per_unit"])]


def _hits(term: str, f: _FileEntry) -> bool:
    if _is_strong(term):
        return term in f.idents
    return term.casefold() in f.code_idents_lower


def _term_hit(t: "dict[str, Any]", f: _FileEntry) -> bool:
    if not _hits(t["term"], f):
        return False
    return t["requires"] is None or _hits(str(t["requires"]), f)


def _qualified_forms(unit: "dict[str, Any]") -> "dict[str, list[str]]":
    """simple type name -> dotted qualified forms (`pkg.sub.Name`, from `pkg.sub::Name`; path qualifiers skipped)."""
    out: "dict[str, list[str]]" = {}
    for s in unit.get("symbols") or []:
        if cd.is_member_symbol(s) or "::" not in s:
            continue
        ns, name = s.split("::", 1)
        if ns and "/" not in ns and "\\" not in ns and "." not in name:
            out.setdefault(name, []).append(f"{ns}.{name}")
    return out


def scan_content_presence(units: "Iterable[dict[str, Any]]", content_roots: "dict[str, list[Path]]", *,
                          criteria: "dict[str, Any] | None" = None, index: "ContentIndex | None" = None,
                          placement_config: "dict[str, Any] | None" = None, locales: "set[str] | None" = None
                          ) -> "dict[str, dict[str, Any]]":
    """L3. For every unit (or GT-2 file hint) and each of the five surfaces: `present_count` (distinct
    terms found), `terms_total`, `coverage` (share of the unit's NEW types found), `primary_present`,
    `files` (<= max_files_per_surface, sorted), `qualified_hits`, `keyword_hits`; plus the unit-level
    `absent_from` (surfaces with zero terms), `coverage` {basis, new_symbols, present_symbols, ratio,
    by_surface, surfaces_carrying, member_ratio} and `content_gap` (ratio over the gap surfaces' union
    strictly below max_coverage_ratio; see unit_content_gap).
    `content_roots` maps surface -> [dir, ...] (see surface_roots); returns {unit_id: result}."""
    crit = criteria or load_criteria()
    pcfg = placement_config if placement_config is not None else cd.load_config()
    idx = index or ContentIndex(content_roots, crit, locales if locales is not None else
                                {str(c).casefold() for c in crit["scan"]["locale_codes"]})
    scan = crit["scan"]
    max_files = int(scan["max_files_per_surface"])
    result: "dict[str, dict[str, Any]]" = {}
    for unit in units:
        terms = unit_terms(unit, min_length=int(scan["min_term_length"]))
        kws = unit_keywords(unit, placement_config=pcfg, criteria=crit)
        qforms = _qualified_forms(unit)
        # PRIMARY terms = the unit's NEW public types (internal ones excluded); a unit with none falls back to
        # all of its new symbols. Members / constants / formats of a unit that has new types are SECONDARY:
        # reported as member_ratio, never decisive (they can hide behind one shared existing name).
        internal = set(unit.get("internal_symbols") or [])
        type_names = {cd.simple_name(s) for s in unit.get("symbols") or []
                      if not cd.is_member_symbol(s) and s not in internal}
        primary = [t for t in terms if t["requires"] is None and t["term"] in type_names]
        basis = "new_types"
        if not primary:
            primary, basis = list(terms), "all_new_symbols"
        primary_ids = {_display(t) for t in primary}
        secondary = [t for t in terms if _display(t) not in primary_ids]
        per_surface: "dict[str, Any]" = {}
        member_hits: "dict[str, set[str]]" = {}
        for surface in SURFACES:
            files = idx.surfaces.get(surface, [])
            hit_terms: "set[str]" = set()
            hit_files: "list[str]" = []
            qual: "set[str]" = set()
            kw_hits: "set[str]" = set()
            for f in files:
                found = [t for t in terms if _term_hit(t, f)]
                if found:
                    hit_terms |= {_display(t) for t in found}
                    hit_files.append(f.path)
                    for t in found:
                        for form in qforms.get(t["term"], []):
                            if t["requires"] is None and "." in form and form in f.text:
                                qual.add(form)
                kw_hits |= {k for k in kws if k in f.words}
            per_surface[surface] = {
                "present_count": len(hit_terms),
                "terms_total": len(terms),
                "coverage": round(len(hit_terms & primary_ids) / len(primary_ids), 6) if primary_ids else 0.0,
                "primary_present": sorted(hit_terms & primary_ids),
                "files": sorted(set(hit_files))[:max_files],
                "files_scanned": len(files),
                "qualified_hits": sorted(qual),
                "keyword_hits": sorted(kw_hits),
            }
            member_hits[surface] = hit_terms - primary_ids
        gap_surfaces = [s for s in crit["content_gap"]["gap_surfaces"] if s in per_surface]
        present = set().union(*(set(per_surface[s]["primary_present"]) for s in gap_surfaces)) if gap_surfaces else set()
        m_present = set().union(*(member_hits[s] for s in gap_surfaces)) if gap_surfaces else set()
        sec_ids = {_display(t) for t in secondary}
        coverage = {
            "basis": basis,
            "primary_total": len(primary_ids),
            "new_symbols": sorted(primary_ids),
            "present_symbols": sorted(present),
            "ratio": round(len(present) / len(primary_ids), 6) if primary_ids else 0.0,
            "by_surface": {s: per_surface[s]["primary_present"] for s in SURFACES},
            "surfaces_carrying": sorted(s for s in SURFACES if per_surface[s]["primary_present"]),
            "member_total": len(sec_ids),
            "member_present": len(m_present & sec_ids),
            "member_ratio": round(len(m_present & sec_ids) / len(sec_ids), 6) if sec_ids else None,
        }
        entry = {
            "id": unit["id"],
            "terms": sorted(_display(t) for t in terms),
            "keywords": kws,
            "presence": per_surface,
            "coverage": coverage,
            "absent_from": sorted(s for s in SURFACES if per_surface[s]["present_count"] == 0),
        }
        entry["content_gap"] = unit_content_gap(entry, crit)
        result[str(unit["id"])] = entry
    return result


def _display(t: "dict[str, Any]") -> str:
    return t["term"] if t["requires"] is None else f"{t['requires']}.{t['term']}"


def unit_content_gap(scan: "dict[str, Any]", criteria: "dict[str, Any]") -> bool:
    """Criterion-3 predicate on a unit's scan block (`presence` + `coverage`), recomputed with the criteria in
    force: the share of NEW types present on ANY gap surface is strictly below max_coverage_ratio. A unit with
    nothing to look for is never claimed as a gap."""
    cg = criteria["content_gap"]
    total = int((scan.get("coverage") or {}).get("primary_total", 0))
    if not cg["gap_surfaces"] or total <= 0:
        return False
    present: "set[str]" = set()
    for s in cg["gap_surfaces"]:
        present |= set(((scan.get("presence") or {}).get(s) or {}).get("primary_present") or [])
    return len(present) / total < float(cg["max_coverage_ratio"])


# ── GT-2 file hints ──────────────────────────────────────────────────────────────────────────────

def file_hints(adapter_delta: "dict[str, Any]", platform: str, *, config: "dict[str, Any] | None" = None
               ) -> "list[dict[str, Any]]":
    """GT-2: one hint per ADDED source file that sits on an API path. The hint term is the file stem
    (private `_x` modules and bare `__init__` style stems are skipped)."""
    cfg = config if config is not None else la.load_language_config()
    added = list(adapter_delta.get("added_source_files") or [])
    # classify with the platform the adapter itself reported, so hints can never disagree with its verdict
    api = set(la.classify_paths(adapter_delta.get("platform") or platform, added, config=cfg)["api_files"])
    hints = []
    for path in sorted(api):
        stem = Path(path).stem
        if not stem or stem.startswith("_") or not _IDENT_RE.fullmatch(stem):
            continue
        uid = "FH-" + hashlib.sha256(path.encode("utf-8")).hexdigest()[:8]
        hints.append({"id": uid, "kind": "file-hint", "title": f"New source file: {path}", "path": path,
                      "symbols": [stem], "terms": [{"term": stem, "requires": None}],
                      "evidence_tier": la.GT2})
    return hints


# ── analysis ─────────────────────────────────────────────────────────────────────────────────────

def _summary_counts(api_delta: "dict[str, Any]") -> "dict[str, int]":
    return {"added_types": len(api_delta.get("added_types") or []),
            "added_members": len(api_delta.get("added_members") or []),
            "enum_constants_added": len(api_delta.get("enum_constants_added") or []),
            "formats_added": len(api_delta.get("formats_added") or [])}


def _adapter_touched(ad: "dict[str, Any]") -> "bool | None":
    if ad.get("ground_truth_tier") == la.GT1:
        return bool(ad.get("added_types") or ad.get("removed_types") or ad.get("changed_types"))
    return ad.get("api_surface_touched")


def _propagation(rec: "dict[str, Any] | None", head: "str | None") -> "dict[str, Any]":
    sha = (rec or {}).get("content_propagated_sha")
    if not sha:
        status = "UNRECORDED"
    elif head and sha == head:
        status = "PROPAGATED"
    else:
        status = "DRIFTED"
    return {"status": status, "content_propagated_sha": sha, "state_present": rec is not None}


def _release_block(release_info: Any, head: "str | None", baseline_version: "str | None") -> "dict[str, Any]":
    info = release_info(head) if callable(release_info) else (release_info or {})
    published = info.get("published_version")
    return {"release_state": info.get("release_state") or "unknown",
            "release_state_reason": info.get("release_state_reason"),
            "published_version": published, "baseline_version": baseline_version,
            "new_release": compute_new_release(published, baseline_version)}


def _placement_summary(unit: "dict[str, Any]") -> "dict[str, str]":
    return {s: ((unit.get("dispositions") or {}).get(s) or {}).get("action", "none") for s in SURFACES}


def _skeleton(family: str, platform: str) -> "dict[str, Any]":
    return {
        "schema_version": SCHEMA_VERSION, "kind": ANALYSIS_KIND, "family": family, "platform": platform,
        "product": f"{family}/{platform}", "status": STATUS_OK, "error": None,
        "baseline": {"ref": None, "source": None, "assumed": False, "version": None, "reachable": None,
                     "reachability": None},
        "head": {"ref": None, "source": None},
        "propagation": {"status": "UNRECORDED", "content_propagated_sha": None, "state_present": False},
        "release": {"release_state": "unknown", "release_state_reason": None, "published_version": None,
                    "baseline_version": None, "new_release": None},
        "method": None, "ground_truth_tier": None, "symbol_level": False, "fallback": None,
        "api_surface_touched": None, "delta_summary": {}, "changed_files": {},
        "units": [], "file_hints": [], "content_files_scanned": {}, "notes": [], "volatile": {},
    }


def analyze_product(family: str, platform: str, *, base_ref: "str | None" = None, head_ref: "str | None" = None,
                    repo_path: "Path | str | None" = None, content_root: "Path | str",
                    state_reader: "Callable[[str, str], dict | None] | None" = None,
                    adapter: "la.LanguageAdapter | None" = None, runner: "Callable[..., Any] | None" = None,
                    config: "dict[str, Any] | None" = None,
                    bundles: "tuple[Path | str, Path | str] | None" = None,
                    criteria: "dict[str, Any] | None" = None, knowledge_root: "Path | str | None" = None,
                    ensure_reachable: "Callable[[Path | str, str], str | bool] | None" = None,
                    release_info: Any = None, grouping_overrides: "list[dict[str, Any]] | None" = None,
                    now: "str | None" = None) -> "dict[str, Any]":
    """See the module docstring. Never raises for an unreachable baseline / missing data: the
    result's `status` is OK | ORPHANED_BASELINE | NO_BASELINE | ERROR. `config` is the
    capability_placement config (default: the shipped file); `release_info` is a dict (or a
    callable(head_sha) -> dict) with release_state / published_version."""
    crit = criteria or load_criteria()
    pcfg = config if config is not None else cd.load_config()
    runner = runner or la.default_runner
    ensure = ensure_reachable or default_ensure_reachable
    kroot = Path(knowledge_root) if knowledge_root is not None else _REPO_ROOT / "knowledge"
    res = _skeleton(family, platform)
    if now:
        res["volatile"]["generated_at"] = now
    if repo_path is not None:
        res["volatile"]["repo_path"] = str(repo_path)
    rec = state_reader(family, platform) if state_reader else None

    # ---- baseline / head ---------------------------------------------------------------------
    model = read_model_fields(kroot / family / platform / "merged" / "model.yaml")
    base_version = model["version"]
    kd = fd = new_surface = None
    bcounts: "dict[str, int]" = {}
    if bundles is not None:
        old_dir, new_dir = Path(bundles[0]), Path(bundles[1])
        old_model = read_model_fields(old_dir / "model.yaml")
        new_model = read_model_fields(new_dir / "model.yaml")
        base_sha = base_ref or old_model["repo_sha"]
        base_version = old_model["version"]
        head_sha = head_ref or new_model["repo_sha"]
        res["baseline"].update(ref=base_sha, source="explicit" if base_ref else "bundle",
                               assumed=not base_ref, version=base_version)
        res["head"].update(ref=head_sha, source="explicit" if head_ref else "bundle")
        res["method"] = "bundles"
        res["volatile"]["bundles"] = [str(old_dir), str(new_dir)]
    else:
        if base_ref:
            base_sha, src, assumed = base_ref, "explicit", False
        elif rec and rec.get("content_propagated_sha"):
            base_sha, src, assumed = rec["content_propagated_sha"], "content_propagated_sha", False
        elif model["repo_sha"]:
            base_sha, src, assumed = model["repo_sha"], "knowledge_sha", True
        else:
            base_sha, src, assumed = None, None, False
        # the knowledge version describes the baseline only when the baseline IS the knowledge sha
        base_version = base_version if (base_sha and base_sha == model["repo_sha"]) else None
        res["baseline"].update(ref=base_sha, source=src, assumed=assumed, version=base_version)
        head_sha, head_src = (head_ref, "explicit") if head_ref else (None, None)
        if repo_path is not None and not head_ref:
            head_sha, head_src = resolve_head(repo_path, runner)
        res["head"].update(ref=head_sha, source=head_src)

    res["propagation"] = _propagation(rec, head_sha)
    res["release"] = _release_block(release_info, head_sha, base_version)

    def finish(status: str, error: "str | None" = None) -> "dict[str, Any]":
        res["status"], res["error"] = status, error
        return res

    if not base_sha:
        return finish(STATUS_NO_BASELINE, "no baseline: no base_ref, no content_propagated_sha, no model.yaml repo_sha")
    if bundles is None and repo_path is None:
        return finish(STATUS_ERROR, "repo_path is required unless bundles are given")
    if not head_sha:
        return finish(STATUS_ERROR, "upstream head could not be resolved")

    # ---- delta -------------------------------------------------------------------------------------
    hints: "list[dict[str, Any]]" = []
    if bundles is not None:
        kd, fd, new_surface, bcounts = knowledge_delta_from_bundles(bundles[0], bundles[1])
        api_delta = cd.from_knowledge_delta(kd, fd, api_surface=new_surface)
        res["ground_truth_tier"] = TIER_KNOWLEDGE
        res["symbol_level"] = True
        res["api_surface_touched"] = bool(bcounts.get("new_types") or bcounts.get("removed_types")
                                          or bcounts.get("modified_types") or fd["formats_added"])
        res["changed_files"] = {"counts": bcounts}
    else:
        try:
            verdict = normalize_reachability(ensure(repo_path, base_sha))
        except Exception as exc:  # noqa: BLE001 -- a probe failure is "could not tell", never an orphan
            verdict = UNKNOWN
            res["notes"].append(f"reachability probe raised {type(exc).__name__}: {exc}")
        res["baseline"]["reachability"] = verdict
        res["baseline"]["reachable"] = {REACHABLE: True, ORPHANED: False}.get(verdict)
        if verdict == ORPHANED:
            return finish(STATUS_ORPHANED, f"baseline {str(base_sha)[:12]} is unreachable after a completed deepen")
        if verdict != REACHABLE:
            return finish(STATUS_UNVERIFIABLE,
                          f"baseline {str(base_sha)[:12]} reachability could not be established "
                          "(network, lock, timeout or fetch cap): NOT an orphan verdict")
        if base_sha == head_sha:
            api_delta = cd.normalize_delta({"ground_truth": {"tier": la.ground_truth_tier_for(platform),
                                                              "symbol_level": la.ground_truth_tier_for(platform) == la.GT1}})
            res["ground_truth_tier"] = la.ground_truth_tier_for(platform)
            res["symbol_level"] = res["ground_truth_tier"] == la.GT1
            res["api_surface_touched"] = False
            res["method"] = "no_change"
            res["notes"].append("baseline equals upstream head: nothing to analyse")
        else:
            res["method"] = "adapter"
            use = adapter or la.adapter_for(platform)
            try:
                ad = use.api_delta(base_sha, head_sha, repo_path=repo_path, runner=runner)
            except la.AdapterError as exc:
                if use.ground_truth_tier != la.GT1:
                    return finish(STATUS_ERROR, f"adapter failed: {type(exc).__name__}: {exc}")
                try:
                    ad = la.GenericFileAdapter(platform).api_delta(base_sha, head_sha, repo_path=repo_path,
                                                                   runner=runner)
                except la.AdapterError as exc2:
                    return finish(STATUS_ERROR, f"adapter failed: {type(exc2).__name__}: {exc2}")
                res["fallback"] = {"from": la.GT1, "reason": f"{type(exc).__name__}: {exc}"}
            ad = copy.deepcopy(ad)
            ad.pop("volatile", None)
            res["ground_truth_tier"] = ad.get("ground_truth_tier")
            res["symbol_level"] = ad.get("ground_truth_tier") == la.GT1
            res["api_surface_touched"] = _adapter_touched(ad)
            api_delta = cd.from_adapter_delta(ad)
            if ad.get("ground_truth_tier") == la.GT1:
                res["changed_files"] = {"counts": {"added_types": len(ad.get("added_types") or []),
                                                   "removed_types": len(ad.get("removed_types") or []),
                                                   "changed_types": len(ad.get("changed_types") or [])}}
            else:
                hints = file_hints(ad, platform)
                res["changed_files"] = {
                    "counts": {"changed": len(ad.get("changed_files") or []),
                               "source": len(ad.get("source_files") or []),
                               "api_path": len(ad.get("api_path_files") or []),
                               "added_source": len(ad.get("added_source_files") or [])},
                    "api_path_files": sorted(ad.get("api_path_files") or [])[:25],
                    "added_source_files": sorted(ad.get("added_source_files") or [])[:25],
                    "changelog_files": sorted(ad.get("changelog_files") or [])[:10],
                    "known_platform": ad.get("known_platform")}
                res["notes"].append("GT-2: file-level evidence only; capability units unavailable, file_hints "
                                    "(added API-path source files) stand in for them")

    # ---- units ---------------------------------------------------------------------------------------
    ledger = cd.build_ledger(api_delta, family=family, platform=platform, upstream_head=head_sha, config=pcfg,
                             grouping_overrides=grouping_overrides,
                             meta={"base_ref": str(base_sha), "analysis": ANALYSIS_KIND})
    res["delta_summary"] = _summary_counts(api_delta)
    res["notes"] += [n for n in ledger.get("notes") or [] if n not in res["notes"]]
    units = [dict(u) for u in ledger["units"]]

    # ---- L3 ------------------------------------------------------------------------------------------
    roots = surface_roots(content_root, family, platform, crit)
    index = ContentIndex(roots, crit, discover_locale_codes(content_root, crit))
    res["content_files_scanned"] = index.file_counts()
    scanned = scan_content_presence(units + hints, roots, criteria=crit, index=index, placement_config=pcfg)
    for u in units:
        s = scanned[u["id"]]
        u["placement_summary"] = _placement_summary(u)
        u["scan"] = {k: s[k] for k in ("terms", "keywords", "presence", "coverage", "absent_from", "content_gap")}
    for h in hints:
        s = scanned[h["id"]]
        h["scan"] = {k: s[k] for k in ("terms", "keywords", "presence", "coverage", "absent_from", "content_gap")}
    res["units"] = sorted(units, key=lambda u: u["id"])
    res["file_hints"] = sorted(hints, key=lambda h: h["id"])
    return finish(STATUS_OK)


# ── criteria evaluation (L4 inputs) ──────────────────────────────────────────────────────────────

def _worth(unit: "dict[str, Any]", criteria: "dict[str, Any]") -> bool:
    wm = criteria["worth_mentioning"]
    need = ACTION_RANK[wm["min_action"]]
    summary = unit.get("placement_summary") or _placement_summary(unit)
    return any(ACTION_RANK.get(summary.get(s, "none"), 0) >= need for s in wm["surfaces"])


def _absent_symbols(items: "list[dict[str, Any]]", limit: int) -> "list[str]":
    out: "set[str]" = set()
    for u in items:
        out |= set(u.get("symbols") or [])
    return sorted(out)[:limit]


def evaluate_candidate(analysis: "dict[str, Any]", criteria: "dict[str, Any]") -> "dict[str, Any]":
    """The four Wave-E criteria for one analysis, each with its evidence, plus `candidate`,
    `reasons[]`, `classification` (candidate | NOT_ANALYSED | NOT_ANALYSABLE | NO_DRIFT_SIGNAL |
    NOT_WORTH_MENTIONING | COVERED | <analysis status>), `release_triggered`, `api_touched` and
    `gap_units` (the ranking inputs)."""
    product = analysis.get("product") or f"{analysis.get('family')}/{analysis.get('platform')}"
    status = analysis.get("status")
    prop = analysis.get("propagation") or {}
    rel = analysis.get("release") or {}
    units = list(analysis.get("units") or [])
    hints = list(analysis.get("file_hints") or [])
    api_touched = analysis.get("api_surface_touched")

    # criterion 1 -- drift / release
    not_propagated = prop.get("status") != "PROPAGATED"
    new_release = rel.get("new_release") is True
    main_states = criteria["drift"]["main_release_states"]
    main_api = (rel.get("release_state") in main_states
                and (api_touched is True or not criteria["drift"]["require_api_touched_for_main"]))
    c1 = not_propagated and (new_release or main_api)
    release_triggered = bool(not_propagated and new_release)
    c1_ev = {"propagation_status": prop.get("status"), "new_release": rel.get("new_release"),
             "published_version": rel.get("published_version"), "baseline_version": rel.get("baseline_version"),
             "release_state": rel.get("release_state"), "api_surface_touched": api_touched,
             "baseline_assumed": (analysis.get("baseline") or {}).get("assumed"),
             "release_evidence": "unknown" if rel.get("release_state") in (None, "unknown") else rel.get("release_state"),
             "trigger": "release" if release_triggered else ("main_api_touched" if (c1 and main_api) else None)}

    # criterion 2 -- worth mentioning
    worth_units = [u for u in units if _worth(u, criteria)]
    gt2_ok = len(hints) >= criteria["gt2"]["min_added_api_files"]
    worth_items: "list[dict[str, Any]]" = list(worth_units)
    if not units and gt2_ok:
        worth_items = list(hints)
    c2 = len(worth_units) >= criteria["worth_mentioning"]["min_units"] or (not units and gt2_ok)
    c2_ev = {"worth_units": sorted(u["id"] for u in worth_units), "units_total": len(units),
             "file_hints": len(hints), "evidence_tier": "GT-2-file-level" if (not units and hints) else "unit"}

    # criterion 3 -- content gap (among worth-mentioning items)
    gap_items = [u for u in worth_items if unit_content_gap(u.get("scan") or {}, criteria)]
    c3 = c2 and len(gap_items) >= criteria["content_gap"]["min_gap_units"]
    c3_ev = {"gap_units": sorted(u["id"] for u in gap_items),
             "absent_symbols": _absent_symbols(gap_items, int(criteria["output"]["max_absent_symbols"])),
             "covered_units": sorted(u["id"] for u in worth_items if u not in gap_items)}

    # criterion 4 -- analysable
    tier = analysis.get("ground_truth_tier")
    c4 = tier in criteria["analysable"]["tiers"]
    c4_ev = {"ground_truth_tier": tier, "symbol_level": bool(analysis.get("symbol_level")),
             "method": analysis.get("method"), "fallback": analysis.get("fallback")}

    reasons: "list[str]" = []
    if status != STATUS_OK:
        classification = status
        reasons.append(f"analysis status {status}" + (f": {analysis.get('error')}" if analysis.get("error") else ""))
        candidate = False
    else:
        if not c4:
            classification = "NOT_ANALYSABLE"
            reasons.append(f"ground-truth tier {tier!r} is not analysable")
        elif not c1:
            classification = "NO_DRIFT_SIGNAL"
            reasons.append("no new release and no API-touching change on main, or content already PROPAGATED")
        elif not c2:
            classification = "NOT_WORTH_MENTIONING"
            reasons.append("no capability unit reaches the mention threshold on a non-reference surface")
        elif not c3:
            classification = "COVERED"
            reasons.append("every worth-mentioning unit already appears in docs/kb/blog/products English content")
        else:
            classification = "candidate"
        candidate = classification == "candidate"
        if candidate:
            reasons.append(f"{len(gap_items)} worth-mentioning unit(s) under-covered in English content; trigger={c1_ev['trigger']}")
            if c1_ev["release_evidence"] == "unknown":
                reasons.append("release_evidence: unknown")
    return {
        "product": product, "candidate": candidate, "classification": classification, "reasons": reasons,
        "release_triggered": release_triggered,
        "release_state": rel.get("release_state") or "unknown",
        "api_touched": bool(api_touched is True),
        "gap_units": len(gap_items) if candidate else 0,
        "criteria": {"1_drift_release": {"ok": bool(c1), "evidence": c1_ev},
                     "2_worth_mentioning": {"ok": bool(c2), "evidence": c2_ev},
                     "3_content_gap": {"ok": bool(c3), "evidence": c3_ev},
                     "4_analysable": {"ok": bool(c4), "evidence": c4_ev}},
    }


def rank_key(ev: "dict[str, Any]", criteria: "dict[str, Any]") -> tuple:
    """Sort key from criteria.ranking.order (default: release-triggered first, then API-touched, then the
    release state's position in ranking.release_state_order -- unreleased_main before unknown --, then
    gap-unit count desc, then family/platform)."""
    states = list(criteria["ranking"]["release_state_order"])
    state = ev.get("release_state") or "unknown"
    parts = {
        "release_triggered": 0 if ev["release_triggered"] else 1,
        "api_touched": 0 if ev["api_touched"] else 1,
        "release_state": states.index(state) if state in states else len(states),
        "gap_units": -int(ev["gap_units"]),
        "product": ev["product"],
    }
    return tuple(parts[k] for k in criteria["ranking"]["order"])


def classify_all(analyses: "Iterable[dict[str, Any]]", criteria: "dict[str, Any]") -> "list[dict[str, Any]]":
    """Every analysis evaluated (sorted by product) -- the G8 'all products classified' view."""
    return sorted((evaluate_candidate(a, criteria) for a in analyses), key=lambda e: e["product"])


def rank_candidates(analyses: "Iterable[dict[str, Any]]", criteria: "dict[str, Any]") -> "list[dict[str, Any]]":
    """Deterministic ranking of the candidates only (`rank` starts at 1). Input order is irrelevant."""
    cands = [e for e in classify_all(analyses, criteria) if e["candidate"]]
    ranked = sorted(cands, key=lambda e: rank_key(e, criteria))
    return [{"rank": i, **e} for i, e in enumerate(ranked, start=1)]


# ── serialisation ────────────────────────────────────────────────────────────────────────────────

def dumps(obj: Any) -> str:
    return json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def write_text(path: "Path | str", text: str) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


def canonical_for_compare(obj: Any) -> Any:
    """Deep copy with every `volatile` key removed (two runs over identical truth compare equal)."""
    if isinstance(obj, dict):
        return {k: canonical_for_compare(v) for k, v in obj.items() if k != "volatile"}
    if isinstance(obj, list):
        return [canonical_for_compare(v) for v in obj]
    return copy.deepcopy(obj)


def build_candidates_report(analyses: "list[dict[str, Any]]", criteria: "dict[str, Any]") -> "dict[str, Any]":
    """candidates.json content: ranked candidates with full evidence, every other product with its
    classification. Contains no wall-clock values (byte-identical on re-run)."""
    evals = classify_all(analyses, criteria)
    ranked = rank_candidates(analyses, criteria)
    by_product = {a.get("product"): a for a in analyses}
    cands = []
    for e in ranked:
        a = by_product.get(e["product"]) or {}
        gap_ids = set(e["criteria"]["3_content_gap"]["evidence"]["gap_units"])
        items = [u for u in (a.get("units") or []) + (a.get("file_hints") or []) if u.get("id") in gap_ids]
        cands.append({
            **e,
            "baseline": a.get("baseline"), "head": a.get("head"), "ground_truth_tier": a.get("ground_truth_tier"),
            "release": a.get("release"),
            "gap_unit_details": [{"id": u["id"], "title": u.get("title"), "symbols": sorted(u.get("symbols") or []),
                                  "absent_from": (u.get("scan") or {}).get("absent_from", []),
                                  "placement_summary": u.get("placement_summary")} for u in sorted(items, key=lambda x: x["id"])],
        })
    excluded = [{"product": e["product"], "classification": e["classification"], "reasons": e["reasons"]}
                for e in evals if not e["candidate"]]
    by_class: "dict[str, int]" = {}
    for e in evals:
        by_class[e["classification"]] = by_class.get(e["classification"], 0) + 1
    return {"schema_version": SCHEMA_VERSION, "kind": CANDIDATES_KIND, "criteria_sha256": criteria_digest(criteria),
            "summary": {"total": len(evals), "candidates": len(cands), "by_classification": dict(sorted(by_class.items()))},
            "candidates": cands, "excluded": excluded}


def render_markdown(report: "dict[str, Any]") -> str:
    s = report["summary"]
    lines = ["# Propagation candidates", "",
             f"criteria sha256: `{report['criteria_sha256'][:16]}`  ",
             f"products: {s['total']} | candidates: {s['candidates']} | "
             + ", ".join(f"{k}={v}" for k, v in s["by_classification"].items()), "",
             "## Ranked candidates", ""]
    if report["candidates"]:
        lines += ["| # | product | trigger | api touched | gap units | tier | baseline |", "|---|---|---|---|---|---|---|"]
        for c in report["candidates"]:
            trig = c["criteria"]["1_drift_release"]["evidence"]["trigger"]
            base = (c.get("baseline") or {})
            lines.append(f"| {c['rank']} | {c['product']} | {trig} | {'yes' if c['api_touched'] else 'no'} | "
                         f"{c['gap_units']} | {c.get('ground_truth_tier')} | "
                         f"{str(base.get('ref'))[:10]}{' (assumed)' if base.get('assumed') else ''} |")
        for c in report["candidates"]:
            lines += ["", f"### {c['product']}", ""]
            for u in c["gap_unit_details"]:
                syms = ", ".join(f"`{x}`" for x in u["symbols"][:8]) + (" ..." if len(u["symbols"]) > 8 else "")
                lines.append(f"- {u['id']} {u.get('title')}: {syms}")
    else:
        lines.append("_none_")
    lines += ["", "## Not candidates", ""]
    if report["excluded"]:
        lines += ["| product | classification | reason |", "|---|---|---|"]
        for e in report["excluded"]:
            lines.append(f"| {e['product']} | {e['classification']} | {'; '.join(e['reasons'])} |")
    else:
        lines.append("_none_")
    return "\n".join(lines) + "\n"
