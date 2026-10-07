#!/usr/bin/env python3
"""capability_surface_gate.py -- close-time capability-surface gate (MT074 cards B4/B5/B9).

CONTRACT: scripts/pipeline/commands/ops/capability_surface_gate.py
  purpose: A product is "propagated" only when every capability unit of its delta has a
           recorded, VERIFIED disposition on every surface. This gate checks that and is the ONLY
           caller of content_propagation_state's propagation writer (a source-scan test enforces
           the allow-list by this file's name). A refresh, a drift scan or a hand edit can make a
           product DRIFTED; only a PASS here can make it PROPAGATED.
  usage:   capability_surface_gate.py --family F --platform P --ledger PATH
              [--content-root DIR ...] [--state-path PATH] [--local-only] [--dry-run]
              [--json-out PATH] [--released-version V ...]
  checks (each failure is one machine-readable reason {code, unit, surface, path, detail}):
    ledger_invalid / ledger_mismatch   lib/capability_delta.validate_ledger problems (incl. every
                                       `unplaced` decision), or family/platform differ from the CLI
    no_symbol_level_ground_truth       the ledger came from file-level (GT-2) evidence only
    missing_upstream_head              the ledger carries no upstream head to record
    unsatisfied                        satisfaction_report: a create/update/mention target missing
                                       or not mentioning the unit's symbols; none without rationale
    availability_qualifier_missing     a page evidencing a unit whose availability is not
                                       `released` (unreleased OR unknown) has a mention of the
                                       unit's symbols with no availability qualifier within the
                                       configured window (lib/availability.qualifier_uncovered)
    config_missing_key                 a required capability_placement.yaml key is absent (the code
                                       carries no defaults for thresholds)
    config_changed                     ledger config_sha256 != the current config: rebuild the ledger
    upstream_head_invalid / upstream_head_mismatch / model_head_unavailable
                                       upstream_head must be 40-hex AND equal the knowledge model
                                       repo_sha
    delta_not_proven_empty / delta_incomplete
                                       no units needs the empty-delta fingerprint; the units must
                                       cover the symbol count recorded at build
    computed_action_tampered           a persisted computed_action != the recomputation from the unit
                                       scale + config (a weaker RECORDED action is a ledger_invalid
                                       unless the cell carries an override {token_id, reason})
    ledger_does_not_cover              the ledger base is not the recorded propagated sha / knowledge
                                       commit (cumulative coverage)
    knowledge_tree_dirty / knowledge_tree_unchecked
                                       knowledge/<f>/<p> has uncommitted changes (or was not checked)
    forbidden_coordinate               a page evidencing ANY unit names a version outside the allowed
                                       set: availability_context.released_versions plus
                                       --released-version, plus (released unit only) its
                                       release_version / available_since; or one in the unreleased
                                       set (availability_context.unreleased_versions plus
                                       --unreleased-version). Version tokens count only in a
                                       coordinate / keyword context (lib/availability).
  evidence: only ENGLISH, non-draft pages count and only their BODY (frontmatter is internal
           metadata); refused pages are listed in report["refused_evidence"] with the reason. Terms
           match as case-sensitive identifiers (common-word symbols only in code spans or qualified).
  limits (also report["not_verified"]): behavioural, changelog and readme changes are outside a
           symbol-level delta, and a method-name-keyed delta cannot see a new OVERLOAD of an existing
           method name (a second signature of save) -- none of these is verified by this gate.
  outputs: a JSON report on stdout (sorted keys, no wall-clock): {verdict, family, platform,
           upstream_head, reasons, units, recorded, refused_evidence, not_verified}. --json-out
           writes the same report to a file.
  PASS:    unless --dry-run, records upstream head, the tracked knowledge commit (injectable
           resolver), --local-only, the capability units with COMPUTED statuses and verdict
           "PASS" in data/content_propagation_state.json (or --state-path).
  FAIL:    writes NOTHING to the propagation fields; exit code 1. (Exit 2 = unreadable input.)
  seams:   run_gate(..., knowledge_commit_resolver=, reader=, lister=, config=) -- no
           monkeypatching needed; evaluate() is a pure function of its arguments.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path, PurePath
from typing import Any, Callable, Iterable

_PIPELINE_ROOT = Path(__file__).resolve().parents[2]
if str(_PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_ROOT))
_LIB_DIR = str(_PIPELINE_ROOT / "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
_REPO_ROOT = _PIPELINE_ROOT.parents[1]

import availability as av  # noqa: E402
import capability_delta as cd  # noqa: E402
import content_propagation_state as cps  # noqa: E402

PASS, FAIL = "PASS", "FAIL"
_SHA40 = re.compile(r"[0-9a-f]{40}")
# What a symbol-level ledger can NOT verify (static; stated in every gate report).
NOT_VERIFIED = ["behavioural", "changelog", "readme", "overloads of existing method names"]


def _reason(code: str, detail: str, *, unit: "str | None" = None, surface: "str | None" = None,
            path: "str | None" = None) -> "dict[str, Any]":
    return {"code": code, "unit": unit, "surface": surface, "path": path, "detail": detail}


def default_knowledge_commit(family: str, platform: str) -> "str | None":
    """Last commit that touched the tracked knowledge directory of the product (None when nothing
    is tracked or git is unavailable)."""
    try:
        out = subprocess.run(["git", "log", "-1", "--format=%H", "--", f"knowledge/{family}/{platform}"],
                             cwd=str(_REPO_ROOT), capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    sha = (out.stdout or "").strip()
    return sha or None


_VERSIONISH = re.compile(r"v?\d+(?:\.\d+)+(?:[-+][0-9A-Za-z.]*[0-9A-Za-z])?")


def _unit_versions(unit: "dict[str, Any]", released: bool) -> "set[str]":
    """Versions a RELEASED unit's pages may legitimately cite: the release it shipped in
    (release_version) and its available_since when that is a real version (not earlier-than-...)."""
    if not released:
        return set()
    return {str(unit[k]) for k in ("release_version", "available_since")
            if unit.get(k) and _VERSIONISH.fullmatch(str(unit[k]))}


def _read_evidence(rel: str, roots: "list[PurePath]", reader) -> "tuple[str | None, str | None]":
    """(text, root-relative path) of an evidence file, trying every content root in order."""
    for root in roots:
        text = reader(root / rel)
        if text is not None:
            return text, rel
    return None, None


def _fail_report(family: str, platform: str, ledger: "dict[str, Any]", reasons: "list[dict[str, Any]]",
                 units: "list[Any] | None" = None, refused: "list[Any] | None" = None) -> "dict[str, Any]":
    reasons = sorted(reasons, key=lambda r: (r["code"], r["unit"] or "", r["surface"] or "", r["path"] or "", r["detail"]))
    return {
        "verdict": PASS if not reasons else FAIL,
        "family": family, "platform": platform, "upstream_head": ledger.get("upstream_head"),
        "reasons": reasons, "units": units or [], "recorded": False,
        "refused_evidence": refused or [], "not_verified": list(NOT_VERIFIED),
    }


def evaluate(ledger: "dict[str, Any]", content_roots: "Iterable[PurePath | str]", *, family: str, platform: str,
             config: "dict[str, Any] | None" = None, reader: "Callable[[PurePath], str | None] | None" = None,
             lister: "Callable[[PurePath], list[PurePath]] | None" = None,
             released_versions: "Iterable[str] | None" = None,
             unreleased_versions: "Iterable[str] | None" = None,
             prior_state: "dict[str, Any] | None" = None, model_head: "str | None" = None,
             knowledge_state: "tuple[bool, str] | None" = None) -> "dict[str, Any]":
    """Pure verdict over a ledger: the report dict (verdict PASS|FAIL + reasons + computed units).

    `prior_state` is the product's recorded propagation record (None = never propagated),
    `model_head` the knowledge model repo_sha, `knowledge_state` = (clean, detail) of the knowledge
    working tree. Missing model_head / knowledge_state fail closed."""
    cfg = config if config is not None else cd.load_config()
    reader = reader or cd._default_reader
    roots = [r if isinstance(r, PurePath) else PurePath(r) for r in content_roots]
    reasons: "list[dict[str, Any]]" = []
    missing = cd.missing_config_keys(cfg)
    if missing:
        return _fail_report(family, platform, ledger,
                            [_reason("config_missing_key", f"missing required config key {k}") for k in missing])
    if ledger.get("family") != family or ledger.get("platform") != platform:
        reasons.append(_reason("ledger_mismatch", f"ledger is for {ledger.get('family')}/{ledger.get('platform')}, "
                               f"gate invoked for {family}/{platform}"))
    for err in cd.validate_ledger(ledger, config=cfg):
        reasons.append(_reason("ledger_invalid", err))
    if not ledger.get("symbol_level", False):
        reasons.append(_reason("no_symbol_level_ground_truth",
                               "ledger is not symbol-level (GT-2 file evidence only): nothing can be proven propagated"))
    head = ledger.get("upstream_head")
    if not head:
        reasons.append(_reason("missing_upstream_head", "ledger carries no upstream_head to record"))
    elif not _SHA40.fullmatch(str(head)):
        reasons.append(_reason("upstream_head_invalid", f"upstream_head {head!r} is not a 40-hex commit sha"))
    elif not model_head:
        reasons.append(_reason("model_head_unavailable",
                               "cannot verify upstream_head: the knowledge model repo_sha is unavailable"))
    elif str(model_head) != str(head):
        reasons.append(_reason("upstream_head_mismatch",
                               f"ledger upstream_head {head} != knowledge model repo_sha {model_head}"))
    units = ledger.get("units") or []
    if not units and ledger.get("delta_sha256") != cd.empty_delta_sha256():
        reasons.append(_reason("delta_not_proven_empty",
                               "ledger has no units but its delta_sha256 is not the empty-delta fingerprint: an empty "
                               "unit list proves nothing unless the delta itself was empty"))
    counted = sum(len(u.get("symbols") or []) + len(u.get("formats") or []) for u in units)
    if ledger.get("delta_symbol_count") != counted:
        reasons.append(_reason("delta_incomplete",
                               f"ledger units cover {counted} symbol(s)/format(s) but the build recorded "
                               f"{ledger.get('delta_symbol_count')!r}: units were removed or the ledger predates the binding"))
    if ledger.get("config_sha256") != cd.config_digest(cfg):
        reasons.append(_reason("config_changed",
                               f"ledger was built with config {str(ledger.get('config_sha256'))[:12]} but the current "
                               f"capability_placement.yaml is {cd.config_digest(cfg)[:12]}: rebuild the ledger"))
    for problem in cd.check_computed_actions(ledger, cfg):
        reasons.append(_reason("computed_action_tampered", problem))
    prior = prior_state or {}
    if prior.get("content_propagated_sha"):
        if ledger.get("base_sha") != prior["content_propagated_sha"]:
            reasons.append(_reason("ledger_does_not_cover",
                                   f"ledger does not cover propagated..head: ledger base {ledger.get('base_sha')!r} != "
                                   f"recorded propagated sha {prior['content_propagated_sha']} (head {head})"))
        elif prior.get("content_propagated_knowledge_commit") and \
                ledger.get("base_knowledge_commit") != prior["content_propagated_knowledge_commit"]:
            reasons.append(_reason("ledger_does_not_cover",
                                   f"ledger does not cover propagated..head: ledger base knowledge commit "
                                   f"{ledger.get('base_knowledge_commit')!r} != recorded "
                                   f"{prior['content_propagated_knowledge_commit']}"))
    if knowledge_state is None:
        reasons.append(_reason("knowledge_tree_unchecked", "the knowledge working tree was not checked"))
    elif not knowledge_state[0]:
        reasons.append(_reason("knowledge_tree_dirty",
                               f"knowledge/{family}/{platform} has uncommitted changes: {knowledge_state[1]}"))
    report = cd.satisfaction_report(ledger, roots, reader=reader, lister=lister, config=cfg)
    for row in report["units"]:
        for surface, s in row["surfaces"].items():
            for problem in s["problems"]:
                reasons.append(_reason("unsatisfied", problem, unit=row["id"], surface=surface))
    ctx = ledger.get("availability_context") or {}
    released = sorted({str(v) for v in (ctx.get("released_versions") or [])} | {str(v) for v in (released_versions or [])})
    unreleased = sorted({str(v) for v in (ctx.get("unreleased_versions") or [])} | {str(v) for v in (unreleased_versions or [])})
    window = cfg["availability"]["qualifier_window_chars"]
    for u in units:
        is_rel = av.is_released(u.get("availability"))
        allowed = sorted(set(released) | _unit_versions(u, is_rel))
        terms = cd.unit_terms_from_symbols(u)
        row = next((r for r in report["units"] if r["id"] == u.get("id")), None)
        seen: "set[str]" = set()
        for surface, s in ((row or {}).get("surfaces") or {}).items():
            for rel in s["evidence_paths"]:
                if rel in seen:
                    continue
                seen.add(rel)
                text, _ = _read_evidence(rel, roots, reader)
                if text is None:
                    continue
                body = cd.strip_frontmatter(text)
                if not is_rel:
                    spans = sorted({sp for t in terms for sp in cd.find_mentions(body, t)})
                    uncovered = av.qualifier_uncovered(body, spans, config=cfg)
                    if uncovered:
                        reasons.append(_reason(
                            "availability_qualifier_missing",
                            f"unit availability is {u.get('availability')!r}; {len(uncovered)} of {len(spans)} mention(s) "
                            f"of {', '.join(terms)} have no availability qualifier within {window} characters",
                            unit=u.get("id"), surface=surface, path=rel))
                for f in av.forbidden_coordinate_scan(body, released_versions=allowed, unreleased_versions=unreleased,
                                                      config=cfg):
                    reasons.append(_reason("forbidden_coordinate",
                                           f"{f['kind']} {f['text']!r} (version {f['version']}) at line {f['line']} is not in "
                                           f"the released set {allowed or '[unknown]'}",
                                           unit=u.get("id"), surface=surface, path=rel))
    return _fail_report(family, platform, ledger, reasons, report["units"], report["refused"])


def default_model_head(family: str, platform: str) -> "str | None":
    """The knowledge model's repo_sha (model.yaml via the analyzer's reader), else the baseline
    ledger's last accepted sha; None when neither exists."""
    try:
        import propagation_analyzer as pa
        sha = pa.read_model_fields(_REPO_ROOT / "knowledge" / family / platform / "merged" / "model.yaml").get("repo_sha")
        if sha:
            return str(sha)
        from baseline_ledger import BaselineLedger
        return (BaselineLedger(family, platform).last_accepted() or {}).get("new_repo_sha")
    except Exception:  # noqa: BLE001 -- unreadable model => unavailable => the gate fails closed
        return None


