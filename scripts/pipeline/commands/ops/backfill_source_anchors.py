"""backfill_source_anchors.py -- mechanically anchor the pre-2026-08-29
capabilities that docs/id-mapping.md already claims are ported/same, using
docs/id-mapping.md as the mapping source of truth.

TASK_BACKLOG.md SYNC-8. HONEST SCOPE: this establishes a MECHANICAL anchor
(the source file exists at the expected path; its current per-file commit
SHA, via `git log -1 -- path`) for every capability id-mapping.md already
claims is ported/same. It does NOT re-review semantic content equivalence
-- that would mean reading and comparing ~84 skill docs by hand, a
separate, larger task. What this DOES buy: from this point forward,
detect_source_drift.py can tell you the moment any of these source files
changes again, instead of the silent 3.5-month gap that motivated this
whole sync. Anchors written by this tool are labeled
verification_method: "mechanical_existence_and_current_sha" so nobody
later mistakes them for a semantic re-review.

Rows excluded by design (read from id-mapping.md's own Notes column):
  - "DIVERGE" -- source and target have genuinely DIFFERENT skills under a
    colliding ID; anchoring source_path against the wrong target would be
    actively wrong, not just incomplete.
  - "Gap" / "Reserved" / "*(unassigned)*" -- no real skill on one or both sides.
  - "foss-only" -- no source counterpart to anchor against at all.

Usage:
    export SOURCE_REPO_PATH=/path/to/aspose-org-checkout
    .venv/bin/python scripts/pipeline/commands/ops/backfill_source_anchors.py --dry-run
    .venv/bin/python scripts/pipeline/commands/ops/backfill_source_anchors.py --apply
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    import yaml
    _HAS_YAML = True
except ImportError:
    _HAS_YAML = False

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
_ID_MAPPING_FILE = _REPO_ROOT / "docs" / "id-mapping.md"
_ANCHORS_FILE = _REPO_ROOT / "docs" / "parity" / "source-anchors.yaml"

_ROW_RE = re.compile(
    r"^\|\s*(?P<foss_id>[^|]+?)\s*\|\s*(?P<foss_name>[^|]+?)\s*\|\s*"
    r"(?P<aspose_id>[^|]+?)\s*\|\s*(?P<aspose_name>[^|]+?)\s*\|\s*(?P<notes>[^|]+?)\s*\|\s*$"
)
_EXCLUDE_NOTE_MARKERS = ("DIVERGE", "Gap", "Reserved", "foss-only")
_PLACEHOLDER_RE = re.compile(r"^\*\(.*\)\*$")
_BOLD_RE = re.compile(r"^\*\*(.+)\*\*$")


def parse_mapping_table(text: str) -> list[dict]:
    rows = []
    in_table = False
    for line in text.splitlines():
        if line.strip().startswith("## Mapping Table"):
            in_table = True
            continue
        if in_table and line.strip().startswith("## "):
            break
        if not in_table:
            continue
        match = _ROW_RE.match(line.strip())
        if not match:
            continue
        d = match.groupdict()
        if d["foss_id"] == "foss-launcher ID":
            continue  # header row
        if "---" in d["foss_id"]:
            continue  # separator row
        # Strip markdown BOLD only (id-mapping.md bolds a few names to flag
        # divergence/renumbering, e.g. "**no-downgrade-guard**") -- without
        # this, target_path would literally contain "**", never resolving
        # to a real file. Deliberately NOT stripping single "*": that's the
        # placeholder convention ("*(unassigned)*", "*(none)*") is_eligible
        # depends on below to detect gaps -- stripping it would silently
        # break that detection.
        d["foss_name"] = _BOLD_RE.sub(r"\1", d["foss_name"])
        d["aspose_name"] = _BOLD_RE.sub(r"\1", d["aspose_name"])
        rows.append(d)
    return rows


def is_eligible(row: dict) -> bool:
    if any(marker in row["notes"] for marker in _EXCLUDE_NOTE_MARKERS):
        return False
    if _PLACEHOLDER_RE.match(row["foss_name"]) or _PLACEHOLDER_RE.match(row["aspose_name"]):
        return False
    if row["aspose_name"] in ("*(none)*",) or row["foss_name"] in ("*(none)*",):
        return False
    return True


def resolve_source_repo() -> Path:
    raw = os.environ.get("SOURCE_REPO_PATH", "").strip()
    if not raw:
        raise ValueError("SOURCE_REPO_PATH is not set")
    path = Path(raw).expanduser().resolve()
    if not (path / ".git").exists():
        raise ValueError("SOURCE_REPO_PATH is not a git working tree: " + raw)
    return path


def _run_git(args, repo_root):
    return subprocess.run(["git"] + args, capture_output=True, text=True, cwd=str(repo_root), timeout=30)


def resolve_source_path(source_repo: Path, aspose_name: str) -> "str | None":
    """Prefer skills/{name}.md (both repos' canonical convention); fall back
    to .claude/commands/{name}.md for anything not mirrored that way."""
    for candidate in (f"skills/{aspose_name}.md", f".claude/commands/{aspose_name}.md"):
        if (source_repo / candidate).is_file():
            return candidate
    return None


def current_file_sha(source_repo: Path, rel_path: str) -> "str | None":
    result = _run_git(["log", "-1", "--format=%H", "HEAD", "--", rel_path], source_repo)
    sha = result.stdout.strip()
    return sha if result.returncode == 0 and sha else None


def load_existing_anchors() -> list[dict]:
    if not _HAS_YAML or not _ANCHORS_FILE.exists():
        return []
    data = yaml.safe_load(_ANCHORS_FILE.read_text(encoding="utf-8")) or {}
    return data.get("anchors", []) or []


def build_candidates(source_repo: Path, mapping_rows: list[dict], already_anchored_ids: set) -> dict:
    """Returns {"anchorable": [...], "missing_source": [...], "already_anchored": [...]}."""
    anchorable = []
    missing_source = []
    already_anchored = []

    for row in mapping_rows:
        if not is_eligible(row):
            continue
        foss_id = row["foss_id"]
        if foss_id in already_anchored_ids:
            already_anchored.append(row)
            continue

        source_path = resolve_source_path(source_repo, row["aspose_name"])
        if source_path is None:
            missing_source.append(row)
            continue

        sha = current_file_sha(source_repo, source_path)
        if sha is None:
            missing_source.append(row)
            continue

        anchorable.append({
            "target_path": f"skills/{row['foss_name']}.md",
            "source_path": source_path,
            "capability_id": foss_id,
            "commit_sha": sha,
            "aspose_id": row["aspose_id"],
        })

    return {"anchorable": anchorable, "missing_source": missing_source, "already_anchored": already_anchored}


def render_anchor_yaml(candidate: dict, verified_at: str) -> str:
    lines = [
        f"  - target_path: {candidate['target_path']}",
        f"    source_path: {candidate['source_path']}",
        f"    capability_id: {candidate['capability_id']}",
        f"    commit_sha: {candidate['commit_sha']}",
        f'    verified_at: "{verified_at}"',
        "    verification_method: mechanical_existence_and_current_sha",
        "    notes: >",
        f"      Backfilled 2026-08-29 (TASK_BACKLOG.md SYNC-8) from docs/id-mapping.md's",
        f"      existing '{candidate['aspose_id']}' mapping row. Mechanical anchor only --",
        f"      source file confirmed to exist at this path, commit_sha is its own most",
        f"      recent commit. NOT a semantic content re-review; see TASK_BACKLOG.md SYNC-8",
        f"      for what that would still require.",
    ]
    return "\n".join(lines) + "\n"


def main(argv: "list[str] | None" = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="Report only; write nothing")
    mode.add_argument("--apply", action="store_true", help="Append new anchors to source-anchors.yaml")
    args = parser.parse_args(argv)

    try:
        source_repo = resolve_source_repo()
    except ValueError as exc:
        print("ERROR: " + str(exc), file=sys.stderr)
        return 2

    mapping_rows = parse_mapping_table(_ID_MAPPING_FILE.read_text(encoding="utf-8"))
    existing = load_existing_anchors()
    already_anchored_ids = {a.get("capability_id") for a in existing if a.get("capability_id")}

    result = build_candidates(source_repo, mapping_rows, already_anchored_ids)

    print(f"Eligible mapping rows: {sum(1 for r in mapping_rows if is_eligible(r))}")
    print(f"  Already anchored:   {len(result['already_anchored'])}")
    print(f"  Anchorable now:     {len(result['anchorable'])}")
    print(f"  Missing source:     {len(result['missing_source'])}  (needs manual investigation, NOT anchored)")

    if result["missing_source"]:
        print("\nMissing-source rows (source file not found at either skills/{name}.md or "
              ".claude/commands/{name}.md -- likely renamed, moved, or my path-guessing heuristic "
              "is wrong for these):")
        for row in result["missing_source"]:
            print(f"  {row['foss_id']} / {row['foss_name']}  <-  aspose {row['aspose_id']} / {row['aspose_name']}")

    if args.dry_run:
        print(f"\nDry run: would append {len(result['anchorable'])} new anchor(s). "
              f"Re-run with --apply to write them.")
        return 0

    if not result["anchorable"]:
        print("\nNothing new to anchor.")
        return 0

    verified_at = datetime.now(tz=timezone.utc).isoformat().replace("+00:00", "Z")
    new_yaml = "".join(render_anchor_yaml(c, verified_at) for c in result["anchorable"])
    current_text = _ANCHORS_FILE.read_text(encoding="utf-8")
    with open(_ANCHORS_FILE, "a", encoding="utf-8", newline="\n") as f:
        f.write(new_yaml)
    print(f"\nAppended {len(result['anchorable'])} new anchor(s) to {_ANCHORS_FILE.relative_to(_REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
