"""capability_delta.py -- capability units and the five-surface disposition ledger (MT074 card B4).

CONTRACT: scripts/pipeline/lib/capability_delta.py
  purpose: A knowledge/API delta says WHICH symbols changed; it does not say which pages owe a
           change for them. This library turns a delta into CAPABILITY UNITS (a coherent group of
           new symbols a reader would call "a feature") and a DISPOSITION LEDGER: for every unit
           and each of the five surfaces (reference, docs, kb, blog, products) an explicit
           decision -- create | update | mention | none -- with a target and, for `none`, a
           mandatory rationale. Plan time proves the ledger is COMPLETE (validate_ledger); close
           time proves it was SATISFIED (satisfaction_report, statuses computed from the files,
           never trusted from the ledger). Pure library: no network, no git, no clock.
  config:  config/capability_placement.yaml -- every threshold. Code contains none.

INPUT SCHEMA -- the generic `api_delta` dict (normalize_delta fills defaults)::

    {"schema_version": 1,
     "added_types":   [{"qualified": "<ns>::<Name>" | "<Name>", "kind": str|None,
                        "member_count": int,            # public members of the NEW type
                        "signature_refs": [identifier]}],
     "added_members": [{"owner": "<qualified or simple type>", "name": str,
                        "signature_refs": [identifier]}],       # members added to EXISTING types
     "enum_constants_added": [{"owner": "<enum>", "name": str}],
     "formats_added": [{"name": str, "ext": str|None}],
     "name_collisions": [{"name": str, ...}],
     "existing_symbols": [str] | None,        # None = unknown -> token affinity is skipped
     "public_surface_size": int | None,       # types + members, for share_of_public_surface
     "ground_truth": {"tier": "GT-1"|"GT-2"|..., "symbol_level": bool},
     "unconfirmed": {"breaking_unconfirmed": [name], "extraction_drift_suspect": [qualified]}}

  Adapters: from_knowledge_delta(knowledge_delta, format_delta, api_surface=None) (absent keys
  are empty) and from_adapter_delta(adapter_delta) for lib/language_adapters results. A GT-2
  adapter delta carries NO symbols: the ledger is `symbol_level: false` with no units, and the
  gate refuses to treat that as "nothing to propagate".

SYMBOL FORM (shared with lib/availability.py): type ``<qualifier>::<Name>``; member / enum
constant ``<type symbol>.<member>``; format override token ``format:<name>``.

GROUPING (documented honestly -- every automatic grouping is a DRAFT for independent review):
  (a) structural  new public types co-added in the same namespace form a base group (a source-file
      qualifier -- last path segment has an extension -- is reduced to its directory; no qualifier at all = one shared namespace). Added
      members of existing types whose SIGNATURES reference a new type's simple name attach to
      that type's group. Limits: it needs the extractor to have recorded parameter / return
      types (many extractors leave them empty -> nothing to attach), matching is by simple
      name, and a flat namespace that holds a whole library groups everything into one unit.
  (b) token affinity (default ON, config grouping.token_affinity)  CamelCase/snake tokens; a
      token carried by >= min_new_symbols_sharing NEW types and <= max_existing_symbols_sharing
      EXISTING symbols links their groups. Unattached members / enum constants / formats attach
      to the group whose type names share an informative token (constants and formats by a
      normalised-key substring match). Limits: lexical, so it can both over-merge (two
      unrelated features sharing a rare word) and under-merge (a feature named differently
      from its helpers); generic tokens and short tokens are ignored; it is SKIPPED when
      existing_symbols is unknown.
  (c) grouping_overrides  [{id, symbols}] from an independent reviewer always win and mark the
      unit `grouping: reviewed`. A symbol that does not exist in the delta, or is claimed twice,
      is a GroupingOverrideError (a reviewer typo must not silently drop a capability).
  Leftovers become units, never dropped: members with no group -> one `api-extension` unit per
  owning type; constants with no group -> one `format-route` unit per owning enum (formats with a
  matching key join it); remaining formats -> one `format-route` unit.

UNIT (ledger["units"][i])::

    {"id": "CU-<8 hex of sha256(sorted symbols + format:<name>)>", "title", "grouping": draft|reviewed,
     "kind": route|type-group|api-extension|format-route,
     "symbols": [...], "internal_symbols": [...], "enum_constants": [...], "formats": [...],
     "scale": {"new_public_types", "new_internal_types", "new_public_members", "new_enum_constants",
               "new_formats", "introduces_new_io_route", "introduces_options_type",
               "share_of_public_surface", "verified_example_present", "snippet_candidates"},
     "availability": released|unreleased|unknown, "unconfirmed_flags": [...],
     "ambiguous_symbols": [{"symbol", "candidates"}],   # member of a colliding owner name, unresolved
     "available_since": str|null, "partial_earlier": bool, "release_version": str|null,
     "symbol_counts": {since_current, earlier, since_unknown, unreleased, unknown},
     "dispositions": {surface: {"action": create|update|mention|none, "target": str|None,
                                "rationale": str, "status": pending|satisfied|none_justified,
                                "evidence_paths": [...], "placement": str|None}}}

  introduces_new_io_route (deterministic, generic): any of
     R1 a new enum constant on an EXISTING enum together with >= 1 new public type;
     R2/R5 >= 1 new format;
     R3 a new public type whose name tokens include one of io_route.type_tokens;
     R4 an attached added member whose name tokens include io_route.member_verbs and whose
        signature references a new type of the unit.

LEDGER FILE: JSON, sorted keys, indent 2, LF, schema_version 1; path convention
``reports/refresh_runs/<family>/<platform>/<run_id>/capability_ledger.json`` (caller chooses).
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path, PurePath
from typing import Any, Callable, Iterable

_LIB_DIR = Path(__file__).resolve().parent
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

import availability as _av  # noqa: E402

SCHEMA_VERSION = 1
SURFACES = ("reference", "docs", "kb", "blog", "products")
ACTIONS = ("create", "update", "mention", "none")
STATUSES = ("pending", "satisfied", "none_justified")
KINDS = ("route", "type-group", "api-extension", "format-route")

load_config = _av.load_config
configure = _av.configure
is_member_symbol = _av.is_member_symbol
simple_name = _av.simple_name
type_of_symbol = _av.type_of_symbol



# Every key of capability_placement.yaml that library or gate code reads. The code carries NO
# default for any of them: a missing key is a ConfigError naming it (M5, fail closed).
REQUIRED_KEYS: "tuple[tuple[str, ...], ...]" = (
    ("grouping", "token_affinity", "enabled"),
    ("grouping", "token_affinity", "min_token_length"),
    ("grouping", "token_affinity", "min_new_symbols_sharing"),
    ("grouping", "token_affinity", "max_existing_symbols_sharing"),
    ("grouping", "token_affinity", "generic_tokens"),
    ("internal_namespace_segments",),
    ("io_route", "type_tokens"),
    ("io_route", "member_verbs"),
    ("options", "type_tokens"),
    ("placement", "products", "dedicated_section", "min_public_types"),
    ("placement", "products", "dedicated_section", "min_public_members_without_route"),
    ("placement", "products", "dedicated_section", "require_verified_example"),
    ("placement", "products", "mention", "min_public_types"),
    ("placement", "products", "mention", "min_public_members"),
    ("placement", "products", "mention", "min_new_enum_constants"),
    ("placement", "products", "mention", "min_new_formats"),
    ("placement", "products", "block_match", "min_overlap"),
    ("placement", "reference", "create_min_public_types"),
    ("placement", "reference", "update_min_members_or_constants"),
    ("placement", "docs", "create_if_new_io_route"),
    ("placement", "docs", "create_min_public_types"),
    ("placement", "docs", "update_min_public_types"),
    ("placement", "docs", "update_min_public_members"),
    ("placement", "kb", "create_if_introduces_options"),
    ("placement", "kb", "create_if_new_io_route"),
    ("placement", "kb", "update_min_public_types"),
    ("placement", "blog", "create_kinds"),
    ("placement", "blog", "create_min_public_types"),
    ("placement", "blog", "create_min_new_formats"),
    ("satisfaction", "min_term_ratio", "reference"),
    ("satisfaction", "min_term_ratio", "docs"),
    ("satisfaction", "min_term_ratio", "kb"),
    ("satisfaction", "min_term_ratio", "blog"),
    ("satisfaction", "min_term_ratio", "products"),
    ("satisfaction", "directory_suffixes"),
    ("availability", "qualifier_phrases"),
    ("availability", "qualifier_negation_prefixes"),
    ("availability", "qualifier_window_chars"),
    ("availability", "tag_templates"),
    ("availability", "release_ref_keys"),
    ("availability", "coordinate_scan", "min_components_in_coordinate"),
    ("availability", "coordinate_scan", "version_pattern"),
    ("availability", "coordinate_scan", "coordinate_patterns"),
    ("availability", "coordinate_scan", "keyword_contexts"),
    ("availability", "coordinate_scan", "ignore_patterns"),
    ("availability", "coordinate_scan", "ignore_tool_names"),
)

ConfigError = _av.ConfigError

# What the symbol-only model can NOT see (static, documented -- never a data-dependent claim).
DELTA_KINDS_UNSEEN = ["behavioural", "changelog", "readme"]
KNOWN_LIMITS = [
    "method-name-keyed deltas cannot see a new overload of an existing method name",
    "behavioural, changelog and readme changes are outside the symbol-level delta",
]
ACTION_RANK = {"none": 0, "mention": 1, "update": 2, "create": 3}
WORTH_VALUES = ("internal", "public")


def missing_config_keys(config: "dict[str, Any] | None" = None) -> "list[str]":
    """Dotted names of every REQUIRED_KEYS entry absent (or null) in `config` (default: the file)."""
    root = config if config is not None else load_config()
    out = []
    for path in REQUIRED_KEYS:
        node: Any = root
        for key in path:
            node = node.get(key) if isinstance(node, dict) else None
            if node is None:
                out.append(".".join(path))
                break
    return out


def require_config(config: "dict[str, Any] | None" = None) -> "dict[str, Any]":
    """The config, or ConfigError naming every missing required key."""
    root = config if config is not None else load_config()
    missing = missing_config_keys(root)
    if missing:
        raise ConfigError("missing required config key " + ", ".join(missing))
    return root


class GroupingOverrideError(ValueError):
    """A reviewer grouping override names an unknown symbol or claims a symbol twice."""


# ── tokens ──────────────────────────────────────────────────────────────────────────────────────

_CAMEL = re.compile(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z]+|[A-Z]+|\d+")
_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def tokens(name: str) -> "list[str]":
    """Lower-case CamelCase / snake_case / digit tokens of an identifier."""
    out: "list[str]" = []
    for part in re.split(r"[^A-Za-z0-9]+", name or ""):
        out.extend(t.lower() for t in _CAMEL.findall(part))
    return out


def _norm(text: "str | None") -> str:
    return re.sub(r"[^a-z0-9]+", "", (text or "").casefold())


def _aff(cfg: "dict[str, Any]") -> "dict[str, Any]":
    return cfg["grouping"]["token_affinity"]


def _sig_tokens(name: str, cfg: "dict[str, Any]") -> "set[str]":
    a = _aff(cfg)
    min_len = int(a["min_token_length"])
    generic = {str(g).casefold() for g in a["generic_tokens"]}
    return {t for t in tokens(name) if len(t) >= min_len and t not in generic}


def unit_id(symbols: "Iterable[str]", formats: "Iterable[str]" = ()) -> str:
    """``CU-`` + 8 hex of a stable hash of the sorted qualified symbols (+ ``format:<name>``)."""
    basis = sorted({str(s) for s in symbols} | {f"format:{f}" for f in formats})
    return "CU-" + hashlib.sha256("\n".join(basis).encode("utf-8")).hexdigest()[:8]


# ── input normalisation / adapters ──────────────────────────────────────────────────────────────

def _split_qualified(q: str) -> "tuple[str, str]":
    if "::" in q:
        ns, name = q.split("::", 1)
        return ns, name
    return "", q


def _ns_key(ns: str) -> str:
    """Namespace used for structural grouping: a file-path qualifier reduces to its directory."""
    ns = ns.replace("\\", "/")
    if "/" in ns and "." in ns.rsplit("/", 1)[1]:  # looks like a source file path
        return ns.rsplit("/", 1)[0]
    return ns


def _is_internal(ns: str, cfg: "dict[str, Any]") -> bool:
    segs = {str(s).casefold() for s in cfg["internal_namespace_segments"]}
    return any(seg.casefold() in segs for seg in re.split(r"[./\\]+", ns) if seg)


def normalize_delta(api_delta: "dict[str, Any]") -> "dict[str, Any]":
    d = api_delta or {}
    gt = dict(d.get("ground_truth") or {})
    gt.setdefault("tier", None)
    gt.setdefault("symbol_level", True)
    unc = d.get("unconfirmed") or {}
    return {
        "schema_version": SCHEMA_VERSION,
        "added_types": [dict(t) for t in d.get("added_types") or []],
        "added_members": [dict(m) for m in d.get("added_members") or []],
        "enum_constants_added": [dict(c) for c in d.get("enum_constants_added") or []],
        "formats_added": [dict(f) for f in d.get("formats_added") or []],
        "name_collisions": [dict(c) for c in d.get("name_collisions") or []],
        "existing_symbols": None if d.get("existing_symbols") is None else [str(s) for s in d["existing_symbols"]],
        "public_surface_size": d.get("public_surface_size"),
        "ambiguous_resolved": int(d.get("ambiguous_resolved") or 0),
        "ground_truth": gt,
        "unconfirmed": {"breaking_unconfirmed": sorted(unc.get("breaking_unconfirmed") or []),
                        "extraction_drift_suspect": sorted(unc.get("extraction_drift_suspect") or [])},
    }


def _entry_member_count(e: "dict[str, Any]") -> int:
    return sum(len(_av._member_names(e, f)) for f in ("methods", "properties", "enum_members"))


def _member_refs(entry: "dict[str, Any] | None", name: str) -> "list[str]":
    refs: "set[str]" = set()
    for field in ("methods", "properties"):
        for m in (entry or {}).get(field) or []:
            if isinstance(m, dict) and m.get("name") == name:
                for p in m.get("params") or []:
                    refs.update(_IDENT.findall(str((p or {}).get("type") or "")))
                refs.update(_IDENT.findall(str(m.get("return_type") or "")))
                refs.update(_IDENT.findall(str(m.get("type") or "")))
    return sorted(refs)


def from_knowledge_delta(knowledge_delta: "dict[str, Any] | None", format_delta: "dict[str, Any] | None" = None, *,
                         api_surface: "list[dict[str, Any]] | None" = None,
                         adapter_delta: "dict[str, Any] | None" = None) -> "dict[str, Any]":
    """Build an api_delta from knowledge_delta.json (+ format_delta.json). `api_surface` is the NEW
    merged api_surface.json (optional): it supplies member counts, signature references,
    visibility (entries marked private/internal are dropped) and the existing-symbol universe.
    Without it member counts are 0, no signature attachment is possible and token affinity is
    skipped (existing_symbols None). Absent knowledge_delta keys are treated as empty."""
    kd = knowledge_delta or {}
    new_q = sorted({str(q) for q in kd.get("new_apis_qualified") or []})
    idx = {_av.qualified_name(e): e for e in (api_surface or []) if isinstance(e, dict) and "name" in e}

    def hidden(e: "dict[str, Any] | None") -> bool:
        return bool(e) and str(e.get("visibility") or "").casefold() in ("private", "internal")

    added_types = []
    for q in new_q:
        e = idx.get(q)
        if hidden(e):
            continue
        added_types.append({"qualified": q, "kind": (e or {}).get("kind"),
                            "member_count": _entry_member_count(e) if e else 0, "signature_refs": []})
    modified_by_simple: "dict[str, list[str]]" = {}
    for q in kd.get("modified_apis_qualified") or []:
        modified_by_simple.setdefault(_split_qualified(str(q))[1], []).append(str(q))
    members: "dict[tuple[str, str], dict[str, Any]]" = {}
    consts: "dict[tuple[str, str], dict[str, Any]]" = {}
    resolved = 0

    def owners_of(cands: "list[str]", member: str, fields: "tuple[str, ...]") -> "list[str]":
        return [c for c in cands if idx.get(c) and member in {n for f in fields for n in _av._member_names(idx[c], f)}]

    for name, sig in sorted((kd.get("api_signature_changes") or {}).items()):
        cands = sorted(modified_by_simple.get(name, []))
        owner = cands[0] if len(cands) == 1 else name
        entry = idx.get(owner)
        collide = len(cands) > 1 and any(c in idx for c in cands)

        def place(member: str, fields: "tuple[str, ...]") -> "tuple[str, list[str] | None]":
            """(owner, candidates-or-None) for one added member of a possibly colliding owner."""
            nonlocal resolved
            if not collide:
                return owner, None
            hit = owners_of(cands, member, fields)
            if len(hit) == 1:
                resolved += 1
                return hit[0], None
            return name, (hit if len(hit) > 1 else cands)

        for field in ("added_methods", "added_properties"):
            for m in sig.get(field) or []:
                o, oc = place(str(m), ("methods", "properties"))
                rec = {"owner": o, "name": str(m), "signature_refs": _member_refs(idx.get(o) or entry, str(m))}
                if oc:
                    rec["owner_candidates"] = oc
                members[(o, str(m))] = rec
        for c in sig.get("enum_members_added") or []:
            o, oc = place(str(c), ("enum_members",))
            rec = {"owner": o, "name": str(c)}
            if oc:
                rec["owner_candidates"] = oc
            consts[(o, str(c))] = rec
    formats = [{"name": f.get("name"), "ext": f.get("ext")}
               for f in sorted((format_delta or {}).get("formats_added") or [], key=lambda f: str(f.get("name")))]
    existing = None
    surface_size = None
    if api_surface is not None:
        new_set = set(new_q)
        existing = sorted(q for q, e in idx.items() if q not in new_set and not hidden(e))
        surface_size = sum(1 + _entry_member_count(e) for e in idx.values() if not hidden(e))
    bu = kd.get("breaking_unconfirmed")
    breaking = sorted(bu) if isinstance(bu, dict) else sorted(bu or kd.get("breaking_unconfirmed_apis") or [])
    suspects = sorted(str(s.get("qualified")) for s in kd.get("extraction_drift_suspect") or [] if s.get("qualified"))
    tier = (adapter_delta or {}).get("ground_truth_tier") or "KNOWLEDGE"
    return {
        "schema_version": SCHEMA_VERSION,
        "added_types": added_types,
        "added_members": [members[k] for k in sorted(members)],
        "enum_constants_added": [consts[k] for k in sorted(consts)],
        "formats_added": formats,
        "name_collisions": [dict(c) for c in kd.get("name_collisions") or []],
        "existing_symbols": existing,
        "public_surface_size": surface_size,
        "ambiguous_resolved": resolved,
        "ground_truth": {"tier": tier, "symbol_level": True},
        "unconfirmed": {"breaking_unconfirmed": breaking, "extraction_drift_suspect": suspects},
    }


def _compiled_qualified_name(t: str) -> str:
    return f"{t.rsplit('.', 1)[0]}::{t.rsplit('.', 1)[1]}" if "." in t else t


def _compiled_member_name(line: str) -> str:
    head = line.split("(", 1)[0] if "(" in line else line.rstrip(";")
    idents = _IDENT.findall(head)
    return idents[-1] if idents else ""


def from_adapter_delta(adapter_delta: "dict[str, Any] | None") -> "dict[str, Any]":
    """Build an api_delta from a lib/language_adapters result. GT-1 (compiled-API truth) yields
    symbols; GT-2 (file-level evidence) yields NO symbols and `symbol_level: false`."""
    ad = adapter_delta or {}
    tier = ad.get("ground_truth_tier")
    if tier != "GT-1":
        return normalize_delta({"ground_truth": {"tier": tier, "symbol_level": False}})
    types, members, consts = [], [], []
    for t in ad.get("added_types") or []:
        refs: "set[str]" = set()
        for line in t.get("member_list") or []:
            refs.update(_IDENT.findall(line))
        types.append({"qualified": _compiled_qualified_name(str(t["type"])), "kind": "enum" if t.get("is_enum") else "class",
                      "member_count": int(t.get("members") or 0), "signature_refs": sorted(refs)})
    for owner, ch in sorted((ad.get("changed_types") or {}).items()):
        oq = _compiled_qualified_name(owner)
        added_consts = set(ch.get("enum_constants_added") or [])
        for c in sorted(added_consts):
            consts.append({"owner": oq, "name": c})
        for line in ch.get("added") or []:
            name = _compiled_member_name(line)
            if name in added_consts and "(" not in line:
                continue
            members.append({"owner": oq, "name": name, "signature_refs": sorted(set(_IDENT.findall(line)))})
    return normalize_delta({"added_types": types, "added_members": members, "enum_constants_added": consts,
                            "ground_truth": {"tier": "GT-1", "symbol_level": True}})


# ── grouping ────────────────────────────────────────────────────────────────────────────────────

class _UF:
    def __init__(self, items: "Iterable[str]"):
        self.p = {i: i for i in items}

    def find(self, x: str) -> str:
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            lo, hi = sorted((ra, rb))
            self.p[hi] = lo


def _existing_stats(d: "dict[str, Any]", cfg: "dict[str, Any]") -> "tuple[Counter, list[str]] | None":
    if d["existing_symbols"] is None:
        return None
    freq: Counter = Counter()
    norms: "list[str]" = []
    for s in d["existing_symbols"]:
        nm = simple_name(s) if "::" in s or "." not in s else s.rsplit(".", 1)[-1]
        nm = _split_qualified(s)[1].split(".", 1)[0]
        for t in _sig_tokens(nm, cfg):
            freq[t] += 1
        norms.append(_norm(nm))
    return freq, norms


def group_units(api_delta: "dict[str, Any]", *, config: "dict[str, Any] | None" = None,
                grouping_overrides: "list[dict[str, Any]] | None" = None) -> "list[dict[str, Any]]":
    """Group a delta into capability units (see the module docstring). Returns units sorted by id,
    each with id/title/grouping/symbols/internal_symbols/enum_constants/formats and a private
    `_detail` used by build_ledger (stripped from the ledger)."""
    cfg = require_config(config)
    d = normalize_delta(api_delta)
    aff = _aff(cfg)
    min_len = int(aff["min_token_length"])
    max_existing = int(aff["max_existing_symbols_sharing"])
    min_new = int(aff["min_new_symbols_sharing"])
    stats = _existing_stats(d, cfg)
    affinity_on = bool(aff["enabled"]) and stats is not None
    freq, ex_norms = stats if stats else (Counter(), [])
    collision_names = {str(c.get("name")) for c in d["name_collisions"]}

    types: "dict[str, dict[str, Any]]" = {}
    for t in d["added_types"]:
        q = str(t["qualified"])
        ns, name = _split_qualified(q)
        types[q] = {"qualified": q, "name": name, "namespace": ns, "kind": t.get("kind"),
                    "member_count": int(t.get("member_count") or 0),
                    "signature_refs": sorted(set(t.get("signature_refs") or [])),
                    "internal": _is_internal(ns, cfg), "namespace_internal": _is_internal(ns, cfg)}
    by_simple: "dict[str, list[str]]" = {}
    for q, t in types.items():
        by_simple.setdefault(t["name"], []).append(q)

    def resolve_owner(owner: str) -> "tuple[str, bool]":
        if owner in types:
            return owner, True
        if "::" not in owner and len(by_simple.get(owner, [])) == 1 and owner not in collision_names:
            return by_simple[owner][0], True
        return owner, False

    members: "dict[str, dict[str, Any]]" = {}
    for m in d["added_members"]:
        owner, new = resolve_owner(str(m["owner"]))
        sym = f"{owner}.{m['name']}"
        members[sym] = {"symbol": sym, "owner": owner, "owner_is_new": new, "name": str(m["name"]),
                        "refs": sorted(set(m.get("signature_refs") or [])),
                        "candidates": sorted(f"{c}.{m['name']}" for c in m.get("owner_candidates") or [])}
    consts: "dict[str, dict[str, Any]]" = {}
    for c in d["enum_constants_added"]:
        owner, new = resolve_owner(str(c["owner"]))
        sym = f"{owner}.{c['name']}"
        consts[sym] = {"symbol": sym, "owner": owner, "owner_is_new": new, "name": str(c["name"]),
                       "candidates": sorted(f"{o}.{c['name']}" for o in c.get("owner_candidates") or [])}
    formats: "dict[str, dict[str, Any]]" = {}
    for f in d["formats_added"]:
        formats[f"format:{f['name']}"] = {"name": str(f["name"]), "ext": f.get("ext")}

    # (c) reviewer overrides -------------------------------------------------------------------
    claimed: "dict[str, int]" = {}
    overrides = list(grouping_overrides or [])
    known = set(types) | set(members) | set(consts) | set(formats)
    for i, ov in enumerate(overrides):
        for sym in ov.get("symbols") or []:
            if sym not in known:
                raise GroupingOverrideError(f"grouping override {ov.get('id') or i}: unknown symbol {sym!r}")
            if sym in claimed:
                raise GroupingOverrideError(f"grouping override {ov.get('id') or i}: symbol {sym!r} claimed twice "
                                            f"(also by override #{claimed[sym]})")
            claimed[sym] = i
    buckets: "dict[Any, dict[str, Any]]" = {}

    def bucket(key: Any, **kw: Any) -> "dict[str, Any]":
        b = buckets.setdefault(key, {"types": set(), "members": set(), "consts": set(), "formats": set(),
                                     "grouping": "draft", "title": None})
        for k, v in kw.items():
            b[k] = v
        return b

    type_unit: "dict[str, Any]" = {}
    for i, ov in enumerate(overrides):
        b = bucket(("ov", i), grouping="reviewed", title=ov.get("id"))
        for sym in ov.get("symbols") or []:
            if sym in types:
                b["types"].add(sym)
                type_unit[sym] = ("ov", i)
            elif sym in members:
                b["members"].add(sym)
            elif sym in consts:
                b["consts"].add(sym)
            else:
                b["formats"].add(sym)

    # (a)+(b) auto grouping of the remaining types ---------------------------------------------
    auto_types = sorted(q for q in types if q not in claimed)
    uf = _UF(auto_types)
    first_in_ns: "dict[str, str]" = {}
    for q in auto_types:
        key = _ns_key(types[q]["namespace"])
        if key in first_in_ns:
            uf.union(first_in_ns[key], q)
        else:
            first_in_ns[key] = q
    type_toks = {q: _sig_tokens(types[q]["name"], cfg) for q in auto_types}
    if affinity_on:
        carriers: "dict[str, list[str]]" = {}
        for q in auto_types:
            for t in type_toks[q]:
                carriers.setdefault(t, []).append(q)
        for t, qs in sorted(carriers.items()):
            if len(qs) >= min_new and freq.get(t, 0) <= max_existing:
                for other in qs[1:]:
                    uf.union(qs[0], other)
    for q in auto_types:
        type_unit[q] = ("auto", uf.find(q))

    def best(counts: Counter) -> Any:
        if not counts:
            return None
        top = max(counts.values())
        return sorted((k for k, v in counts.items() if v == top), key=repr)[0]

    # attach members ---------------------------------------------------------------------------
    unattached_members: "list[str]" = []
    for sym in sorted(members):
        if sym in claimed:
            continue
        m = members[sym]
        key = None
        if m["owner_is_new"]:
            key = type_unit.get(m["owner"])
        if key is None:
            counts: Counter = Counter()
            for q, t in types.items():
                if t["name"] in m["refs"] and q in type_unit:
                    counts[type_unit[q]] += 1
            key = best(counts)
        if key is None and affinity_on:
            mt = {t for t in _sig_tokens(m["name"], cfg) if freq.get(t, 0) <= max_existing}
            counts = Counter()
            for q in auto_types:
                shared = mt & type_toks[q]
                if shared:
                    counts[type_unit[q]] += len(shared)
            key = best(counts)
        if key is None:
            unattached_members.append(sym)
        else:
            bucket(key)["members"].add(sym)

    def key_match(keys: "set[str]") -> Any:
        counts: Counter = Counter()
        for k in keys:
            if len(k) < min_len or sum(1 for n in ex_norms if k in n) > max_existing:
                continue
            for q in auto_types:
                if k in _norm(types[q]["name"]):
                    counts[type_unit[q]] += 1
        return best(counts)

    unattached_consts: "list[str]" = []
    for sym in sorted(consts):
        if sym in claimed:
            continue
        c = consts[sym]
        key = type_unit.get(c["owner"]) if c["owner_is_new"] else None
        if key is None and affinity_on:
            key = key_match({_norm(c["name"])})
        if key is None:
            unattached_consts.append(sym)
        else:
            bucket(key)["consts"].add(sym)

    def format_keys(f: "dict[str, Any]") -> "set[str]":
        return {k for k in (_norm((f.get("ext") or "").lstrip(".")), _norm(f.get("name"))) if k}

    unattached_formats: "list[str]" = []
    for sym in sorted(formats):
        if sym in claimed:
            continue
        key = key_match(format_keys(formats[sym])) if affinity_on else None
        if key is None:
            unattached_formats.append(sym)
        else:
            bucket(key)["formats"].add(sym)

    # standalone leftovers ---------------------------------------------------------------------
    for sym in unattached_members:
        bucket(("ext", members[sym]["owner"]))["members"].add(sym)
    const_keys: "dict[Any, set[str]]" = {}
    for sym in unattached_consts:
        key = ("enum", consts[sym]["owner"])
        bucket(key)["consts"].add(sym)
        const_keys.setdefault(key, set()).add(_norm(consts[sym]["name"]))
    leftover_formats = []
    for sym in unattached_formats:
        fk = format_keys(formats[sym])
        target = next((k for k in sorted(const_keys, key=repr) if fk & const_keys[k]), None)
        if target is None:
            leftover_formats.append(sym)
        else:
            bucket(target)["formats"].add(sym)
    for sym in leftover_formats:
        bucket(("formats",))["formats"].add(sym)
    for q in auto_types:
        bucket(type_unit[q])["types"].add(q)

    # assemble ---------------------------------------------------------------------------------
    units = []
    for key, b in buckets.items():
        if not (b["types"] or b["members"] or b["consts"] or b["formats"]):
            continue
        symbols = sorted(b["types"] | b["members"] | b["consts"])
        fmt_names = sorted(formats[s]["name"] for s in b["formats"])
        internal = sorted(q for q in b["types"] if types[q]["internal"])
        title = b["title"] or _title(sorted(types[q]["name"] for q in b["types"]),
                                     sorted({members[s]["owner"] for s in b["members"]}),
                                     sorted({consts[s]["owner"] for s in b["consts"]}), fmt_names)
        units.append({
            "id": unit_id(symbols, fmt_names), "title": title, "grouping": b["grouping"], "symbols": symbols,
            "internal_symbols": internal, "enum_constants": sorted(b["consts"]), "formats": fmt_names,
            "ambiguous_symbols": [{"symbol": sy, "candidates": (members.get(sy) or consts[sy])["candidates"]}
                                  for sy in sorted(b["members"] | b["consts"])
                                  if (members.get(sy) or consts.get(sy) or {}).get("candidates")],
            "_detail": {"types": {q: types[q] for q in sorted(b["types"])},
                        "members": {s: members[s] for s in sorted(b["members"])},
                        "consts": {s: consts[s] for s in sorted(b["consts"])},
                        "formats": {formats[s]["name"]: formats[s] for s in sorted(b["formats"])}},
        })
    return sorted(units, key=lambda u: u["id"])


def _title(type_names: "list[str]", member_owners: "list[str]", const_owners: "list[str]",
           formats: "list[str]") -> str:
    def short(items: "list[str]", n: int = 3) -> str:
        shown = ", ".join(items[:n])
        return shown + (f" (+{len(items) - n} more)" if len(items) > n else "")

    if type_names:
        return "New: " + short(type_names)
    if const_owners:
        return "New values for " + short([_split_qualified(o)[1] for o in const_owners]) + (
            "; formats: " + short(formats) if formats else "")
    if formats:
        return "New formats: " + short(formats)
    return "Additions to " + short([_split_qualified(o)[1] for o in member_owners])


# ── scale ───────────────────────────────────────────────────────────────────────────────────────

def compute_scale(unit: "dict[str, Any]", *, config: "dict[str, Any]", public_surface_size: "int | None" = None,
                  verified_example_symbols: "Iterable[str] | None" = None,
                  snippet_index: "dict[str, list[str]] | None" = None) -> "dict[str, Any]":
    """Scale of one unit (uses unit['_detail']; members/constants flagged `excluded` by a worth
    override do not count, types flagged internal count as internal)."""
    require_config(config)
    det = unit["_detail"]
    public = {q: t for q, t in det["types"].items() if not t["internal"]}
    internal = {q: t for q, t in det["types"].items() if t["internal"]}
    ext_members = [m for m in det["members"].values() if not m["owner_is_new"] and not m.get("excluded")]
    ext_consts = [c for c in det["consts"].values() if not c["owner_is_new"] and not c.get("excluded")]
    io = config["io_route"]
    type_tokens = {str(t).casefold() for t in io["type_tokens"]}
    verbs = {str(t).casefold() for t in io["member_verbs"]}
    opt_tokens = {str(t).casefold() for t in config["options"]["type_tokens"]}
    new_members = sum(t["member_count"] for t in public.values()) + len(ext_members)
    public_names = {t["name"] for t in public.values()}
    route = bool(
        (ext_consts and public)                                                     # R1
        or det["formats"]                                                           # R2 / R5
        or any(set(tokens(t["name"])) & type_tokens for t in public.values())       # R3
        or any(set(tokens(m["name"])) & verbs and public_names & set(m["refs"])     # R4
               for m in ext_members))
    types_total = len(det["types"])
    if types_total:
        kind = "route" if route else "type-group"
    elif det["consts"] or det["formats"]:
        kind = "format-route"
    else:
        kind = "api-extension"
    if verified_example_symbols is None:
        verified: "bool | None" = None
    else:
        vs = {str(s) for s in verified_example_symbols}
        verified = any(q in vs or t["name"] in vs for q, t in det["types"].items()) or any(
            s in vs for s in unit["symbols"])
    snippets: "set[str]" = set()
    for q, t in det["types"].items():
        snippets.update((snippet_index or {}).get(t["name"], []))
        snippets.update((snippet_index or {}).get(q, []))
    return {
        "kind": kind,
        "new_public_types": len(public),
        "new_internal_types": len(internal),
        "new_public_members": new_members,
        "new_enum_constants": len(ext_consts),
        "new_formats": len(det["formats"]),
        "introduces_new_io_route": route,
        "introduces_options_type": any(set(tokens(t["name"])) & opt_tokens for t in public.values()),
        "share_of_public_surface": (round((len(public) + new_members) / public_surface_size, 6)
                                    if public_surface_size else None),
        "verified_example_present": verified,
        "snippet_candidates": sorted(snippets),
    }


# ── placement ───────────────────────────────────────────────────────────────────────────────────

def _disposition(action: str, target: "str | None", rationale: str, *, placement: "str | None" = None) -> "dict[str, Any]":
    return {"action": action, "target": target, "rationale": rationale,
            "status": "none_justified" if action == "none" else "pending",
            "evidence_paths": [], "placement": placement,
            "computed_action": action, "computed_placement": placement}


def _term_tokens(terms: "Iterable[str]", config: "dict[str, Any]") -> "set[str]":
    out: "set[str]" = set()
    for t in terms:
        out |= _sig_tokens(t, config)
    return out


def match_block(unit_terms: "Iterable[str]", candidate_blocks: "list[dict[str, Any]]",
                config: "dict[str, Any]") -> "dict[str, Any] | None":
    """The existing block with the highest token overlap (>= block_match.min_overlap), ties broken
    by (path, id); None when nothing qualifies."""
    need = int(config["placement"]["products"]["block_match"]["min_overlap"])
    ut = _term_tokens(unit_terms, config)
    scored = []
    for b in candidate_blocks or []:
        overlap = len(ut & _term_tokens(b.get("terms") or [], config))
        if overlap >= max(need, 1):
            scored.append((-overlap, str(b.get("path")), str(b.get("id") or ""), b))
    if not scored:
        return None
    return sorted(scored, key=lambda s: s[:3])[0][3]


def decide_products(scale: "dict[str, Any]", *, unit_terms: "Iterable[str]", candidate_blocks: "list[dict[str, Any]]",
                    config: "dict[str, Any]", new_section_target: "str | None" = None) -> "dict[str, Any]":
    """Products-surface decision (FROZEN initial values in capability_placement.yaml):
    dedicated_section iff types >= 5 AND (route OR members >= 15) AND a verified example is
    present; mention iff types >= 1 OR members >= 3 OR new enum constants (OR formats); else none.
    A mention without a matching existing block is `unplaced` -- never promoted."""
    p = config["placement"]["products"]
    ded, men = p["dedicated_section"], p["mention"]
    t, m = scale["new_public_types"], scale["new_public_members"]
    if (t >= ded["min_public_types"]
            and (scale["introduces_new_io_route"] or m >= ded["min_public_members_without_route"])
            and (scale["verified_example_present"] is True or not ded["require_verified_example"])):
        return _disposition("create", new_section_target,
                            f"products dedicated section: {t} new public types, route={scale['introduces_new_io_route']}, "
                            f"{m} new public members, verified example present", placement="dedicated_section")
    if (t >= men["min_public_types"] or m >= men["min_public_members"]
            or scale["new_enum_constants"] >= men["min_new_enum_constants"]
            or scale["new_formats"] >= men["min_new_formats"]):
        block = match_block(unit_terms, candidate_blocks, config)
        why = (f"products mention: {t} new public types, {m} new public members, "
               f"{scale['new_enum_constants']} new enum constants, {scale['new_formats']} new formats")
        if block is None:
            return _disposition("mention", None, why + "; no existing block matches -> UNPLACED (hard fail at the gate)",
                                placement="unplaced")
        target = str(block.get("path")) + (f"#{block['id']}" if block.get("id") else "")
        return _disposition("mention", target, why + f"; target = best-overlap block {target}", placement="mention")
    return _disposition("none", None, f"below the products mention threshold ({t} types, {m} members, "
                        f"{scale['new_enum_constants']} enum constants, {scale['new_formats']} formats)")


def decide_dispositions(scale: "dict[str, Any]", *, kind: str, unit_terms: "Iterable[str]",
                        surface_targets: "dict[str, str] | None", candidate_blocks: "list[dict[str, Any]]",
                        config: "dict[str, Any]") -> "dict[str, dict[str, Any]]":
    """The five surface decisions for one unit; every threshold comes from the config."""
    pl = require_config(config)["placement"]
    tg = surface_targets or {}
    t, m = scale["new_public_types"], scale["new_public_members"]
    consts, formats = scale["new_enum_constants"], scale["new_formats"]
    ref, docs, kb, blog = pl["reference"], pl["docs"], pl["kb"], pl["blog"]
    if t == 0 and scale["new_internal_types"] >= 1 and m == 0 and consts == 0 and formats == 0:
        out = {"reference": _disposition("create", tg.get("reference"),
                                         f"{scale['new_internal_types']} internal-looking new type(s): reference-only")}
        for s in ("docs", "kb", "blog", "products"):
            out[s] = _disposition("none", None, "none_justified:internal -- every new type matches an internal "
                                  "namespace pattern or is marked internal; documented in the reference surface only")
        return out
    out = {}
    if t >= ref["create_min_public_types"]:
        out["reference"] = _disposition("create", tg.get("reference"), f"{t} new public type(s): reference pages are mechanical")
    elif m + consts >= ref["update_min_members_or_constants"]:
        out["reference"] = _disposition("update", tg.get("reference"),
                                        f"{m} new member(s) / {consts} new enum constant(s) on existing types")
    else:
        out["reference"] = _disposition("none", None, "no new API symbols (formats only): nothing for a reference page")
    if (docs["create_if_new_io_route"] and scale["introduces_new_io_route"]) or t >= docs["create_min_public_types"]:
        out["docs"] = _disposition("create", tg.get("docs"),
                                   f"docs: new I/O route={scale['introduces_new_io_route']} or {t} >= "
                                   f"{docs['create_min_public_types']} new public types")
    elif t >= docs["update_min_public_types"] or m >= docs["update_min_public_members"]:
        out["docs"] = _disposition("update", tg.get("docs"), f"docs: {t} new public types / {m} new public members")
    else:
        out["docs"] = _disposition("none", None, f"docs: only {t} new public types / {m} new public members")
    if (kb["create_if_introduces_options"] and scale["introduces_options_type"]) or (
            kb["create_if_new_io_route"] and scale["introduces_new_io_route"]):
        out["kb"] = _disposition("create", tg.get("kb"), "kb: unit introduces options/knobs or a new I/O route")
    elif t >= kb["update_min_public_types"]:
        out["kb"] = _disposition("update", tg.get("kb"), f"kb: {t} new public types, no options or route")
    else:
        out["kb"] = _disposition("none", None, "kb: no new public type, options or route")
    if kind in blog["create_kinds"] and (
            t >= blog["create_min_public_types"] or formats >= blog["create_min_new_formats"]):
        out["blog"] = _disposition("create", tg.get("blog"), f"blog: {kind} unit with {t} new public types / {formats} formats")
    else:
        out["blog"] = _disposition("none", None, f"blog: kind={kind} with {t} new public types / {formats} formats is below "
                                   "the blog threshold")
    out["products"] = decide_products(scale, unit_terms=unit_terms, candidate_blocks=candidate_blocks, config=config,
                                      new_section_target=tg.get("products"))
    return out


# ── ledger ──────────────────────────────────────────────────────────────────────────────────────

def _state_of(v: Any) -> "str | None":
    return v.get("state") if isinstance(v, dict) else v


def _combine_candidates(candidates: "list[str]", infos: "dict[str, dict[str, Any]]") -> "dict[str, Any]":
    """One availability info for an ambiguous member symbol: released iff EVERY candidate is
    released (since = the current-release version when any candidate is new in it, the earlier one
    when all are earlier, None when undetermined); unknown otherwise."""
    cand = [infos.get(c) or {"state": _av.UNKNOWN} for c in candidates]
    if not cand or any(i.get("state") != _av.RELEASED for i in cand):
        return {"state": _av.UNKNOWN, "available_since": None, "since_basis": "n/a"}
    if any(i.get("available_since") is None for i in cand):
        return {"state": _av.RELEASED, "available_since": None, "since_basis": "ambiguous_previous"}
    current = [i for i in cand if i.get("since_basis") != "previous"]
    return dict(current[0] if current else cand[0])


def _flags(unit: "dict[str, Any]", d: "dict[str, Any]") -> "list[str]":
    det = unit["_detail"]
    flags: "set[str]" = set()
    tier = (d["ground_truth"] or {}).get("tier")
    if tier == "GT-2":
        flags.add("ground_truth:GT-2")
    collisions = {str(c.get("name")) for c in d["name_collisions"]}
    owners = {m["owner"] for m in det["members"].values()} | {c["owner"] for c in det["consts"].values()}
    names = {t["name"] for t in det["types"].values()} | {_split_qualified(o)[1] for o in owners}
    for n in sorted(names & collisions):
        flags.add(f"name_collision:{n}")
    suspects = set(d["unconfirmed"]["extraction_drift_suspect"])
    for o in sorted(owners):
        if o in suspects:
            flags.add(f"extraction_drift_suspect:{o}")
    breaking = set(d["unconfirmed"]["breaking_unconfirmed"])
    for o in sorted(owners):
        if _split_qualified(o)[1] in breaking:
            flags.add(f"breaking_unconfirmed:{_split_qualified(o)[1]}")
    return sorted(flags)


def _unit_terms(unit: "dict[str, Any]") -> "list[str]":
    det = unit["_detail"]
    terms = [t["name"] for t in det["types"].values()]
    for c in det["consts"].values():
        terms += [c["name"], _split_qualified(c["owner"])[1]]
    for f in det["formats"].values():
        terms += [f["name"], str(f.get("ext") or "").lstrip(".")]
    for m in det["members"].values():
        terms += [m["name"], _split_qualified(m["owner"])[1]]
    return [t for t in terms if t]


def config_digest(cfg: "dict[str, Any]") -> str:
    """sha256 of the canonical JSON of the whole placement config (what a ledger was built with)."""
    return hashlib.sha256(json.dumps(cfg, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def delta_fingerprint(api_delta: "dict[str, Any]") -> str:
    """sha256 of the content-bearing part of a delta (new types, added members, new enum constants,
    new formats), order independent. The empty delta has the fixed value empty_delta_sha256()."""
    d = normalize_delta(api_delta)
    basis = {
        "added_types": sorted([str(t["qualified"]), int(t.get("member_count") or 0)] for t in d["added_types"]),
        "added_members": sorted([str(m["owner"]), str(m["name"])] for m in d["added_members"]),
        "enum_constants_added": sorted([str(c["owner"]), str(c["name"])] for c in d["enum_constants_added"]),
        "formats_added": sorted(str(f["name"]) for f in d["formats_added"]),
    }
    return hashlib.sha256(json.dumps(basis, sort_keys=True).encode("utf-8")).hexdigest()


def empty_delta_sha256() -> str:
    return delta_fingerprint({})


def _apply_worth_to_detail(detail: "dict[str, Any]", symbol_worth: "dict[str, Any]") -> None:
    """Fold per-symbol worth into a unit detail: a type is internal when its namespace says so unless a
    worth entry overrides it; a member / constant marked internal is excluded from the scale."""
    for q, t in detail["types"].items():
        w = (symbol_worth.get(q) or {}).get("worth")
        t["internal"] = bool(t.get("namespace_internal", t["internal"])) if w is None else (w == "internal")
    for key in ("members", "consts"):
        for sym, m in detail[key].items():
            m["excluded"] = (symbol_worth.get(sym) or {}).get("worth") == "internal"


def _parse_worth(overrides: "Iterable[dict[str, Any]] | None", known: "set[str]") -> "dict[str, dict[str, str]]":
    out: "dict[str, dict[str, str]]" = {}
    for ov in overrides or []:
        sym, worth, reason = ov.get("symbol"), ov.get("worth"), str(ov.get("reason") or "").strip()
        if sym not in known:
            raise ValueError(f"worth override: unknown symbol {sym!r}")
        if worth not in WORTH_VALUES:
            raise ValueError(f"worth override {sym!r}: worth must be one of {WORTH_VALUES}, got {worth!r}")
        if not reason:
            raise ValueError(f"worth override {sym!r}: a non-empty reason is required")
        out[sym] = {"worth": worth, "reason": reason}
    return out


def build_ledger(api_delta: "dict[str, Any]", *, family: str, platform: str, upstream_head: "str | None" = None,
                 config: "dict[str, Any] | None" = None, surface_targets: "dict[str, str] | None" = None,
                 candidate_blocks: "list[dict[str, Any]] | None" = None,
                 grouping_overrides: "list[dict[str, Any]] | None" = None,
                 availability: "dict[str, Any] | None" = None,
                 availability_context: "dict[str, Any] | None" = None,
                 verified_example_symbols: "Iterable[str] | None" = None,
                 snippet_index: "dict[str, list[str]] | None" = None,
                 meta: "dict[str, Any] | None" = None,
                 base_sha: "str | None" = None, base_knowledge_commit: "str | None" = None,
                 worth_overrides: "list[dict[str, Any]] | None" = None) -> "dict[str, Any]":
    """Build the disposition ledger. `availability` maps symbol -> state (or {state, reason});
    `verified_example_symbols` is None at plan time (verified_example_present stays None).
    `base_sha` / `base_knowledge_commit` record where the cumulative delta STARTS (the previously
    propagated head / knowledge commit); the gate refuses a ledger whose base is not the recorded one.
    `worth_overrides` = [{symbol, worth: internal|public, reason}] marks helper symbols internal."""
    cfg = require_config(config)
    d = normalize_delta(api_delta)
    units = group_units(d, config=cfg, grouping_overrides=grouping_overrides)
    all_symbols = {s for u in units for s in u["symbols"]}
    worth = _parse_worth(worth_overrides, all_symbols)
    infos = {s: (v if isinstance(v, dict) else {"state": v}) for s, v in (availability or {}).items()}
    ctx = dict(availability_context or {})
    out_units = []
    totals = {"since_current": 0, "earlier": 0, "since_unknown": 0, "unreleased": 0, "unknown": 0}
    for u in units:
        sw = {sym: dict(worth[sym]) for sym in u["symbols"] if sym in worth}
        _apply_worth_to_detail(u["_detail"], sw)
        u["internal_symbols"] = sorted(q for q, t in u["_detail"]["types"].items() if t["internal"])
        sc = compute_scale(u, config=cfg, public_surface_size=d["public_surface_size"],
                           verified_example_symbols=verified_example_symbols, snippet_index=snippet_index)
        kind = sc.pop("kind")
        disp = decide_dispositions(sc, kind=kind, unit_terms=_unit_terms(u), surface_targets=surface_targets,
                                   candidate_blocks=candidate_blocks or [], config=cfg)
        amb = {a["symbol"]: a["candidates"] for a in u["ambiguous_symbols"]}
        unit_infos = [_combine_candidates(amb[sym], infos) if sym in amb else infos.get(sym) or {"state": _av.UNKNOWN}
                      for sym in u["symbols"]]
        unit_avail = _av.unit_availability(i.get("state") for i in unit_infos)
        since = _av.unit_since(unit_infos, version=ctx.get("release_version"),
                               previous_version=ctx.get("previous_release_version"))
        for k, n in since["counts"].items():
            totals[k] += n
        released = unit_avail == _av.RELEASED
        out_units.append({
            "id": u["id"], "title": u["title"], "kind": kind, "grouping": u["grouping"], "symbols": u["symbols"],
            "internal_symbols": u["internal_symbols"], "enum_constants": u["enum_constants"], "formats": u["formats"],
            "ambiguous_symbols": u["ambiguous_symbols"],
            "scale": sc,
            "availability": unit_avail,
            "available_since": since["available_since"] if released else None,
            "partial_earlier": bool(since["partial_earlier"]) if released else False,
            "release_version": ctx.get("release_version"),
            "symbol_counts": since["counts"],
            "unconfirmed_flags": _flags(u, d),
            "symbol_worth": sw,
            "scale_inputs": copy.deepcopy(u["_detail"]),
            "dispositions": {s: disp[s] for s in SURFACES},
        })
    notes = []
    if d["existing_symbols"] is None:
        notes.append("existing symbols unknown: token-affinity grouping skipped")
    if not (d["ground_truth"] or {}).get("symbol_level", True):
        notes.append("ground truth is not symbol-level (GT-2 file evidence only): no capability units can be derived")
    if availability is not None:
        ctx.setdefault("symbol_counts", {**totals, "ambiguous_resolved": d["ambiguous_resolved"]})
    return {
        "schema_version": SCHEMA_VERSION,
        "family": family, "platform": platform, "upstream_head": upstream_head,
        "ground_truth_tier": (d["ground_truth"] or {}).get("tier"),
        "symbol_level": bool((d["ground_truth"] or {}).get("symbol_level", True)),
        "config_sha256": config_digest(cfg),
        "delta_sha256": delta_fingerprint(d),
        "delta_symbol_count": sum(len(u["symbols"]) + len(u["formats"]) for u in out_units),
        "base_sha": base_sha, "base_knowledge_commit": base_knowledge_commit,
        "public_surface_size": d["public_surface_size"],
        "delta_kinds_unseen": list(DELTA_KINDS_UNSEEN),
        "known_limits": list(KNOWN_LIMITS),
        "availability_context": dict(sorted(ctx.items())),
        "declared_shared_symbols": [],
        "notes": notes,
        "meta": dict(sorted((meta or {}).items())),
        "units": sorted(out_units, key=lambda x: x["id"]),
    }


def dump_ledger(ledger: "dict[str, Any]") -> str:
    return json.dumps(ledger, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def write_ledger(path: "Path | str", ledger: "dict[str, Any]") -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(dump_ledger(ledger))


def load_ledger(path: "Path | str") -> "dict[str, Any]":
    return json.loads(Path(path).read_text(encoding="utf-8"))


STAGES = ("plan", "close")


def validate_ledger(ledger: "dict[str, Any]", *, stage: str = "close",
                    config: "dict[str, Any] | None" = None) -> "list[str]":
    """Completeness errors of a ledger (sorted; [] = complete). See validate_ledger_ex."""
    return validate_ledger_ex(ledger, stage=stage, config=config)[0]


def _override_ok(ov: Any) -> bool:
    return (isinstance(ov, dict) and isinstance(ov.get("token_id"), str) and ov["token_id"].strip() != ""
            and isinstance(ov.get("reason"), str) and ov["reason"].strip() != "")


def validate_ledger_ex(ledger: "dict[str, Any]", *, stage: str = "close",
                       config: "dict[str, Any] | None" = None) -> "tuple[list[str], list[str]]":
    """(errors, warnings), both sorted.

    stage='close' (default, the original behaviour): schema_version, deterministic ids, no
    duplicate symbols across units unless declared, every unit x surface present with a valid
    action/status, a target for create/update/mention, a non-empty rationale for none, no
    `unplaced` decision, no 'satisfied' claim without evidence -- all errors.
    stage='plan': targets are not known yet, so a missing target and an `unplaced` mention are
    WARNINGS, not errors; everything else is still an error."""
    if stage not in STAGES:
        raise ValueError(f"stage must be one of {STAGES}, got {stage!r}")
    errs: "list[str]" = []
    warns: "list[str]" = []
    soft = warns if stage == "plan" else errs
    for key in missing_config_keys(config):
        errs.append(f"missing required config key {key}")
    if ledger.get("schema_version") != SCHEMA_VERSION:
        errs.append(f"schema_version must be {SCHEMA_VERSION}, got {ledger.get('schema_version')!r}")
    declared = set(ledger.get("declared_shared_symbols") or [])
    seen: "dict[str, str]" = {}
    for u in ledger.get("units") or []:
        uid = u.get("id")
        expect = unit_id(u.get("symbols") or [], u.get("formats") or [])
        if uid != expect:
            errs.append(f"unit {uid}: id does not match its symbols (expected {expect})")
        for s in u.get("symbols") or []:
            if s in seen and s not in declared:
                errs.append(f"duplicate symbol {s} in units {seen[s]} and {uid} (declare it in declared_shared_symbols)")
            seen.setdefault(s, str(uid))
        if u.get("availability") not in _av.STATES:
            errs.append(f"unit {uid}: availability must be one of {_av.STATES}, got {u.get('availability')!r}")
        since = u.get("available_since")
        if since is not None and (not isinstance(since, str) or u.get("availability") != _av.RELEASED):
            errs.append(f"unit {uid}: available_since is only valid (a string) on a released unit, got {since!r} "
                        f"with availability {u.get('availability')!r}")
        for amb in u.get("ambiguous_symbols") or []:
            if (not isinstance(amb, dict) or amb.get("symbol") not in (u.get("symbols") or [])
                    or not isinstance(amb.get("candidates"), list) or not amb["candidates"]):
                errs.append(f"unit {uid}: malformed ambiguous_symbols entry {amb!r} (needs a symbol of the unit and "
                            "a non-empty candidates list)")
        for sym, w in (u.get("symbol_worth") or {}).items():
            if (not isinstance(w, dict) or w.get("worth") not in WORTH_VALUES or sym not in (u.get("symbols") or [])
                    or not str(w.get("reason") or "").strip()):
                errs.append(f"unit {uid}: malformed symbol_worth entry for {sym!r}")
        if not isinstance(u.get("partial_earlier", False), bool):
            errs.append(f"unit {uid}: partial_earlier must be a boolean")
        if u.get("grouping") not in ("draft", "reviewed"):
            errs.append(f"unit {uid}: grouping must be draft|reviewed")
        disp = u.get("dispositions") or {}
        for extra in sorted(set(disp) - set(SURFACES)):
            errs.append(f"unit {uid}: unknown surface {extra!r}")
        for surface in SURFACES:
            d = disp.get(surface)
            where = f"unit {uid} surface {surface}"
            if not isinstance(d, dict):
                errs.append(f"{where}: disposition missing")
                continue
            action, status = d.get("action"), d.get("status")
            if action not in ACTIONS:
                errs.append(f"{where}: action must be one of {ACTIONS}, got {action!r}")
                continue
            comp = d.get("computed_action")
            if comp is not None:
                if comp not in ACTIONS:
                    errs.append(f"{where}: computed_action must be one of {ACTIONS}, got {comp!r}")
                elif ACTION_RANK[action] < ACTION_RANK[comp] and not _override_ok(d.get("override")):
                    errs.append(f"{where}: action {action!r} is weaker than computed_action {comp!r} without a valid "
                                "override {token_id, reason}")
            if d.get("override") is not None and not _override_ok(d.get("override")):
                errs.append(f"{where}: malformed override (needs non-empty token_id and reason)")
            if status not in STATUSES:
                errs.append(f"{where}: status must be one of {STATUSES}, got {status!r}")
            if action == "none":
                if status != "none_justified":
                    errs.append(f"{where}: action none requires status none_justified")
                if not str(d.get("rationale") or "").strip():
                    errs.append(f"{where}: action none requires a non-empty rationale")
            else:
                if status == "none_justified":
                    errs.append(f"{where}: status none_justified is only valid with action none")
                if d.get("placement") == "unplaced":
                    soft.append(f"{where}: unplaced -- no existing block matches this mention (never silently promoted)")
                elif not str(d.get("target") or "").strip():
                    soft.append(f"{where}: action {action} requires a target")
                if status == "satisfied" and not d.get("evidence_paths"):
                    errs.append(f"{where}: status satisfied claimed without evidence_paths")
    return sorted(errs), sorted(warns)


# ── close-time satisfaction ─────────────────────────────────────────────────────────────────────

def _default_reader(path: PurePath) -> "str | None":
    p = Path(path)
    if not p.is_file():
        return None
    return p.read_text(encoding="utf-8", errors="replace")


def _default_lister(path: PurePath) -> "list[PurePath]":
    p = Path(path)
    return sorted(q for q in p.rglob("*") if q.is_file()) if p.is_dir() else []


def _rel(path: PurePath, root: PurePath) -> str:
    try:
        return path.relative_to(root).as_posix()
    except (ValueError, TypeError, AttributeError):
        return PurePath(path).as_posix()


def unit_terms_from_symbols(unit: "dict[str, Any]") -> "list[str]":
    """Terms a page must mention: type names; else enum constants; else formats; else members."""
    types = sorted({simple_name(s) for s in unit.get("symbols") or [] if not is_member_symbol(s)})
    if types:
        return types
    consts = sorted({simple_name(s) for s in unit.get("enum_constants") or []})
    if consts:
        return consts
    if unit.get("formats"):
        return sorted(unit["formats"])
    return sorted({simple_name(s) for s in unit.get("symbols") or []})


def _pa() -> Any:
    """propagation_analyzer, imported lazily (it imports this module): its frontmatter stripper,
    locale rules and code-span regexes are the single shared implementation."""
    import propagation_analyzer as pa
    return pa


def strip_frontmatter(text: str) -> str:
    """The page body: the YAML/TOML frontmatter block (internal metadata) removed."""
    return _pa().strip_frontmatter(text)


_DRAFT_RE = re.compile(r"^\s*draft\s*[:=]\s*true\s*(?:#.*)?$", re.IGNORECASE | re.MULTILINE)


def locale_codes(roots: "Iterable[PurePath]") -> "set[str]":
    """Locale codes whose pages are never English evidence: the analyzer's configured codes plus the
    locale directories found under a real content root."""
    pa = _pa()
    crit = pa.load_criteria()
    codes = {str(c).casefold() for c in crit["scan"]["locale_codes"]}
    for r in roots:
        try:
            codes |= pa.discover_locale_codes(Path(r), crit)
        except OSError:
            pass
    codes.discard("en")
    return codes


def evidence_page(rel: str, text: str, locales: "set[str]") -> "tuple[str | None, str | None]":
    """(body, None) when `text` may count as evidence, else (None, reason): reason is
    locale-suffixed | locale-directory | draft. The body has its frontmatter stripped."""
    pa = _pa()
    parts = rel.replace("\\", "/").split("/")
    if pa._is_locale_file(parts[-1], locales):
        return None, "locale-suffixed"
    if any(seg.casefold() in locales for seg in parts[:-1]):
        return None, "locale-directory"
    body = pa.strip_frontmatter(text)
    if _DRAFT_RE.search(text[:len(text) - len(body)]):
        return None, "draft"
    return body, None


def _code_spans(body: str) -> "list[tuple[int, int]]":
    pa = _pa()
    return [m.span() for rx in (pa._FENCE_RE, pa._INLINE_RE) for m in rx.finditer(body)]


def find_mentions(body: str, term: str) -> "list[tuple[int, int]]":
    """Spans where `term` is mentioned as an IDENTIFIER: case-sensitive, word-bounded. A common-word
    symbol (a single plain word -- no inner capital, digit or underscore) counts only inside a code
    span / fence or qualified (`ns.Name`, `ns::Name`)."""
    pa = _pa()
    spans = [m.span() for m in re.finditer(rf"(?<![A-Za-z0-9_]){re.escape(term)}(?![A-Za-z0-9_])", body)]
    if pa._is_strong(term):
        return spans
    code = _code_spans(body)
    out = []
    for a, b in spans:
        qualified = (a >= 2 and body[a - 2:a] == "::") or (a >= 2 and body[a - 1] == "." and body[a - 2].isalnum())
        if qualified or any(c0 <= a and b <= c1 for c0, c1 in code):
            out.append((a, b))
    return out


def _mentions(text: str, term: str) -> bool:
    return bool(find_mentions(text, term))


def satisfaction_report(ledger: "dict[str, Any]", content_roots: "Iterable[PurePath | str]", *,
                        reader: "Callable[[PurePath], str | None] | None" = None,
                        lister: "Callable[[PurePath], list[PurePath]] | None" = None,
                        config: "dict[str, Any] | None" = None) -> "dict[str, Any]":
    """CLOSE-TIME: for every create/update/mention disposition the target (file or directory,
    `#fragment` stripped) must resolve to >= 1 existing ENGLISH, non-draft page under a content
    root whose BODY (frontmatter stripped) mentions >= satisfaction.min_term_ratio[surface] of the
    unit's terms (and >= 1 term). Draft pages, locale-suffixed files and locale directories are
    refused and reported with the reason. `none` needs a non-empty rationale. Statuses are COMPUTED
    here, never read from the ledger. Returns {"units": [{"id", "surfaces": {surface: {action,
    status, evidence_paths, problems, placement, refused}}}], "all_satisfied", "problems",
    "refused": [{unit, surface, path, reason}]}."""
    cfg = require_config(config)
    sat = cfg["satisfaction"]
    ratios = sat["min_term_ratio"]
    suffixes = tuple(str(s).casefold() for s in sat["directory_suffixes"])
    reader = reader or _default_reader
    lister = lister or _default_lister
    roots = [PurePath(r) if not isinstance(r, PurePath) else r for r in content_roots]
    locales = locale_codes(roots)
    rows, problems, refused_all = [], [], []
    for u in ledger.get("units") or []:
        terms = unit_terms_from_symbols(u)
        surfaces: "dict[str, Any]" = {}
        for surface in SURFACES:
            d = (u.get("dispositions") or {}).get(surface) or {}
            action = d.get("action")
            row = {"action": action, "status": "pending", "evidence_paths": [], "problems": [],
                   "placement": d.get("placement"), "refused": []}
            if action == "none":
                if str(d.get("rationale") or "").strip():
                    row["status"] = "none_justified"
                else:
                    row["problems"].append("none without a rationale")
            elif action in ("create", "update", "mention"):
                if d.get("placement") == "unplaced":
                    row["problems"].append("unplaced: no existing block matches this mention")
                elif not str(d.get("target") or "").strip():
                    row["problems"].append("no target")
                else:
                    _check_target(row, str(d["target"]).split("#", 1)[0], terms, roots, reader, lister, suffixes,
                                  float(ratios[surface]), locales)
            else:
                row["problems"].append(f"unknown action {action!r}")
            row["evidence_paths"] = sorted(set(row["evidence_paths"]))
            row["problems"] = sorted(row["problems"])
            row["refused"] = sorted(row["refused"], key=lambda x: (x["path"], x["reason"]))
            for p in row["problems"]:
                problems.append(f"{u.get('id')}/{surface}: {p}")
            for r in row["refused"]:
                refused_all.append({"unit": u.get("id"), "surface": surface, **r})
            surfaces[surface] = row
        rows.append({"id": u.get("id"), "surfaces": surfaces})
    return {"units": rows, "problems": sorted(problems), "refused": refused_all,
            "all_satisfied": all(s["status"] in ("satisfied", "none_justified")
                                 for r in rows for s in r["surfaces"].values())}


def _check_target(row, target, terms, roots, reader, lister, suffixes, min_ratio, locales) -> None:
    files: "list[tuple[PurePath, str, PurePath]]" = []  # (path, text, root)
    for root in roots or [PurePath("")]:
        base = PurePath(target) if PurePath(target).is_absolute() else root / target
        if not target.endswith("/"):
            text = reader(base)
            if text is not None:
                files.append((base, text, root))
                continue
        for f in lister(base):
            if str(f).casefold().endswith(suffixes):
                text = reader(f)
                if text is not None:
                    files.append((f, text, root))
    if not files:
        row["problems"].append(f"target not found under any content root: {target}")
        return
    hit_terms: "set[str]" = set()
    evidence: "set[str]" = set()
    for path, text, root in files:
        rel = _rel(path, root)
        body, reason = evidence_page(rel, text, locales)
        if reason:
            row["refused"].append({"path": rel, "reason": reason})
            continue
        found = {t for t in terms if find_mentions(body, t)}
        if found:
            hit_terms |= found
            evidence.add(rel)
    row["evidence_paths"] = sorted(evidence)
    need = min_ratio * len(terms)
    note = ("; refused: " + ", ".join(f"{r['path']} ({r['reason']})" for r in row["refused"])) if row["refused"] else ""
    if not hit_terms:
        row["problems"].append(f"no unit term mentioned in {target} (terms: {', '.join(terms)}){note}")
    elif len(hit_terms) < need:
        missing = sorted(set(terms) - hit_terms)
        row["problems"].append(f"term coverage {len(hit_terms)}/{len(terms)} below {min_ratio}; missing: "
                               f"{', '.join(missing)}{note}")
    else:
        row["status"] = "satisfied"


def check_computed_actions(ledger: "dict[str, Any]", config: "dict[str, Any] | None" = None) -> "list[str]":
    """Re-derive every cell's action from the unit's recorded scale + kind + the CURRENT config and
    compare with the persisted computed_action: a rewritten computed_action (or a ledger hand-edited
    to weaken every cell) shows up here. Returns problems ([] = consistent)."""
    cfg = require_config(config)
    out: "list[str]" = []
    for u in ledger.get("units") or []:
        try:
            fresh = decide_dispositions(u["scale"], kind=u["kind"], unit_terms=unit_terms_from_symbols(u),
                                        surface_targets=None, candidate_blocks=[], config=cfg)
        except (KeyError, TypeError) as exc:
            out.append(f"unit {u.get('id')}: cannot recompute dispositions ({type(exc).__name__}: {exc})")
            continue
        for surface in SURFACES:
            rec = ((u.get("dispositions") or {}).get(surface) or {}).get("computed_action")
            if rec is None:
                out.append(f"unit {u.get('id')} surface {surface}: computed_action missing")
            elif rec != fresh[surface]["action"]:
                out.append(f"unit {u.get('id')} surface {surface}: computed_action {rec!r} != recomputed "
                           f"{fresh[surface]['action']!r} from the unit scale and current config")
    return out


def apply_worth(ledger: "dict[str, Any]", unit_id_: str, symbol: str, worth: str, reason: str, *,
                config: "dict[str, Any] | None" = None) -> "dict[str, Any]":
    """A copy of the ledger with `symbol` marked internal|public in unit `unit_id_`: the unit scale,
    kind, internal_symbols and ALL five dispositions are recomputed (targets and satisfied dispositions that
    keep their action are carried over; an override is dropped because the computed action moved).
    A disposition that becomes none records the worth reason in its rationale."""
    cfg = require_config(config)
    if worth not in WORTH_VALUES:
        raise ValueError(f"worth must be one of {WORTH_VALUES}, got {worth!r}")
    if not str(reason or "").strip():
        raise ValueError("a non-empty reason is required")
    out = copy.deepcopy(ledger)
    unit = next((u for u in out.get("units") or [] if u.get("id") == unit_id_), None)
    if unit is None:
        raise ValueError(f"unknown unit {unit_id_!r}")
    if symbol not in unit.get("symbols", []):
        raise ValueError(f"unknown symbol {symbol!r} in unit {unit_id_}")
    detail = copy.deepcopy(unit["scale_inputs"])
    sw = unit.setdefault("symbol_worth", {})
    ns_internal = bool((detail["types"].get(symbol) or {}).get("namespace_internal"))
    if worth == "public" and not ns_internal:
        sw.pop(symbol, None)
    else:
        sw[symbol] = {"worth": worth, "reason": str(reason).strip()}
    _apply_worth_to_detail(detail, sw)
    old_scale = unit["scale"]
    sc = compute_scale({"_detail": detail, "symbols": unit["symbols"]}, config=cfg,
                       public_surface_size=out.get("public_surface_size"))
    kind = sc.pop("kind")
    sc["verified_example_present"] = old_scale.get("verified_example_present")
    sc["snippet_candidates"] = list(old_scale.get("snippet_candidates") or [])
    old = unit["dispositions"]
    st = {s: old[s]["target"] for s in ("reference", "docs", "kb", "blog") if old.get(s) and old[s].get("target")}
    if (old.get("products") or {}).get("placement") == "dedicated_section" and old["products"].get("target"):
        st["products"] = old["products"]["target"]
    fresh = decide_dispositions(sc, kind=kind, unit_terms=unit_terms_from_symbols(unit), surface_targets=st,
                                candidate_blocks=[], config=cfg)
    for s in SURFACES:
        new, o = fresh[s], old.get(s) or {}
        if new["action"] != "none" and o.get("action") == new["action"] and o.get("target"):
            new["target"] = o["target"]
            if new["placement"] == "unplaced":
                new["placement"] = o.get("placement")
            new["status"], new["evidence_paths"] = o.get("status", "pending"), list(o.get("evidence_paths") or [])
        if new["action"] == "none" and o.get("action") not in (None, "none"):
            new["rationale"] += f" (worth {worth} for {symbol}: {str(reason).strip()})"
        fresh[s] = new
    unit["scale"], unit["kind"] = sc, kind
    unit["scale_inputs"] = detail
    unit["internal_symbols"] = sorted(q for q, t in detail["types"].items() if t["internal"])
    unit["dispositions"] = {s: fresh[s] for s in SURFACES}
    change = {"symbol": symbol, "worth": worth, "reason": str(reason).strip()}
    log = unit.setdefault("worth_changes", [])
    if not log or log[-1] != change:
        log.append(change)
    return out


def apply_report(ledger: "dict[str, Any]", report: "dict[str, Any]") -> "dict[str, Any]":
    """Deep copy of the ledger whose statuses/evidence_paths are the COMPUTED ones from `report`."""
    out = copy.deepcopy(ledger)
    by_id = {r["id"]: r["surfaces"] for r in report.get("units") or []}
    for u in out.get("units") or []:
        for surface, d in (u.get("dispositions") or {}).items():
            comp = (by_id.get(u["id"]) or {}).get(surface)
            if comp:
                d["status"] = comp["status"]
                d["evidence_paths"] = list(comp["evidence_paths"])
    return out
