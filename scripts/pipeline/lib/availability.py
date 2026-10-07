"""availability.py -- symbol-level release availability (MT074 card B5).

CONTRACT: scripts/pipeline/lib/availability.py
  purpose: A capability is `released` iff its qualified symbols exist at the PUBLISHED release,
           NOT because a manifest/pom version string says so. The verified failure this module
           exists for: the package manifest's version is byte-identical at the old commit and
           at upstream HEAD while the changelog (and the API) are many features ahead -- a
           version comparison calls everything "released" and prose then advertises
           coordinates and APIs a user cannot install.
  states:  released | unreleased | unknown
             released    every symbol is present in the API surface at the published release ref
             unreleased  absent at the release ref (or the registry proves nothing is published)
             unknown     the release ref could not be established, the registry type/adapter is
                         unsupported, the probe was ambiguous, the symbol source failed, or the
                         symbol is only matched by simple name under a different qualifier
                         (ambiguous identity). EVERY gate treats unknown as NOT released.
  symbol form (shared with lib/capability_delta.py):
             type      ``<qualifier>::<Name>``  (qualifier = namespace/package, else the source
                       file's directory; none => bare ``Name``) -- the same identity as
                       refresh_knowledge._api_qualified_name
             member    ``<type symbol>.<member>``  (methods, properties, enum constants)

Inputs and seams (all injectable, nothing here touches the network or git on its own):
  release_ref_from_registry(entry, probe=None, *, tag_resolver=None, config=None)
      entry   = one data/package_registry.json platform record (``candidate`` + ``verification``)
      probe   = a lib/publication_probe.probe_publication() result (live fact, optional)
      The release ref is, in order: a ref named by the verification block (config
      availability.release_ref_keys); else a tag resolved from the probe's live latest_version
      through ``tag_resolver(tag) -> sha | None`` (tag candidates from config
      availability.tag_templates); else ``candidate.repo_sha`` (the scout-time commit -- weaker
      evidence, hence last). A live-unambiguous "not published" yields
      `unreleased`; an offline/ambiguous/unsupported probe never flips anything -> `unknown`.
  probe_release(install_info, *, repo_url, fetch, tag_resolver, ...)
      thin wrapper: runs lib/publication_probe.probe_publication with an injectable `fetch`
      (registry adapters for every registry type it supports; anything else is `unknown`).
  symbols_at(ref) -> iterable[str]      caller-supplied seam (api-surface / adapter based).
  symbols_from_api_surface(entries)     builds the symbol set of one api_surface snapshot.
  symbol_availability(symbols, release_ref, symbols_at) -> {symbol: state}
  unit_availability(states) -> state    released only if ALL released; any unreleased ->
                                        unreleased; otherwise unknown.
  release_since(symbols, *, current_symbols, previous_symbols, version, previous_version)
      B5b "Since <version>": per symbol, present in the CURRENT published surface and absent in the
      PREVIOUS one => released, available_since=version; present in the previous one => released,
      available_since=previous_version ("earlier-than-<version>" / "earlier" when unknown);
      absent from the current one => unreleased; ambiguous/empty surfaces or no previous surface
      => since unknown (available_since None -- never a guess).
  unit_since(infos, *, version, previous_version) -> {available_since, partial_earlier, counts}
      unit roll-up: every symbol released-in-version => version; mixed with earlier symbols =>
      version (the max needed) with partial_earlier True; since-unknown symbols never block a
      unit that has a since_current symbol; any unreleased/unknown symbol => None.
  forbidden_coordinate_scan(text, *, released_versions, unreleased_versions, config=None)
      flags version tokens only in a coordinate context, a keyword context of the product's own
      version scheme, or when literally in the unreleased set (m2); dates, IPs, OIDs and tool
      versions are never flagged.
  qualifier_present / qualifier_spans / qualifier_uncovered
      configurable, word-bounded, negation-guarded availability-qualifier phrases; a unit's EACH
      mention needs a qualifier within availability.qualifier_window_chars (m1).
  Every threshold and phrase list is read from config; a missing key raises ConfigError (M5).

Determinism: all outputs are sorted; no wall-clock values.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Callable, Iterable

import yaml

_LIB_DIR = Path(__file__).resolve().parent
_PIPELINE_DIR = _LIB_DIR.parent

DEFAULT_CONFIG_PATH = _PIPELINE_DIR / "config" / "capability_placement.yaml"
_CONFIG_PATH = DEFAULT_CONFIG_PATH
_CONFIG_CACHE: "dict[tuple[str, int], dict[str, Any]]" = {}

RELEASED = "released"
UNRELEASED = "unreleased"
UNKNOWN = "unknown"
STATES = (RELEASED, UNRELEASED, UNKNOWN)


def configure(*, config_path: "Path | str | None" = None) -> None:
    """Point the module at another capability_placement.yaml (tests); None restores the default."""
    global _CONFIG_PATH
    _CONFIG_PATH = Path(config_path) if config_path is not None else DEFAULT_CONFIG_PATH


def load_config(path: "Path | str | None" = None) -> "dict[str, Any]":
    """The whole capability_placement.yaml (cached by path + mtime)."""
    p = Path(path) if path is not None else _CONFIG_PATH
    key = (str(p), p.stat().st_mtime_ns)
    if key not in _CONFIG_CACHE:
        _CONFIG_CACHE[key] = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    return _CONFIG_CACHE[key]


class ConfigError(ValueError):
    """A required key of capability_placement.yaml is missing. The library never falls back to a
    default threshold: damaged config must fail closed, naming the key."""


def _req(config: "dict[str, Any] | None", *path: str) -> Any:
    """The config value at the dotted `path` (config=None -> the current file); ConfigError when a
    key is absent or null."""
    node: Any = config if config is not None else load_config()
    for i, key in enumerate(path):
        if not isinstance(node, dict) or node.get(key) is None:
            raise ConfigError("missing required config key " + ".".join(path[:i + 1]))
        node = node[key]
    return node


# ── symbol identity (shared with capability_delta) ───────────────────────────────────────────

def api_namespace(entry: "dict[str, Any]") -> str:
    """Namespace/package qualifier of an api_surface entry ("" when none). Same field order as
    refresh_knowledge._api_namespace; module_key/module_label are documentation groupings."""
    for field in ("canonical_namespace", "class_package", "namespace", "package"):
        value = entry.get(field)
        if value:
            return str(value)
    return ""


def qualified_name(entry: "dict[str, Any]") -> str:
    """``<qualifier>::<name>``; qualifier falls back to the source file, then to nothing."""
    name = str(entry.get("name", ""))
    qualifier = api_namespace(entry) or str(entry.get("file") or "")
    return f"{qualifier}::{name}" if qualifier else name


def _member_names(entry: "dict[str, Any]", field: str) -> "list[str]":
    out: "list[str]" = []
    for m in entry.get(field, []) or []:
        if isinstance(m, dict):
            if m.get("name") is not None:
                out.append(str(m["name"]))
        elif m is not None:
            out.append(str(m))
    return out


def symbols_from_api_surface(entries: "Iterable[dict[str, Any]]") -> "set[str]":
    """Every type symbol and every member symbol (methods, properties, enum members) of one
    api_surface snapshot, in the shared symbol form."""
    out: "set[str]" = set()
    for e in entries or []:
        if not isinstance(e, dict) or "name" not in e:
            continue
        q = qualified_name(e)
        out.add(q)
        for field in ("methods", "properties", "enum_members"):
            for m in _member_names(e, field):
                out.add(f"{q}.{m}")
    return out


def symbol_type_tail(symbol: str) -> str:
    """The part of a symbol after ``::`` (``Name`` or ``Name.member``)."""
    return symbol.split("::", 1)[-1]


def is_member_symbol(symbol: str) -> bool:
    return "." in symbol_type_tail(symbol)


def type_of_symbol(symbol: str) -> str:
    """The type symbol a (possibly member) symbol belongs to."""
    if "::" in symbol:
        head, tail = symbol.split("::", 1)
        return f"{head}::{tail.split('.', 1)[0]}"
    return symbol.split(".", 1)[0]


def simple_name(symbol: str) -> str:
    """``Name`` for a type symbol, ``member`` for a member symbol."""
    tail = symbol_type_tail(symbol)
    return tail.rsplit(".", 1)[-1]


# ── release ref resolution ──────────────────────────────────────────────────────────────────────

def _result(ref: "str | None", source: str, *, state_hint: "str | None" = None,
            reason: "str | None" = None, version: "str | None" = None) -> "dict[str, Any]":
    return {"ref": ref, "source": source, "state_hint": state_hint, "reason": reason,
            "version": version}


def release_ref_from_registry(entry: "dict[str, Any] | None", probe: "dict[str, Any] | None" = None, *,
                              tag_resolver: "Callable[[str], str | None] | None" = None,
                              config: "dict[str, Any] | None" = None) -> "dict[str, Any]":
    """Establish the PUBLISHED release ref. Returns {ref, source, state_hint, reason, version}.

    ref None => every symbol is `unknown`, unless state_hint == "unreleased" (the registry was
    probed live and unambiguously proves nothing is published: every symbol is `unreleased`).
    """
    release_ref_keys = list(_req(config, "availability", "release_ref_keys"))
    tag_templates = list(_req(config, "availability", "tag_templates"))
    live = (probe or {}).get("live") or {}
    live_unambiguous = bool(probe) and (probe.get("source") == "live_probe") and live.get("ambiguous") is False
    if live_unambiguous and live.get("published") is False:
        return _result(None, "probe", state_hint=UNRELEASED, reason="registry_not_published_live")
    entry = entry or {}
    verification = entry.get("verification") or {}
    candidate = entry.get("candidate") or {}
    published_per_record = verification.get("published")
    for key in release_ref_keys:
        if verification.get(key):
            return _result(str(verification[key]), f"verification.{key}",
                           version=candidate.get("version"))
    if published_per_record is False and not live_unambiguous:
        return _result(None, "record", reason="registry_record_not_published")
    version = live.get("latest_version") if live_unambiguous else None
    tag_miss = False
    if version and tag_resolver is not None:
        for tmpl in tag_templates:
            tag = tmpl.format(version=version)
            try:
                sha = tag_resolver(tag)
            except Exception:  # noqa: BLE001 -- a resolver failure is "cannot tell", never a guess
                sha = None
            if sha:
                return _result(str(sha), f"tag:{tag}", version=version)
        tag_miss = True
    if candidate.get("repo_sha") and published_per_record is not False:
        return _result(str(candidate["repo_sha"]), "candidate.repo_sha",
                       version=candidate.get("version"))
    if tag_miss:
        return _result(None, "probe", reason="release_tag_not_resolvable", version=version)
    if not entry and not probe:
        return _result(None, "none", reason="no_registry_entry")
    if probe and not live_unambiguous:
        return _result(None, "probe", reason="probe_unsupported_or_ambiguous")
    return _result(None, "none", reason="no_release_ref_in_record")


def probe_release(install_info: "dict[str, Any]", *, repo_url: "str | None" = None, fetch=None,
                  tag_resolver=None, config: "dict[str, Any] | None" = None) -> "dict[str, Any]":
    """Probe the registry through lib/publication_probe (injectable `fetch`; every registry type
    that module supports) and resolve the release ref. Unsupported registry / ambiguous probe /
    no candidate identity => ref None (unknown)."""
    from publication_probe import probe_publication  # local: pulls the registry adapters

    probe = probe_publication(install_info, repo_url=repo_url, fetch=fetch)
    entry = {"candidate": (install_info or {}).get("candidate") or {},
             "verification": (install_info or {}).get("verification") or {}}
    out = release_ref_from_registry(entry, probe, tag_resolver=tag_resolver, config=config)
    out["probe_source"] = probe.get("source")
    return out


def released_versions(entry: "dict[str, Any] | None", probe: "dict[str, Any] | None" = None) -> "list[str]":
    """Versions that may legitimately appear in prose: the registry's published candidate
    version (only when the record says published) and the live probe's latest version."""
    out: "set[str]" = set()
    entry = entry or {}
    if (entry.get("verification") or {}).get("published") and (entry.get("candidate") or {}).get("version"):
        out.add(_norm_version(str(entry["candidate"]["version"])))
    live = (probe or {}).get("live") or {}
    if live.get("ambiguous") is False and live.get("published") and live.get("latest_version"):
        out.add(_norm_version(str(live["latest_version"])))
    return sorted(out)