def default_knowledge_clean(family: str, platform: str) -> "tuple[bool, str]":
    """(clean, detail): `git status --porcelain` of knowledge/<family>/<platform> is empty. A git
    failure is NOT clean."""
    try:
        out = subprocess.run(["git", "status", "--porcelain", "--", f"knowledge/{family}/{platform}"],
                             cwd=str(_REPO_ROOT), capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60, check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        return False, f"git status failed: {exc}"
    if out.returncode != 0:
        return False, f"git status failed: {(out.stderr or '').strip()[:200]}"
    lines = [ln for ln in (out.stdout or "").splitlines() if ln.strip()]
    return (not lines), "; ".join(lines[:5])


def run_gate(family: str, platform: str, ledger_path: "Path | str", content_roots: "Iterable[PurePath | str]", *,
             local_only: bool = False, dry_run: bool = False, state_path: "Path | str | None" = None,
             knowledge_commit_resolver: "Callable[[str, str], str | None] | None" = None,
             config: "dict[str, Any] | None" = None, reader=None, lister=None,
             released_versions: "Iterable[str] | None" = None,
             unreleased_versions: "Iterable[str] | None" = None,
             model_head_resolver: "Callable[[str, str], str | None] | None" = None,
             knowledge_clean_checker: "Callable[[str, str], tuple[bool, str]] | None" = None,
             is_descendant: "Callable[[str, str], bool | None] | None" = None
             ) -> "tuple[int, dict[str, Any]]":
    """Evaluate and, on PASS (and not dry_run), record propagation. Returns (exit_code, report)."""
    ledger = cd.load_ledger(ledger_path)
    if state_path is not None:
        cps.configure(state_path)
    try:
        model_head = (model_head_resolver or default_model_head)(family, platform)
    except Exception:  # noqa: BLE001
        model_head = None
    try:
        knowledge_state: "tuple[bool, str] | None" = (knowledge_clean_checker or default_knowledge_clean)(family, platform)
    except Exception as exc:  # noqa: BLE001
        knowledge_state = (False, f"knowledge check failed: {exc}")
    report = evaluate(ledger, content_roots, family=family, platform=platform, config=config, reader=reader,
                      lister=lister, released_versions=released_versions, unreleased_versions=unreleased_versions,
                      prior_state=cps.read_state(family, platform), model_head=model_head,
                      knowledge_state=knowledge_state)
    if report["verdict"] != PASS:
        return 1, report
    if dry_run:
        return 0, report
    computed = cd.apply_report(ledger, {"units": report["units"]})
    resolver = knowledge_commit_resolver or default_knowledge_commit
    cps.record_propagation(
        family, platform,
        content_propagated_sha=ledger["upstream_head"],
        content_propagated_knowledge_commit=resolver(family, platform),
        local_only=local_only,
        capability_units=[{"id": u["id"], "symbols": u["symbols"], "availability": u["availability"],
                           "dispositions": {s: {"status": d["status"], "evidence_paths": d["evidence_paths"]}
                                            for s, d in u["dispositions"].items()}}
                          for u in computed["units"]],
        gate_verdict=PASS,
        is_descendant=is_descendant,
    )
    report["recorded"] = True
    return 0, report


def _dump(report: "dict[str, Any]") -> str:
    return json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def main(argv: "list[str] | None" = None, *, model_head_resolver=None, knowledge_clean_checker=None,
         knowledge_commit_resolver=None, is_descendant=None) -> int:
    ap = argparse.ArgumentParser(description="Close-time capability-surface gate (sole writer of content propagation).")
    ap.add_argument("--family", required=True)
    ap.add_argument("--platform", required=True)
    ap.add_argument("--ledger", required=True, help="capability_ledger.json built by lib/capability_delta")
    ap.add_argument("--content-root", action="append", default=[], help="content root (repeatable); default <repo>/content")
    ap.add_argument("--state-path", default=None, help="content_propagation_state.json override")
    ap.add_argument("--local-only", action="store_true", help="record the propagation as local-only (not pushed)")
    ap.add_argument("--dry-run", action="store_true", help="evaluate only; never write the state file")
    ap.add_argument("--json-out", default=None, help="also write the JSON report here")
    ap.add_argument("--released-version", action="append", default=[], help="additional released version (repeatable)")
    ap.add_argument("--unreleased-version", action="append", default=[],
                    help="a version content must not cite (repeatable; adds to the ledger's unreleased_versions)")
    ap.add_argument("--config", default=None, help="capability_placement.yaml override (default: the repo file)")
    args = ap.parse_args(argv)
    roots = [Path(r) for r in args.content_root] or [_REPO_ROOT / "content"]
    try:
        config = None
        if args.config:
            import yaml
            config = yaml.safe_load(Path(args.config).read_text(encoding="utf-8")) or {}
        code, report = run_gate(args.family, args.platform, args.ledger, roots, local_only=args.local_only,
                                dry_run=args.dry_run, state_path=args.state_path, config=config,
                                released_versions=args.released_version, unreleased_versions=args.unreleased_version,
                                model_head_resolver=model_head_resolver, knowledge_clean_checker=knowledge_clean_checker,
                                knowledge_commit_resolver=knowledge_commit_resolver, is_descendant=is_descendant)
    except (OSError, ValueError, KeyError, cps.StateWriteError, cps.StateCorrupt, cps.StateLockTimeout) as exc:
        report = {"verdict": FAIL, "family": args.family, "platform": args.platform, "recorded": False,
                  "reasons": [_reason("gate_error", f"{type(exc).__name__}: {exc}")], "units": [],
                  "upstream_head": None}
        code = 2
    text = _dump(report)
    if args.json_out:
        out = Path(args.json_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
    sys.stdout.write(text)
    return code


if __name__ == "__main__":
    sys.exit(main())
