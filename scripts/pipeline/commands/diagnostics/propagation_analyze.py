"""propagation_analyze.py -- discovery analysis CLI over lib/propagation_analyzer (MT074 card B16).

CONTRACT: scripts/pipeline/commands/diagnostics/propagation_analyze.py
  purpose: Wave E stages L2-L4 for products whose knowledge is not refreshed:
             analyze  per product: capability units added since the baseline, English content-presence
                      scan, release / drift evidence -> <out-dir>/<family>__<platform>.json
             rank     read a directory of analyses, evaluate the frozen criteria, write the ranked
                      candidates.json / candidates.md (byte-identical on re-run: no wall-clock values)
  read-only: never writes the propagation state file (fleet_drift / the capability gate own it), never
           checks anything out in a clone, never refreshes knowledge. The only sanctioned clone
           mutation is core.clone_cache's baseline deepening (fetch --deepen), reached through the
           library's `ensure_reachable` seam.
  bounds:  --max-repos N caps the products that need repository access (sorted order; the rest are
           written with status DEFERRED and classified, never silently dropped).
  seams:   --offline-fixtures DIR replays recorded results (no git, no network):
             <DIR>/<family>__<platform>.json = {"adapter_delta": <language_adapters result>,
                "base_ref": sha|null, "head_ref": sha, "reachable": bool | "reachable" | "orphaned" | "unknown" (default true),
                "release": {"release_state", "published_version"} | null, "state": {...} | null}
           --bundles OLD NEW analyses ONE product from two knowledge bundles (no repository).

Usage:
    propagation_analyze.py analyze [--products f/p ...]
        --out-dir DIR [--criteria PATH] [--clone-cache DIR] [--content-root DIR] [--bundles OLD NEW]
        [--offline-fixtures DIR] [--max-repos 8] [--repo-root DIR] [--state PATH] [--registry PATH]
        [--knowledge-root DIR] [--now ISO]
    propagation_analyze.py rank --analysis-dir DIR
        [--criteria PATH] --json-out PATH --md-out PATH

Exit codes: 0 ok, 2 configuration / usage error.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

_PIPELINE_ROOT = Path(__file__).resolve().parents[2]
for _p in (str(_PIPELINE_ROOT), str(_PIPELINE_ROOT / "lib"), str(Path(__file__).resolve().parent)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import fleet_drift as fd  # noqa: E402 -- release-state rule + products loader are reused, not copied
import propagation_analyzer as pa  # noqa: E402

_DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[4]


def _read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def make_release_info(registry: "dict[str, Any]", family: str, platform: str) -> "Callable[[str | None], dict[str, Any]]":
    """callable(head_sha) -> {release_state, release_state_reason, published_version} from the package registry
    (the same compute_release_state rule fleet_drift uses; the published version only counts when verified)."""
    info = (registry.get(family) or {}).get(platform)

    def fn(head: "str | None") -> "dict[str, Any]":
        state, reason = fd.compute_release_state(info, head)
        published = bool(((info or {}).get("verification") or {}).get("published"))
        version = ((info or {}).get("candidate") or {}).get("version") if published else None
        return {"release_state": state, "release_state_reason": reason, "published_version": version}

    return fn


def state_reader_from_file(path: "Path | str") -> "Callable[[str, str], dict | None]":
    """Read-only reader over a content_propagation_state.json file (never writes, never locks)."""
    products = (_read_json(Path(path), {}) or {}).get("products") or {}
    return lambda family, platform: products.get(f"{family}/{platform}")


def _product_list(selected: "list[str] | None", products_path: Path) -> "list[tuple[str, str]]":
    if selected:
        out = []
        for item in selected:
            if "/" not in item:
                raise ValueError(f"--products entries must be family/platform, got {item!r}")
            family, platform = item.split("/", 1)
            out.append((family, platform))
        return sorted(set(out))
    products = _read_json(products_path, None)
    if not isinstance(products, list):
        raise FileNotFoundError(f"{products_path} missing or not a list (pass --products)")
    return sorted({(p["family"], p["platform"]) for p in products if p.get("active", False)})


def _out_name(family: str, platform: str) -> str:
    return f"{family}__{platform}.json"


def _deferred(family: str, platform: str, reason: str, now: "str | None") -> "dict[str, Any]":
    res = pa._skeleton(family, platform)  # noqa: SLF001 -- same record shape as a real analysis
    res["status"], res["error"] = pa.STATUS_DEFERRED, reason
    if now:
        res["volatile"]["generated_at"] = now
    return res


def cmd_analyze(args: argparse.Namespace, *, runner: "Callable[..., Any] | None", out) -> int:
    repo_root = Path(args.repo_root) if args.repo_root else _DEFAULT_REPO_ROOT
    try:
        criteria = pa.load_criteria(args.criteria) if args.criteria else pa.load_criteria(_optional_default(repo_root))
        pairs = _product_list(args.products, repo_root / "data" / "products.json")
    except (pa.CriteriaError, FileNotFoundError, ValueError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    if args.bundles and len(pairs) != 1:
        print("ERROR: --bundles analyses exactly one product (pass a single --products f/p)", file=sys.stderr)
        return 2
    content_root = Path(args.content_root) if args.content_root else repo_root / "content"
    knowledge_root = Path(args.knowledge_root) if args.knowledge_root else repo_root / "knowledge"
    state_path = Path(args.state) if args.state else repo_root / "data" / "content_propagation_state.json"
    registry = _read_json(Path(args.registry) if args.registry else repo_root / "data" / "package_registry.json", {})
    state_reader = state_reader_from_file(state_path)
    now = args.now or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    out_dir = Path(args.out_dir)
    offline = Path(args.offline_fixtures) if args.offline_fixtures else None

    prev_cache = os.environ.get("ASPOSE_CLONE_CACHE")
    if args.clone_cache:
        os.environ["ASPOSE_CLONE_CACHE"] = str(Path(args.clone_cache).resolve())
    try:
        from core import clone_cache as cc  # noqa: PLC0415 -- honours ASPOSE_CLONE_CACHE set above
        repos_used = 0
        counts: "dict[str, int]" = {}
        for family, platform in pairs:
            kwargs: "dict[str, Any]" = {}
            sr = state_reader
            needs_repo = not (args.bundles or offline)
            if needs_repo and repos_used >= args.max_repos:
                res = _deferred(family, platform, f"max_repos={args.max_repos} reached", now)
            else:
                if args.bundles:
                    kwargs["bundles"] = (args.bundles[0], args.bundles[1])
                    kwargs["release_info"] = make_release_info(registry, family, platform)
                elif offline:
                    fx = _read_json(offline / _out_name(family, platform), None)
                    if fx is None:
                        res = pa._skeleton(family, platform)  # noqa: SLF001
                        res["status"], res["error"] = pa.STATUS_ERROR, f"offline fixture missing for {family}/{platform}"
                        _write(out_dir, family, platform, res)
                        counts[res["status"]] = counts.get(res["status"], 0) + 1
                        continue
                    kwargs.update(adapter=pa.RecordedAdapter(fx.get("adapter_delta") or {}),
                                  base_ref=fx.get("base_ref"), head_ref=fx.get("head_ref"),
                                  repo_path=offline,
                                  release_info=fx.get("release") or make_release_info(registry, family, platform),
                                  ensure_reachable=(lambda _p, _s, v=fx.get("reachable", True): v))
                    if fx.get("state") is not None:
                        sr = (lambda _f, _p, st=fx["state"]: st)
                else:
                    repos_used += 1
                    kwargs.update(repo_path=cc.clone_path(family, platform),
                                  release_info=make_release_info(registry, family, platform))
                res = pa.analyze_product(
                    family, platform, content_root=content_root, knowledge_root=knowledge_root, criteria=criteria,
                    state_reader=sr, runner=runner, now=now, **kwargs)
            _write(out_dir, family, platform, res)
            counts[res["status"]] = counts.get(res["status"], 0) + 1
    except ValueError as exc:  # cache_root() rejects an obsolete cache path
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    finally:
        if args.clone_cache:
            if prev_cache is None:
                os.environ.pop("ASPOSE_CLONE_CACHE", None)
            else:
                os.environ["ASPOSE_CLONE_CACHE"] = prev_cache
    print("propagation_analyze analyze: " + ", ".join(f"{k}={v}" for k, v in sorted(counts.items()))
          + f" -> {out_dir}", file=out)
    return 0


def _optional_default(repo_root: Path) -> "Path | None":
    p = repo_root / "scripts" / "pipeline" / "config" / "discovery_criteria.yaml"
    return p if p.is_file() else None


def _write(out_dir: Path, family: str, platform: str, res: "dict[str, Any]") -> None:
    pa.write_text(out_dir / _out_name(family, platform), pa.dumps(res))


def cmd_rank(args: argparse.Namespace, *, out) -> int:
    repo_root = Path(args.repo_root) if args.repo_root else _DEFAULT_REPO_ROOT
    try:
        criteria = pa.load_criteria(args.criteria) if args.criteria else pa.load_criteria(_optional_default(repo_root))
    except pa.CriteriaError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    adir = Path(args.analysis_dir)
    if not adir.is_dir():
        print(f"ERROR: --analysis-dir {adir} is not a directory", file=sys.stderr)
        return 2
    analyses = []
    for f in sorted(adir.glob("*.json")):
        data = _read_json(f, None)
        if isinstance(data, dict) and data.get("kind") == pa.ANALYSIS_KIND:
            analyses.append(data)
    report = pa.build_candidates_report(analyses, criteria)
    pa.write_text(args.json_out, pa.dumps(report))
    pa.write_text(args.md_out, pa.render_markdown(report))
    s = report["summary"]
    print(f"propagation_analyze rank: {s['total']} products, {s['candidates']} candidate(s) | "
          + ", ".join(f"{k}={v}" for k, v in s["by_classification"].items()), file=out)
    return 0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="propagation_analyze.py", description="Wave E discovery analysis (read-only)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("analyze", help="analyse products -> <out-dir>/<family>__<platform>.json")
    a.add_argument("--products", nargs="+", metavar="F/P", help="default: every active product in data/products.json")
    a.add_argument("--out-dir", required=True, metavar="DIR")
    a.add_argument("--criteria", metavar="PATH", help="discovery criteria YAML (default: config/discovery_criteria.yaml if present, else embedded defaults)")
    a.add_argument("--clone-cache", metavar="DIR", help="clone cache root (sets ASPOSE_CLONE_CACHE for this run)")
    a.add_argument("--content-root", metavar="DIR", help="default: <repo-root>/content")
    a.add_argument("--bundles", nargs=2, metavar=("OLD", "NEW"), help="analyse ONE product from two knowledge bundle dirs")
    a.add_argument("--offline-fixtures", metavar="DIR", help="replay recorded adapter results; no git, no network")
    a.add_argument("--max-repos", type=int, default=8, metavar="N", help="max products needing repository access (default 8)")
    a.add_argument("--repo-root", metavar="DIR", help="override the repository root (tests)")
    a.add_argument("--state", metavar="PATH", help="content_propagation_state.json to READ (default: repo data file)")
    a.add_argument("--registry", metavar="PATH", help="package_registry.json (default: repo data file)")
    a.add_argument("--knowledge-root", metavar="DIR", help="default: <repo-root>/knowledge")
    a.add_argument("--now", metavar="ISO", help="timestamp recorded under `volatile` (default: now)")
    r = sub.add_parser("rank", help="rank an analysis directory -> candidates.json / candidates.md")
    r.add_argument("--analysis-dir", required=True, metavar="DIR")
    r.add_argument("--criteria", metavar="PATH")
    r.add_argument("--json-out", required=True, metavar="PATH")
    r.add_argument("--md-out", required=True, metavar="PATH")
    r.add_argument("--repo-root", metavar="DIR", help="override the repository root (tests)")
    return ap


def main(argv: "list[str] | None" = None, *, runner: "Callable[..., Any] | None" = None, out=None) -> int:
    out = out or sys.stdout
    args = build_parser().parse_args(argv)
    if args.cmd == "analyze":
        return cmd_analyze(args, runner=runner, out=out)
    return cmd_rank(args, out=out)


if __name__ == "__main__":
    sys.exit(main())