# ── symbol availability ─────────────────────────────────────────────────────────────────────────

def symbol_availability(symbols: "Iterable[str]", release_ref: "str | None",
                        symbols_at: "Callable[[str], Iterable[str]]", *,
                        state_hint: "str | None" = None) -> "dict[str, dict[str, Any]]":
    """{symbol: {"state": released|unreleased|unknown, "reason": str|None}} -- sorted by symbol.

    unknown when: no release ref (unless the registry proved nothing is published), the
    `symbols_at` seam raised or returned nothing for that ref, or the symbol is only matched by
    simple name under a different qualifier (ambiguous identity: never claimed unreleased).
    """
    syms = sorted({str(s) for s in symbols})
    if release_ref is None:
        if state_hint == UNRELEASED:
            return {s: {"state": UNRELEASED, "reason": "registry_not_published_live"} for s in syms}
        return {s: {"state": UNKNOWN, "reason": "no_release_ref"} for s in syms}
    try:
        released = {str(s) for s in symbols_at(release_ref)}
    except Exception as exc:  # noqa: BLE001
        return {s: {"state": UNKNOWN, "reason": f"symbols_at_failed:{type(exc).__name__}"} for s in syms}
    if not released:
        return {s: {"state": UNKNOWN, "reason": "empty_symbol_set_at_release"} for s in syms}
    released_types_by_simple: "dict[str, set[str]]" = {}
    for r in released:
        if not is_member_symbol(r):
            released_types_by_simple.setdefault(simple_name(r), set()).add(r)
    out: "dict[str, dict[str, Any]]" = {}
    for s in syms:
        if s in released:
            out[s] = {"state": RELEASED, "reason": None}
            continue
        owner = type_of_symbol(s)
        # the owner type exists at the release under another qualifier => identity is ambiguous
        other_owner = {t for t in released_types_by_simple.get(simple_name(owner), set()) if t != owner}
        if owner not in released and other_owner:
            out[s] = {"state": UNKNOWN, "reason": "ambiguous_qualifier"}
        elif is_member_symbol(s) and s.rsplit(".", 1)[-1] and any(
                r.rsplit(".", 1)[-1] == s.rsplit(".", 1)[-1] and type_of_symbol(r) in other_owner
                for r in released if is_member_symbol(r)):
            out[s] = {"state": UNKNOWN, "reason": "ambiguous_qualifier"}
        else:
            out[s] = {"state": UNRELEASED, "reason": "absent_at_release"}
    return out


