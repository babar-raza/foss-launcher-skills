"""registry_backfill.py — Mission MT018-2026-08-01-PACKAGE-IDENTITY-COVERAGE, TC-MT018-06.

Backfill orchestrator: for each family/platform pair flagged uncovered by
registry_coverage_scan.py, determines the real package identity and writes
a LIVE-VERIFIED entry to data/package_registry.json. Never writes an
unverified guess -- every entry's published state and candidate name comes
from an actual, evidenced registry check performed during this run.

Strategy per entry, in order (mirrors the manual audit methodology, made
reusable rather than one-off):
  1. Manifest extraction (package_manifest.py against the local FOSS repo
     clone at runs/.clone_cache/) -- highest confidence when it yields a name.
  2. If the manifest name resolves live: identity_basis is "manifest-extracted"
     (name contains "foss") or requires corroboration via is_corroborated_match()
     otherwise.
  3. If the manifest is silent or its name doesn't resolve: try the
     naming-convention guess (naming_convention_candidate()).
  4. If that doesn't resolve either: use the adapter's search() (where one
     exists -- pypi/npm/nuget/cargo) and apply is_corroborated_match() to
     every hit, accepting only a genuinely corroborated match.
  5. If nothing resolves: record verification.published=false with the best
     available candidate (manifest name, else the convention guess) and
     identity_basis=null (no live check ever confirmed an identity -- this
     is a `scout_source: naming-convention-fallback`-style entry, same
     pattern as words/net's pre-2026-08-01 state).

Maven is out of scope (handled by the existing /foss-java-publish, S-110,
path) -- registry_coverage_scan.py's uncovered list never contains a java
pair since all 4 launched java products were already registered by MT015.

CLI:
    PYTHONPATH=scripts/pipeline .venv/Scripts/python -m commands.ops.registry_backfill --dry-run
    PYTHONPATH=scripts/pipeline .venv/Scripts/python -m commands.ops.registry_backfill --execute
    PYTHONPATH=scripts/pipeline .venv/Scripts/python -m commands.ops.registry_backfill --execute --only cells/net,3d/net
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_PIPELINE_ROOT = Path(__file__).resolve().parents[2]
if str(_PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_ROOT))
_LIB_DIR = str(_PIPELINE_ROOT / "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)

from lib.package_registries import is_corroborated_match  # noqa: E402
from lib.package_registries import pypi, npm, nuget, go, cargo  # noqa: E402
from lib.package_registry_data import naming_convention_candidate, load_registry  # noqa: E402
from extraction.package_manifest import parse_manifest  # noqa: E402
from commands.ops.registry_coverage_scan import scan_coverage  # noqa: E402

_DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[4]
_REPO_ROOT = _DEFAULT_REPO_ROOT
_CLONE_CACHE = _DEFAULT_REPO_ROOT / "runs" / ".clone_cache"
_REGISTRY_PATH = _DEFAULT_REPO_ROOT / "data" / "package_registry.json"

_ADAPTERS = {"pypi": pypi, "nuget": nuget, "npm": npm, "go_modules": go, "cargo": cargo}

_PLATFORM_TO_REGISTRY_TYPE = {
    "python": "pypi",
    "net": "nuget",
    "cpp": "nuget",
    "typescript": "npm",
    "javascript": "npm",
    "go": "go_modules",
    "rust": "cargo",
    "java": "maven",
}


def configure(*, repo_root: "Path | str | None" = None) -> None:
    global _REPO_ROOT, _CLONE_CACHE, _REGISTRY_PATH
    _REPO_ROOT = Path(repo_root) if repo_root is not None else _DEFAULT_REPO_ROOT
    _CLONE_CACHE = _REPO_ROOT / "runs" / ".clone_cache"
    _REGISTRY_PATH = _REPO_ROOT / "data" / "package_registry.json"


def _find_clone_cache_dir(family: str, platform: str) -> "Path | None":
    """runs/.clone_cache/ directory names follow aspose_{family}_{platform}
    (confirmed convention, e.g. aspose_cells_net, aspose_pdf_python)."""
    candidate = _CLONE_CACHE / f"aspose_{family}_{platform}"
    return candidate if candidate.is_dir() else None


def _build_candidate(registry_type: str, name: str) -> dict:
    return {"module_path": name} if registry_type == "go_modules" else {"name": name}


def _expected_repo_fragment(family: str) -> str:
    """The generic FOSS-org naming convention (aspose-{family}-foss) used
    as the corroboration target -- every real FOSS org observed this
    session (aspose-note-foss, aspose-cells-foss, aspose-slides-foss, ...)
    follows this exact pattern."""
    return f"aspose-{family}-foss"


def backfill_entry(family: str, platform: str, *, fetch=None) -> "dict | None":
    """Determine the real, live-verified identity for one family/platform.
    Returns a full PackageEntry dict, or None if platform maps to maven
    (out of scope -- handled by S-110)."""
    registry_type = _PLATFORM_TO_REGISTRY_TYPE.get(platform)
    if registry_type is None or registry_type == "maven":
        return None

    adapter = _ADAPTERS[registry_type]
    expected_fragment = _expected_repo_fragment(family)
    checked_at = datetime.now(timezone.utc).date().isoformat()

    # Step 1: manifest extraction
    manifest_name = None
    scout_source = None
    repo_dir = _find_clone_cache_dir(family, platform)
    if repo_dir:
        manifest_info = parse_manifest(repo_dir, platform)
        manifest_name = manifest_info.get("name") or None
        if manifest_name:
            scout_source = f"package_manifest.py:{platform}"

    # Step 2/3: candidates to try, in priority order
    tried_names = set()
    candidates: list[tuple[str, str]] = []  # (name, source_label)
    if manifest_name:
        candidates.append((manifest_name, "manifest"))
    convention = naming_convention_candidate(family, platform, registry_type)
    # naming_convention_candidate()'s output shape is discriminated by
    # registry_type just like PackageEntry.candidate itself -- go_modules
    # uses "module_path", everything else uses "name".
    convention_name = None
    if convention:
        convention_name = convention.get("module_path") if registry_type == "go_modules" else convention.get("name")
    if convention_name and convention_name != manifest_name:
        candidates.append((convention_name, "convention"))

    for name, source in candidates:
        if name in tried_names:
            continue
        tried_names.add(name)
        candidate = _build_candidate(registry_type, name)
        result = adapter.check_published(candidate, fetch=fetch)
        if result.ambiguous or not result.published:
            continue
        has_foss = "foss" in name.lower()
        if has_foss:
            basis = "manifest-extracted" if source == "manifest" else "foss-convention-match"
        elif is_corroborated_match(name, result.project_url, expected_fragment):
            basis = "corroborated-non-convention-match"
        else:
            continue  # a live package exists under this name, but it isn't ours
        return _build_entry(
            registry_type, candidate, result, basis, checked_at,
            candidate_owner=None, scouted_at=checked_at,
            scout_source=scout_source if source == "manifest" else "naming-convention-fallback",
        )

    # Step 4: search fallback (pypi/npm/nuget/cargo only)
    if hasattr(adapter, "search"):
        for result in adapter.search(family, fetch=fetch):
            if not result.candidate_name:
                continue
            if registry_type == "nuget" and platform == "cpp" and "cpp" not in result.candidate_name.lower():
                # NuGet is the only registry shared across two platforms
                # (net/cpp) -- a family-only search ("aspose email") returns
                # both variants indiscriminately. Real case caught 2026-08-01:
                # email/cpp's search fell back to "Aspose.Email.Foss" (the
                # .NET package, which does contain "foss" and would otherwise
                # pass is_corroborated_match) purely because no cpp-specific
                # package exists. Every real cpp NuGet ID observed this
                # session embeds "Cpp" (Aspose.Cells.Cpp.FOSS), so require it
                # here rather than trust family-name matching alone.
                continue
            if is_corroborated_match(result.candidate_name, result.project_url, expected_fragment):
                candidate = _build_candidate(registry_type, result.candidate_name)
                return _build_entry(
                    registry_type, candidate, result, "corroborated-non-convention-match",
                    checked_at, candidate_owner=None, scouted_at=checked_at,
                    scout_source="registry-search",
                )

    # Step 5: nothing resolved -- record honestly as unpublished
    best_name = manifest_name or convention_name
    candidate = _build_candidate(registry_type, best_name) if best_name else {}
    return {
        "registry_type": registry_type,
        "candidate": candidate,
        "candidate_owner": "asposefoss" if registry_type != "go_modules" else f"aspose-{family}-foss",
        "scouted_at": checked_at if best_name else None,
        "scout_source": scout_source or ("naming-convention-fallback" if convention_name else None),
        "verification": {
            "published": False,
            "verified_at": checked_at,
            "verified_owner": None,
            "evidence_url": None,
            "evidence_note": (
                f"Backfilled {checked_at}: no live match found for any tried candidate "
                f"({', '.join(n for n, _ in candidates) or 'none available'}); "
                f"recorded as not-yet-published with the best available candidate name."
            ),
            "method": f"{registry_type}-backfill-scan",
            # 0, not 1 (2026-09-07 fix): this one-time backfill check is scouting/
            # population, not a watch-cycle observation -- package_publish_watch.py's
            # debounce counts INDEPENDENT SCHEDULED-WATCH observations toward its
            # 2-required threshold, and a backfilled entry has had zero of those. A
            # seed of 1 let this single backfill check silently stand in for one of
            # the two required watch-cycle observations, so the watcher's very first
            # real run (which independently rechecks and agrees) already satisfied
            # "2 checks agree" -- confirmed live as the root cause of 13 registry
            # entries (3d/python, cells/typescript, words/net among them) re-firing
            # an identical GitHub issue every single day for 5-9 days once each went
            # live, because nothing ever marks a fired finding as consumed under CI's
            # --no-persist-counters mode. 0 makes a freshly-backfilled entry behave
            # exactly like an organically-added one: no watch-cycle observation has
            # actually happened yet, which is literally true.
            "consecutive_checks_agreeing": 0,
            "identity_basis": None,
        },
        "owner_match": None,
    }


def _build_entry(registry_type, candidate, result, identity_basis, checked_at,
                  *, candidate_owner, scouted_at, scout_source) -> dict:
    return {
        "registry_type": registry_type,
        "candidate": candidate,
        "candidate_owner": result.verified_owner or candidate_owner or "asposefoss",
        "scouted_at": scouted_at,
        "scout_source": scout_source,
        "verification": {
            "published": True,
            "verified_at": checked_at,
            "verified_owner": result.verified_owner,
            "evidence_url": result.evidence_url,
            "evidence_note": (
                f"Live-verified {checked_at} via {result.method}"
                + (f"; identity corroborated via project_url {result.project_url}"
                   if identity_basis == "corroborated-non-convention-match" else "")
                + "."
            ),
            "method": result.method,
            # 0, not 1 (2026-09-07 fix, see the sibling branch above for the full
            # explanation): a one-time backfill check is scouting, not a watch-cycle
            # observation. Largely inert here since this branch already sets
            # published=True (package_publish_watch.py's debounce only gates the
            # false->true transition, via this same field), but kept consistent
            # with the sibling branch rather than leaving one of the two write
            # sites carrying the old, since-proven-wrong seed value.
            "consecutive_checks_agreeing": 0,
            "identity_basis": identity_basis,
        },
        "owner_match": None,
    }


def run_backfill(*, only: "list[tuple[str, str]] | None" = None, fetch=None) -> dict[str, Any]:
    """Run the full backfill. Returns {"entries": {family: {platform: entry}}, "summary": [...]}."""
    if only is not None:
        pairs = only
    else:
        coverage = scan_coverage()
        pairs = [tuple(p.split("/")) for p in coverage["uncovered_pairs"]]

    entries: dict[str, dict[str, Any]] = {}
    summary = []
    for family, platform in pairs:
        entry = backfill_entry(family, platform, fetch=fetch)
        if entry is None:
            summary.append(f"{family}/{platform}: SKIPPED (maven, out of scope)")
            continue
        entries.setdefault(family, {})[platform] = entry
        v = entry["verification"]
        summary.append(
            f"{family}/{platform}: published={v['published']} "
            f"candidate={entry['candidate'].get('name') or entry['candidate'].get('module_path')} "
            f"basis={v.get('identity_basis')}"
        )
    return {"entries": entries, "summary": summary}


def write_entries(entries: dict[str, dict[str, Any]]) -> None:
    """Merge backfilled entries into the real registry file and write atomically."""
    registry = load_registry(_REGISTRY_PATH) if _REGISTRY_PATH.is_file() else {}
    for family, platforms in entries.items():
        registry.setdefault(family, {}).update(platforms)
    tmp = _REGISTRY_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(registry, indent=2) + "\n", encoding="utf-8")
    tmp.replace(_REGISTRY_PATH)


def main(argv: "list[str] | None" = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(prog="registry_backfill")
    parser.add_argument("--execute", action="store_true", help="Write results to data/package_registry.json (default: dry-run)")
    parser.add_argument("--only", default=None, help="Comma-separated family/platform pairs to backfill (default: all uncovered)")
    args = parser.parse_args(argv)

    only = None
    if args.only:
        only = [tuple(p.split("/")) for p in args.only.split(",")]

    result = run_backfill(only=only)
    for line in result["summary"]:
        print(line)

    if args.execute:
        write_entries(result["entries"])
        print(f"\nWrote {sum(len(p) for p in result['entries'].values())} entries to {_REGISTRY_PATH}")
    else:
        print(f"\nDRY-RUN: {sum(len(p) for p in result['entries'].values())} entries would be written. Re-run with --execute to apply.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
