#!/usr/bin/env python3
"""capability_ledger.py -- thin CLI over lib/capability_delta.py (MT074 card B4).

CONTRACT: scripts/pipeline/commands/ops/capability_ledger.py
  purpose: The command surface refresh steps and content skills call to build, check and update a
           capability disposition ledger. All logic lives in lib/capability_delta.py and
           lib/availability.py; this file only reads/writes files. Output JSON is sorted-key,
           LF, deterministic: re-running a command over identical inputs is byte-identical.
  subcommands:
    build --family F --platform P --knowledge-delta PATH --out PATH
          [--format-delta PATH] [--api-surface PATH] [--upstream-head SHA]
          [--grouping-overrides PATH] [--surface-targets PATH] [--blocks PATH]
          [--verified-examples PATH] [--snippet-index PATH]
          [--released-api-surface PATH] [--previous-released-api-surface PATH]
          [--release-version V] [--previous-release-version V0]
          [--registry-json PATH ...] [--config PATH] [--base-sha SHA] [--base-knowledge-commit SHA]
          [--unreleased-version V ...] [--worth PATH]
        Writes the ledger. `--api-surface` is the NEW merged api_surface.json (member counts,
        signature references, visibility, existing-symbol universe -- without it token affinity
        is skipped). Availability: `--released-api-surface` is the api_surface.json of the
        PUBLISHED release bundle; a symbol is `released` iff its qualified name exists there,
        `unreleased` if absent, `unknown` if only matched under another qualifier. With no
        released surface every availability stays `unknown` (never assumed released).
        `--registry-json` (data/package_registry.json shape {family: {platform: entry}}, repeatable,
        first hit wins) only contributes availability_context (release ref, released_versions);
        it cannot decide symbol availability on its own.
        File formats (JSON): grouping overrides = list of {"id": str, "symbols": [qualified
        symbol | "format:<name>" ...]}; surface targets = {surface: path}; blocks = list of
        {"id", "path", "terms": [...]}; verified examples = list of symbols/type names;
        snippet index = {type name: [snippet ids]}.
    validate --ledger PATH --stage plan|close
        stdout {"stage", "valid", "errors", "warnings"}; exit 0 valid, 1 invalid. At `plan` a
        missing target / unplaced mention is a warning; at `close` it is an error.
    set-disposition --ledger PATH --unit ID --surface S --action A --rationale R
          [--target T] [--status pending|satisfied|none_justified] [--evidence PATH ...]
          [--override-token ID --override-reason TEXT]
        Going BELOW the persisted computed_action (e.g. create -> none) is refused unless both override
        flags are given; the override {token_id, reason} is recorded on the cell and the gate accepts it.
    set-worth --ledger PATH --unit ID --symbol S --worth internal|public --reason TEXT
        Marks a helper symbol internal (or public again): the unit scale, kind and all five
        dispositions are recomputed (internal helpers leave scale; an all-internal unit is
        reference-only with a recorded rationale). Grouping itself is changed with --grouping-overrides
        at build time (a reviewed split).
        The ONLY sanctioned way to update one disposition. Refuses an unknown unit/surface or an
        edit that introduces a new validation error (file untouched); never touches symbols/ids.
        An empty --target clears it. Default status: none_justified for action none, else pending.
    satisfaction --ledger PATH [--content-root DIR ...]
        Read-only: prints lib satisfaction_report JSON; exit 0 when all satisfied, else 1.
  exit codes: 0 ok, 1 invalid / unsatisfied / refused, 2 unreadable or malformed input.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

_PIPELINE_ROOT = Path(__file__).resolve().parents[2]
if str(_PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_ROOT))
_LIB_DIR = str(_PIPELINE_ROOT / "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
_REPO_ROOT = _PIPELINE_ROOT.parents[1]

import availability as av  # noqa: E402
import capability_delta as cd  # noqa: E402

RELEASED_SURFACE_REF = "released-api-surface"


class CliError(Exception):
    """Unreadable / malformed input (exit 2)."""


def _read_json(path: "str | Path", what: str) -> Any:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise CliError(f"cannot read {what} {path}: {exc}") from exc


def _emit(obj: "dict[str, Any]") -> None:
    sys.stdout.write(json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False) + "\n")


def _registry_entry(paths: "list[str]", family: str, platform: str) -> "dict[str, Any] | None":
    for p in paths:
        data = _read_json(p, "registry json")
        entry = (data.get(family) or {}).get(platform) if isinstance(data, dict) else None
        if isinstance(entry, dict):
            return entry
    return None


def _surface_symbols(path: str, what: str) -> "tuple[set[str], str]":
    raw = Path(path).read_bytes() if Path(path).is_file() else _fail(f"cannot read {what} {path}")
    try:
        entries = json.loads(raw.decode("utf-8"))
    except ValueError as exc:
        raise CliError(f"cannot read {what} {path}: {exc}") from exc
    return av.symbols_from_api_surface(entries), hashlib.sha256(raw).hexdigest()


def _fail(msg: str) -> bytes:
    raise CliError(msg)


def cmd_build(args: argparse.Namespace) -> int:
    cfg = cd.load_config(args.config) if args.config else cd.load_config()
    kd = _read_json(args.knowledge_delta, "knowledge delta")
    fd = _read_json(args.format_delta, "format delta") if args.format_delta else None
    surface = _read_json(args.api_surface, "api surface") if args.api_surface else None
    delta = cd.from_knowledge_delta(kd, fd, api_surface=surface)
    overrides = _read_json(args.grouping_overrides, "grouping overrides") if args.grouping_overrides else None
    kw: "dict[str, Any]" = {
        "surface_targets": _read_json(args.surface_targets, "surface targets") if args.surface_targets else None,
        "candidate_blocks": _read_json(args.blocks, "blocks") if args.blocks else None,
        "snippet_index": _read_json(args.snippet_index, "snippet index") if args.snippet_index else None,
    }
    if args.verified_examples:
        ve = _read_json(args.verified_examples, "verified examples")
        kw["verified_example_symbols"] = ve.get("symbols", []) if isinstance(ve, dict) else ve
    ctx: "dict[str, Any]" = {}
    if args.unreleased_version:
        ctx["unreleased_versions"] = sorted(set(args.unreleased_version))
    worth = _read_json(args.worth, "worth overrides") if args.worth else None
    entry = _registry_entry(args.registry_json or [], args.family, args.platform)
    if args.registry_json:
        ref = av.release_ref_from_registry(entry, config=cfg)
        ctx.update({"release_ref": ref["ref"], "release_source": ref["source"],
                    "released_versions": av.released_versions(entry)})
    availability = None
    try:
        units = cd.group_units(delta, config=cfg, grouping_overrides=overrides)
    except cd.GroupingOverrideError as exc:
        raise CliError(str(exc)) from exc
    if args.previous_released_api_surface and not args.released_api_surface:
        raise CliError("--previous-released-api-surface requires --released-api-surface")
    if args.previous_released_api_surface and not args.release_version:
        raise CliError("--release-version is required with --previous-released-api-surface")
    versions = set(ctx.get("released_versions") or [])
    if args.release_version:
        ctx["release_version"] = args.release_version
        versions.add(args.release_version)
    if args.previous_release_version:
        ctx["previous_release_version"] = args.previous_release_version
        versions.add(args.previous_release_version)
    if args.released_api_surface:
        symbols, sha = _surface_symbols(args.released_api_surface, "released api surface")
        previous = None
        if args.previous_released_api_surface:
            previous, psha = _surface_symbols(args.previous_released_api_surface, "previous released api surface")
            ctx["previous_release_surface_sha256"] = psha
        lookup = sorted({c for u in units for c in
                         ([x for x in u["symbols"] if x not in {a["symbol"] for a in u["ambiguous_symbols"]}]
                          + [c for a in u["ambiguous_symbols"] for c in a["candidates"]])})
        availability = av.release_since(lookup, current_symbols=symbols,
                                        previous_symbols=previous, version=args.release_version,
                                        previous_version=args.previous_release_version)
        ctx["release_source"] = "released_api_surface"
        ctx["release_surface_sha256"] = sha
    if args.registry_json or versions:
        ctx["released_versions"] = sorted(versions)
    try:
        ledger = cd.build_ledger(delta, family=args.family, platform=args.platform, upstream_head=args.upstream_head,
                                 config=cfg, grouping_overrides=overrides, availability=availability,
                                 availability_context=ctx, base_sha=args.base_sha,
                                 base_knowledge_commit=args.base_knowledge_commit, worth_overrides=worth, **kw)
    except (ValueError, cd.ConfigError) as exc:
        raise CliError(str(exc)) from exc
    cd.write_ledger(args.out, ledger)
    _emit({"ok": True, "out": str(args.out), "units": len(ledger["units"]), "symbol_level": ledger["symbol_level"],
           "availability": {s: sum(1 for u in ledger["units"] if u["availability"] == s) for s in av.STATES}})
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    ledger = _read_json(args.ledger, "ledger")
    errors, warnings = cd.validate_ledger_ex(ledger, stage=args.stage)
    _emit({"stage": args.stage, "valid": not errors, "errors": errors, "warnings": warnings})
    return 0 if not errors else 1


def cmd_set_disposition(args: argparse.Namespace) -> int:
    ledger = _read_json(args.ledger, "ledger")
    unit = next((u for u in ledger.get("units") or [] if u.get("id") == args.unit), None)
    if unit is None:
        _emit({"ok": False, "error": f"unknown unit {args.unit!r}"})
        return 1
    if args.surface not in cd.SURFACES or args.surface not in (unit.get("dispositions") or {}):
        _emit({"ok": False, "error": f"unknown surface {args.surface!r}; expected one of {list(cd.SURFACES)}"})
        return 1
    before, _ = cd.validate_ledger_ex(ledger, stage="plan")
    old = unit["dispositions"][args.surface]
    target = (args.target or "").strip() or None
    computed = old.get("computed_action", old.get("action"))
    weaker = cd.ACTION_RANK[args.action] < cd.ACTION_RANK.get(computed, 0)
    token, reason_ov = (args.override_token or "").strip(), (args.override_reason or "").strip()
    if weaker and not (token and reason_ov):
        _emit({"ok": False, "error": f"downgrading {args.surface} from computed_action {computed!r} to {args.action!r} "
                                     "requires --override-token and --override-reason"})
        return 1
    status = args.status or ("none_justified" if args.action == "none" else "pending")
    if args.action == "none":
        placement = None
    elif old.get("placement") == "unplaced":
        placement = "mention" if (target and args.action == "mention") else None
    else:
        placement = old.get("placement") if args.action == old.get("action") else None
    cell = {"action": args.action, "target": target, "rationale": args.rationale, "status": status,
            "evidence_paths": sorted({str(p) for p in (args.evidence or [])}), "placement": placement,
            "computed_action": computed, "computed_placement": old.get("computed_placement", old.get("placement"))}
    if weaker:
        cell["override"] = {"token_id": token, "reason": reason_ov}
    unit["dispositions"][args.surface] = cell
    after, warnings = cd.validate_ledger_ex(ledger, stage="plan")
    new_errors = sorted(set(after) - set(before))
    if new_errors:
        _emit({"ok": False, "error": "edit refused: it introduces validation errors", "errors": new_errors})
        return 1
    cd.write_ledger(args.ledger, ledger)
    _emit({"ok": True, "unit": args.unit, "surface": args.surface, "disposition": unit["dispositions"][args.surface],
           "warnings": warnings})
    return 0


def cmd_set_worth(args: argparse.Namespace) -> int:
    ledger = _read_json(args.ledger, "ledger")
    try:
        new = cd.apply_worth(ledger, args.unit, args.symbol, args.worth, args.reason)
    except (ValueError, cd.ConfigError) as exc:
        _emit({"ok": False, "error": str(exc)})
        return 1
    cd.write_ledger(args.ledger, new)
    unit = next(u for u in new["units"] if u["id"] == args.unit)
    _emit({"ok": True, "unit": args.unit, "symbol": args.symbol, "worth": args.worth, "scale": unit["scale"],
           "actions": {s: d["action"] for s, d in unit["dispositions"].items()}})
    return 0


def cmd_satisfaction(args: argparse.Namespace) -> int:
    ledger = _read_json(args.ledger, "ledger")
    roots = [Path(r) for r in args.content_root] or [_REPO_ROOT / "content"]
    report = cd.satisfaction_report(ledger, roots)
    _emit(report)
    return 0 if report["all_satisfied"] else 1


def _parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="Capability disposition ledger: build / validate / set-disposition / satisfaction.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="build a ledger from knowledge/format deltas")
    b.add_argument("--family", required=True)
    b.add_argument("--platform", required=True)
    b.add_argument("--knowledge-delta", required=True)
    b.add_argument("--format-delta")
    b.add_argument("--api-surface", help="NEW merged api_surface.json")
    b.add_argument("--out", required=True)
    b.add_argument("--upstream-head")
    b.add_argument("--grouping-overrides")
    b.add_argument("--surface-targets")
    b.add_argument("--blocks")
    b.add_argument("--verified-examples")
    b.add_argument("--snippet-index")
    b.add_argument("--released-api-surface", help="api_surface.json of the PUBLISHED release bundle")
    b.add_argument("--previous-released-api-surface", help="api_surface.json of the PREVIOUS published release")
    b.add_argument("--release-version", help="version of the current published release (e.g. 26.9.0)")
    b.add_argument("--previous-release-version", help="version of the previous published release")
    b.add_argument("--base-sha", help="commit the cumulative delta starts from (the recorded propagated sha)")
    b.add_argument("--base-knowledge-commit", help="knowledge commit the delta starts from")
    b.add_argument("--unreleased-version", action="append", default=[],
                   help="a version content must not cite (repeatable)")
    b.add_argument("--worth", help="JSON list of {symbol, worth: internal|public, reason}")
    b.add_argument("--registry-json", action="append", default=[], help="package_registry.json (repeatable)")
    b.add_argument("--config", help="capability_placement.yaml override")
    b.set_defaults(fn=cmd_build)
    v = sub.add_parser("validate", help="validate a ledger at plan or close stage")
    v.add_argument("--ledger", required=True)
    v.add_argument("--stage", choices=cd.STAGES, default="close")
    v.set_defaults(fn=cmd_validate)
    s = sub.add_parser("set-disposition", help="update one unit x surface disposition (validated)")
    s.add_argument("--ledger", required=True)
    s.add_argument("--unit", required=True)
    s.add_argument("--surface", required=True)
    s.add_argument("--action", required=True, choices=cd.ACTIONS)
    s.add_argument("--target", default="")
    s.add_argument("--rationale", required=True)
    s.add_argument("--status", choices=cd.STATUSES)
    s.add_argument("--evidence", action="append", default=[])
    s.add_argument("--override-token", default="", help="required with --override-reason to go below computed_action")
    s.add_argument("--override-reason", default="")
    s.set_defaults(fn=cmd_set_disposition)
    w = sub.add_parser("set-worth", help="mark one symbol internal|public and recompute its unit")
    w.add_argument("--ledger", required=True)
    w.add_argument("--unit", required=True)
    w.add_argument("--symbol", required=True)
    w.add_argument("--worth", required=True, choices=cd.WORTH_VALUES)
    w.add_argument("--reason", required=True)
    w.set_defaults(fn=cmd_set_worth)
    c = sub.add_parser("satisfaction", help="read-only satisfaction report")
    c.add_argument("--ledger", required=True)
    c.add_argument("--content-root", action="append", default=[])
    c.set_defaults(fn=cmd_satisfaction)
    return ap


def main(argv: "list[str] | None" = None) -> int:
    args = _parser().parse_args(argv)
    try:
        return args.fn(args)
    except CliError as exc:
        _emit({"ok": False, "error": str(exc)})
        return 2


if __name__ == "__main__":
    sys.exit(main())