def unit_availability(states: "Iterable[str]") -> str:
    """released only if ALL released (and there is >= 1 symbol); any unreleased -> unreleased;
    otherwise (any unknown, or no symbols at all) -> unknown."""
    states = list(states)
    if not states:
        return UNKNOWN
    if all(s == RELEASED for s in states):
        return RELEASED
    if any(s == UNRELEASED for s in states):
        return UNRELEASED
    return UNKNOWN


def is_released(state: "str | None") -> bool:
    """The one place that says what every gate means by it: only `released` is released."""
    return state == RELEASED


# ── "Since <version>" (B5b) ─────────────────────────────────────────────────────────────────────

def release_since(symbols: "Iterable[str]", *, current_symbols: "Iterable[str]",
                  previous_symbols: "Iterable[str] | None" = None, version: "str | None" = None,
                  previous_version: "str | None" = None) -> "dict[str, dict[str, Any]]":
    """{symbol: {state, available_since, since_basis, reason}} -- sorted by symbol.

    `current_symbols` / `previous_symbols` are the symbol sets of the PUBLISHED surfaces of the
    current and previous release (see symbols_from_api_surface). since_basis is one of
    current_only | previous | previous_surface_missing | ambiguous_previous | n/a (not released)."""
    syms = sorted({str(x) for x in symbols})
    cur = {str(x) for x in current_symbols}
    cur_states = symbol_availability(syms, "current", lambda _r: cur)
    prev_states = None
    if previous_symbols is not None:
        prev = {str(x) for x in previous_symbols}
        prev_states = symbol_availability(syms, "previous", lambda _r: prev)
    out: "dict[str, dict[str, Any]]" = {}
    for sym in syms:
        state, reason = cur_states[sym]["state"], cur_states[sym]["reason"]
        if state != RELEASED:
            out[sym] = {"state": state, "available_since": None, "since_basis": "n/a", "reason": reason}
        elif prev_states is None:
            out[sym] = {"state": RELEASED, "available_since": None, "since_basis": "previous_surface_missing",
                        "reason": None}
        else:
            pst = prev_states[sym]
            if pst["state"] == RELEASED:
                out[sym] = {"state": RELEASED, "since_basis": "previous", "reason": None,
                            "available_since": previous_version or (f"earlier-than-{version}" if version else "earlier")}
            elif pst["state"] == UNRELEASED:
                out[sym] = {"state": RELEASED, "available_since": version, "since_basis": "current_only",
                            "reason": None}
            else:
                out[sym] = {"state": RELEASED, "available_since": None, "since_basis": "ambiguous_previous",
                            "reason": pst["reason"]}
    return out


