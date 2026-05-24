#!/usr/bin/env python3
"""semantic_source_classifier.py — Pre-update source semantic classification.

CONTRACT: scripts/pipeline/commands/ops/semantic_source_classifier.py
  purpose: Classify each file in the upstream source diff between old/new SHAs.
           Produces semantic_source_delta.json for use by semantic_refresh_guard.py.
           Runs BEFORE page-update step in S-84. Does NOT require page_decisions.json.
  inputs:  family, platform, --old-sha, --new-sha, clone cache, --knowledge-delta (optional)
  outputs: reports/refresh_review/{family}/{platform}/semantic_source_delta.json
  idempotent: yes — overwrites on re-run

Exit codes:
  0 = classification complete (JSON always written, even for UNKNOWN cases)
  1 = clone not found / git not available
  2 = old SHA not in history (shallow clone); UNKNOWN written to output
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[4]
_PIPELINE_DIR = Path(__file__).resolve().parents[2]
if str(_PIPELINE_DIR) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_DIR))


# ---------------------------------------------------------------------------
# Classification rules (applied in priority order)
# ---------------------------------------------------------------------------

def _classify_file(path: str) -> tuple[str, str]:
    """Return (category, reason) for a changed file path."""
    p = path.lower()

    # 1. Test files
    if "/tests/" in p or "/test/" in p or path.startswith("tests/") or path.startswith("test/"):
        return "TEST_ONLY", "test directory"
    if "_test.py" in p or Path(path).name.lower().startswith("test_"):
        return "TEST_ONLY", "test file naming pattern"

    # 2. Build/config files
    ext = Path(path).suffix.lower()
    build_exts = {".toml", ".cfg", ".ini", ".csproj", ".vbproj", ".fsproj"}
    if ext in build_exts:
        return "BUILD_ONLY", f"build/config file ({ext})"
    build_names = {"setup.py", "setup.cfg", "makefile", "dockerfile", "codeowners"}
    if Path(path).name.lower() in build_names:
        return "BUILD_ONLY", f"build file ({Path(path).name})"
    if "requirements" in Path(path).stem.lower() and ext in {".txt", ".in"}:
        return "BUILD_ONLY", "requirements file"
    if path.lower().endswith("pom.xml"):
        return "BUILD_ONLY", "Maven pom.xml"

    # 3. Upstream docs
    doc_exts = {".md", ".rst", ".txt"}
    if ext in doc_exts:
        doc_names = {"readme", "changelog", "license", "security", "agents"}
        if Path(path).stem.lower() in doc_names or Path(path).name.lower().startswith("readme"):
            return "DOC_ONLY_UPSTREAM", f"upstream doc ({Path(path).name})"
    if ext == ".html" and ("docs/apidocs" in p or "api_docs" in p or "apidocs/" in p):
        return "DOC_ONLY_UPSTREAM", "generated apidocs HTML"

    # 4. Examples / samples
    if "/examples/" in p or path.startswith("examples/") or "/samples/" in p or path.startswith("samples/"):
        return "EXAMPLE_CHANGE", "examples directory"

    # 5. Source files — classify by location
    source_exts = {".py", ".cs", ".java", ".cpp", ".h", ".hpp", ".ts", ".js"}
    if ext in source_exts:
        internal_markers = {"_internal", "_private", "internal/", "private/", "vendor/"}
        is_internal = any(m in p for m in internal_markers)
        src_markers = {"src/", "/lib/", "aspose_", "/com/aspose", "/aspose."}
        is_in_src = any(m in p for m in src_markers)
        if is_in_src and not is_internal:
            return "DEFINITELY_USER_FACING", f"public source file in {ext} package"
        elif not is_internal:
            return "PROBABLY_USER_FACING", f"source file {ext} (location unclear)"
        else:
            return "INTERNAL_ONLY", f"internal source file"

    return "UNKNOWN", f"unclassified file ({ext})"


def _aggregate_impact(categories: list[str]) -> str:
    """Aggregate file categories into overall impact level."""
    cat_set = set(categories)
    if "DEFINITELY_USER_FACING" in cat_set:
        return "HIGH"
    if "PROBABLY_USER_FACING" in cat_set or "EXAMPLE_CHANGE" in cat_set:
        return "MEDIUM"
    if cat_set <= {"TEST_ONLY", "BUILD_ONLY", "DOC_ONLY_UPSTREAM"}:
        return "INTERNAL_ONLY"
    if "UNKNOWN" in cat_set and not (cat_set & {"DEFINITELY_USER_FACING", "PROBABLY_USER_FACING", "EXAMPLE_CHANGE"}):
        return "UNKNOWN"
    return "MEDIUM"  # mixed with UNKNOWN → conservative


def _run_git_diff(clone_path: Path, old_sha: str, new_sha: str) -> tuple[list[str], str, bool]:
    """Run git diff --name-status. Returns (lines, error, shallow_clone_issue)."""
    try:
        result = subprocess.run(
            ["git", "diff", "--name-status", f"{old_sha}..{new_sha}"],
            cwd=clone_path,
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode == 0:
            lines = [l.strip() for l in result.stdout.splitlines() if l.strip()]
            return lines, "", False
        err = result.stderr.lower()
        if "unknown revision" in err or "bad revision" in err or "not a tree" in err:
            return [], result.stderr.strip(), True
        return [], result.stderr.strip(), False
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        return [], str(e), False


def _load_knowledge_delta(delta_path: Path | None) -> dict:
    """Load knowledge_delta.json; return {} if absent."""
    if not delta_path or not delta_path.is_file():
        return {}
    try:
        return json.loads(delta_path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}


def _find_clone_path(repo_root: Path, family: str, platform: str, override: str | None) -> Path | None:
    """Resolve clone cache directory for this family/platform."""
    if override:
        p = Path(override)
        return p if p.is_dir() else None
    name = f"aspose_{family}_{platform}"
    clone = repo_root / "runs" / ".clone_cache" / name
    return clone if clone.is_dir() else None


def _write_output(result: dict, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, indent=2), encoding="utf-8")


def classify(
    family: str,
    platform: str,
    old_sha: str,
    new_sha: str,
    *,
    repo_root: Path | None = None,
    clone_cache_override: str | None = None,
    knowledge_delta_path: Path | None = None,
    out_path: Path | None = None,
) -> tuple[dict, int]:
    """
    Classify source diff between old_sha and new_sha.

    Returns (result_dict, exit_code).
    Exit codes: 0=ok, 1=clone not found, 2=shallow clone/diff unavailable.
    """
    root = repo_root or _REPO_ROOT
    clone_path = _find_clone_path(root, family, platform, clone_cache_override)

    if out_path is None:
        out_path = root / "reports" / "refresh_review" / family / platform / "semantic_source_delta.json"

    result: dict = {
        "family": family,
        "platform": platform,
        "old_source_sha": old_sha,
        "new_source_sha": new_sha,
        "source_changed": old_sha != new_sha,
        "clone_path": str(clone_path) if clone_path else None,
        "diff_available": False,
        "source_change_impact": "UNKNOWN",
        "files_classified": [],
        "claim_delta_count": 0,
        "claim_delta_detail": {
            "new_claims": 0, "modified_claims": 0, "removed_claims": 0,
            "new_apis": 0, "modified_apis": 0, "removed_apis": 0,
        },
        "proof": [],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    exit_code = 0

    if not clone_path:
        result["proof"].append(f"Clone cache not found for {family}/{platform} at runs/.clone_cache/aspose_{family}_{platform}")
        _write_output(result, out_path)
        return result, 1

    if old_sha == new_sha:
        result["source_changed"] = False
        result["source_change_impact"] = "INTERNAL_ONLY"
        result["diff_available"] = True
        result["proof"].append("old_sha == new_sha — no source change")
        _write_output(result, out_path)
        return result, 0

    diff_lines, err, shallow = _run_git_diff(clone_path, old_sha, new_sha)

    if shallow or (not diff_lines and err):
        result["diff_available"] = False
        result["source_change_impact"] = "UNKNOWN"
        result["proof"].append(
            f"Shallow clone: diff unavailable for SHA range {old_sha}..{new_sha}"
            if shallow else f"git diff error: {err}"
        )
        exit_code = 2
    elif not diff_lines:
        result["diff_available"] = True
        result["source_change_impact"] = "INTERNAL_ONLY"
        result["proof"].append("git diff returned empty — no file changes in SHA range")
    else:
        result["diff_available"] = True
        files_classified = []
        categories: list[str] = []
        for line in diff_lines:
            parts = line.split("\t", 1)
            if len(parts) < 2:
                continue
            change_type, file_path = parts[0].strip(), parts[1].strip()
            category, reason = _classify_file(file_path)
            files_classified.append({
                "path": file_path,
                "change_type": change_type,
                "category": category,
                "reason": reason,
            })
            categories.append(category)

        result["files_classified"] = files_classified
        result["source_change_impact"] = _aggregate_impact(categories)

        user_facing = [f for f in files_classified if f["category"] in {"DEFINITELY_USER_FACING", "PROBABLY_USER_FACING"}]
        test_only = [f for f in files_classified if f["category"] == "TEST_ONLY"]
        internal_only = [f for f in files_classified if f["category"] in {"TEST_ONLY", "BUILD_ONLY", "DOC_ONLY_UPSTREAM"}]

        if user_facing:
            result["proof"].append(
                f"{len(user_facing)} user-facing source files changed: "
                f"{[f['path'] for f in user_facing[:3]]}"
            )
        if test_only:
            result["proof"].append(f"{len(test_only)} test-only files changed")
        if result["source_change_impact"] == "INTERNAL_ONLY":
            result["proof"].append(
                f"All {len(internal_only)} changed files are TEST_ONLY/BUILD_ONLY/DOC_ONLY_UPSTREAM"
            )

    delta = _load_knowledge_delta(knowledge_delta_path)
    if delta:
        nc = len(delta.get("new_claims", []))
        mc = len(delta.get("modified_claims", []))
        rc = len(delta.get("removed_claims", []))
        na = len(delta.get("new_apis", []))
        ma = len(delta.get("modified_apis", []))
        ra = len(delta.get("removed_apis", []))
        result["claim_delta_count"] = nc + mc + rc + na + ma + ra
        result["claim_delta_detail"] = {
            "new_claims": nc, "modified_claims": mc, "removed_claims": rc,
            "new_apis": na, "modified_apis": ma, "removed_apis": ra,
        }
        if result["claim_delta_count"] > 0:
            result["proof"].append(
                f"knowledge_delta: {mc} modified_claims, {rc} removed_claims, {ma} modified_apis"
            )

    _write_output(result, out_path)
    return result, exit_code


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Pre-update source semantic classifier for S-84 Step 4.5"
    )
    parser.add_argument("family", help="Product family (e.g. font, cells)")
    parser.add_argument("platform", help="Platform (e.g. python, java)")
    parser.add_argument("--old-sha", required=True, help="Old source SHA")
    parser.add_argument("--new-sha", required=True, help="New source SHA")
    parser.add_argument("--clone-cache", default=None, help="Override clone cache path")
    parser.add_argument("--knowledge-delta", default=None, help="Path to knowledge_delta.json")
    parser.add_argument("--out", default=None, help="Output path for semantic_source_delta.json")
    parser.add_argument("--repo-root", default=None, help="Override repository root")
    args = parser.parse_args(argv)

    repo_root = Path(args.repo_root) if args.repo_root else None
    kd_path: Path | None = None
    if args.knowledge_delta:
        kd_path = Path(args.knowledge_delta)
    else:
        r = repo_root or _REPO_ROOT
        default_kd = r / "knowledge" / args.family / args.platform / "merged" / "knowledge_delta.json"
        if default_kd.is_file():
            kd_path = default_kd

    out_path = Path(args.out) if args.out else None

    _, exit_code = classify(
        family=args.family,
        platform=args.platform,
        old_sha=args.old_sha,
        new_sha=args.new_sha,
        repo_root=repo_root,
        clone_cache_override=args.clone_cache,
        knowledge_delta_path=kd_path,
        out_path=out_path,
    )
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