def unit_since(infos: "Iterable[Any]", *, version: "str | None" = None,
               previous_version: "str | None" = None) -> "dict[str, Any]":
    """Roll per-symbol infos ({state, available_since, since_basis} or a bare state string) up to a
    unit: {available_since, partial_earlier, counts}. The unit's required version is the MAX over its
    symbols' since-versions. available_since is None while any symbol is unreleased/unknown. Otherwise,
    with >= 1 since_current symbol it is `version` (even if other symbols are since_unknown -- being
    present in the current release they cannot be later than it); partial_earlier is True only when
    some symbol is determinately earlier. With no since_current symbol it is the earlier version
    shared by all, and None if any symbol is since_unknown."""
    counts = {"since_current": 0, "earlier": 0, "since_unknown": 0, "unreleased": 0, "unknown": 0}
    sinces: "list[str]" = []
    n = 0
    for raw in infos:
        n += 1
        info = raw if isinstance(raw, dict) else {"state": raw}
        state = info.get("state")
        if state == UNRELEASED:
            counts["unreleased"] += 1
        elif state != RELEASED:
            counts["unknown"] += 1
        elif info.get("available_since") is None:
            counts["since_unknown"] += 1
        elif info.get("since_basis") == "previous":
            counts["earlier"] += 1
            sinces.append(str(info["available_since"]))
        else:
            counts["since_current"] += 1
            sinces.append(str(info["available_since"]))
    since: "str | None" = None
    partial = False
    if n and not (counts["unreleased"] or counts["unknown"]):
        if counts["since_current"]:
            # a symbol PRESENT in the current release can never be later than it, so undetermined
            # (since_unknown) symbols cannot raise the unit's required version above `version`
            since = version if version else None
            partial = counts["earlier"] > 0
        elif counts["since_unknown"] == 0 and sinces:
            since = sorted(set(sinces))[0] if len(set(sinces)) == 1 else (previous_version or None)
    return {"available_since": since, "partial_earlier": partial, "counts": counts}


# ── prose scans ─────────────────────────────────────────────────────────────────────────────────

def _norm_version(v: str) -> str:
    v = v.strip()
    return v[1:] if v[:1] in ("v", "V") and v[1:2].isdigit() else v


def _components(version: str) -> int:
    return len(re.findall(r"\d+", re.split(r"[-+]", version, maxsplit=1)[0]))


def _line_of(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _major(version: str) -> "str | None":
    m = re.match(r"\d+", _norm_version(version))
    return m.group(0) if m else None


def forbidden_coordinate_scan(text: str, *, released_versions: "Iterable[str] | None",
                              unreleased_versions: "Iterable[str] | None" = (),
                              config: "dict[str, Any] | None" = None) -> "list[dict[str, Any]]":
    """Version tokens in `text` that content must not cite. A token is flagged only when it is

      (i)   inside a STRONG coordinate context (config coordinate_scan.coordinate_patterns:
            groupId:artifactId:V, <version>V</version>, version="V", pkg==V, pkg@V, pkg-V), or
            directly after a keyword (coordinate_scan.keyword_contexts: version, since, requires,
            ...) AND of the product's own version scheme (same leading component as a released or
            unreleased version; with no known version every keyword context counts), or
      (ii)  literally in `unreleased_versions` (the ledger's unreleased set),

    and is NOT in `released_versions`. Dotted-quad addresses, ISO-ish dates, long dotted OIDs
    (coordinate_scan.ignore_patterns) and tool-name coordinates (ignore_tool_names) are never
    flagged, except an explicitly unreleased version. Findings: {kind: coordinate|keyword|
    unreleased, text, version, line, released_set_known}, sorted by (line, version). Every
    coordinate_scan key is REQUIRED (ConfigError names a missing one) -- no defaults in code.
    """
    root = config
    _req(root, "availability", "coordinate_scan")
    min_coord = int(_req(root, "availability", "coordinate_scan", "min_components_in_coordinate"))
    vpat = str(_req(root, "availability", "coordinate_scan", "version_pattern"))
    patterns = list(_req(root, "availability", "coordinate_scan", "coordinate_patterns"))
    keywords = list(_req(root, "availability", "coordinate_scan", "keyword_contexts"))
    ignores = list(_req(root, "availability", "coordinate_scan", "ignore_patterns"))
    tools = {str(t).casefold() for t in _req(root, "availability", "coordinate_scan", "ignore_tool_names")}
    released = {_norm_version(str(v)) for v in (released_versions or [])}
    unreleased = {_norm_version(str(v)) for v in (unreleased_versions or [])} - released
    known = bool(released)
    majors = {m for m in (_major(v) for v in released | unreleased) if m}
    text = text or ""
    ignored = [m.span() for pat in ignores for m in re.finditer(pat, text)]

    def skip(span: "tuple[int, int]", version: str) -> bool:
        if version in released:
            return True
        if version in unreleased:
            return False
        return any(a <= span[0] and span[1] <= b for a, b in ignored)

    found: "dict[tuple[int, str], dict[str, Any]]" = {}

    def add(kind: str, shown: str, version: str, offset: int) -> None:
        line = _line_of(text, offset)
        found.setdefault((line, version), {"kind": kind, "text": shown.strip(), "version": version, "line": line,
                                           "released_set_known": known})

    for pat in patterns:
        for m in re.finditer(pat.replace("{V}", vpat), text):
            version = _norm_version(m.group("version"))
            lead = text[m.start():m.start("version")].casefold()
            if any(tok in tools for tok in re.split(r"[^a-z0-9]+", lead) if tok):
                continue
            if _components(version) < min_coord or skip(m.span("version"), version):
                continue
            add("coordinate", m.group(0), version, m.start())
    if keywords:
        alt = "|".join(re.escape(k).replace("\\ ", r"\s+") for k in keywords)
        kw = re.compile(r"(?i)(?<![\w.])(?:" + alt + r")\s*[:=]?\s*[\"']?v?(?P<version>" + vpat + ")")
        for m in kw.finditer(text):
            version = _norm_version(m.group("version"))
            if _components(version) < min_coord or skip(m.span("version"), version):
                continue
            if known or majors:
                if _major(version) not in majors:
                    continue
            add("keyword", m.group(0), version, m.start())
    for u in sorted(unreleased):
        for m in re.finditer(r"(?<![\w.])v?" + re.escape(u) + r"(?![\w]|\.\d)", text):
            if not skip(m.span(), u):
                add("unreleased", u, u, m.start())
    return [found[k] for k in sorted(found)]


def _negation_guard(root: "dict[str, Any] | None") -> "re.Pattern[str]":
    prefixes = list(_req(root, "availability", "qualifier_negation_prefixes"))
    alts = []
    for p in prefixes:
        body = r"\s+".join(re.escape(w) for w in str(p).split())
        alts.append(body if "'" in str(p) else r"(?<![A-Za-z0-9])" + body)
    return re.compile("(?:" + "|".join(alts) + r")\s+$", re.IGNORECASE) if alts else re.compile(r"(?!x)x")


def qualifier_spans(text: str, *, config: "dict[str, Any] | None" = None) -> "list[tuple[int, int]]":
    """Spans of every availability-qualifier phrase in `text`: configured phrases (case-insensitive,
    whitespace-flexible, word-bounded) not directly preceded by a negation prefix."""
    phrases = list(_req(config, "availability", "qualifier_phrases"))
    guard = _negation_guard(config)
    out: "list[tuple[int, int]]" = []
    for ph in phrases:
        body = r"\s+".join(re.escape(w) for w in str(ph).split())
        for m in re.finditer(r"(?<![A-Za-z0-9])" + body + r"(?![A-Za-z0-9])", text or "", re.IGNORECASE):
            if guard.search(text[max(0, m.start() - 30):m.start()]):
                continue
            out.append(m.span())
    return sorted(set(out))


def qualifier_present(text: str, *, config: "dict[str, Any] | None" = None) -> bool:
    """True when `text` contains at least one availability qualifier (see qualifier_spans). Page
    level only; a unit's mentions are checked individually with qualifier_uncovered."""
    return bool(qualifier_spans(text, config=config))


def qualifier_uncovered(text: str, mention_spans: "Iterable[tuple[int, int]]", *,
                        config: "dict[str, Any] | None" = None) -> "list[tuple[int, int]]":
    """The mentions that have NO qualifier within availability.qualifier_window_chars characters
    (before or after). Each mention needs its own nearby qualifier."""
    window = int(_req(config, "availability", "qualifier_window_chars"))
    quals = qualifier_spans(text, config=config)
    return [sp for sp in mention_spans
            if not any(q0 <= sp[1] + window and q1 >= sp[0] - window for q0, q1 in quals)]
