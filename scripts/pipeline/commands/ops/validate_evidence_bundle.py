#!/usr/bin/env python3
"""Evidence bundle validator.

Validates a ZIP evidence bundle for structural completeness and consistency.

Checks performed:
  1. ZIP is readable
  2. Contains a manifest (*manifest*.json)
  3. Contains bundle-validation.json
  4. All files listed in manifest exist in ZIP
  5. HEAD SHA values are consistent across files
  6. No PROPOSED/IN_PROGRESS taskcards (handles flat, nested, and list formats)
  7. 00-final-verdict.md exists in ZIP
  8. bundle-validation.json recorded ZIP size/SHA matches actual ZIP (sidecar pattern allowed)
  9. evidence-checksums.sha256 file exists (WARN if absent, not FAIL)
 10. All taskcards have terminal statuses (not CLOSED_SCAFFOLDED, CLOSED_CLASSIFIED, etc.)

Usage:
    python validate_evidence_bundle.py <path-to-bundle.zip>

Outputs JSON report to stdout.
Exit 0 if all checks PASS, exit 1 if any FAIL.
"""

import argparse
import hashlib
import json
import os
import re
import sys
import zipfile

SHA_PATTERN = re.compile(r"\b[0-9a-f]{40}\b")
TASKCARD_BAD_STATES = {"PROPOSED", "IN_PROGRESS"}
TASKCARD_TERMINAL_STATUSES = {
    "CLOSED_VERIFIED", "CLOSED_IMPLEMENTED_VERIFIED", "CLOSED_SKIPPED_WITH_REASON",
    "BLOCKED_EXTERNAL_GATE", "BLOCKED_GOVERNANCE", "COMPLETE",
}
# Top-level metadata keys in nested taskcard-state files; not card IDs.
_TASKCARD_META_KEYS = frozenset(
    {"sprint", "head", "generated_at", "note", "note_zip_stats",
     "open_taskcards", "proposed_or_in_progress", "taskcards"}
)


def check_zip_readable(path: str) -> dict:
    """Check 1: ZIP file is readable."""
    try:
        with zipfile.ZipFile(path, "r") as zf:
            bad = zf.testzip()
            if bad is not None:
                return {"check": "zip_readable", "status": "FAIL",
                        "detail": f"Corrupt entry: {bad}"}
        return {"check": "zip_readable", "status": "PASS", "detail": "ZIP is valid"}
    except (zipfile.BadZipFile, FileNotFoundError, OSError) as exc:
        return {"check": "zip_readable", "status": "FAIL", "detail": str(exc)}


def check_manifest_exists(zf: zipfile.ZipFile) -> dict:
    """Check 2: At least one *manifest*.json exists."""
    matches = [n for n in zf.namelist()
                if "manifest" in n.lower() and n.endswith(".json")]
    if matches:
        return {"check": "manifest_exists", "status": "PASS",
                "detail": f"Found: {matches}"}
    return {"check": "manifest_exists", "status": "FAIL",
            "detail": "No *manifest*.json found in ZIP"}


def check_bundle_validation_exists(zf: zipfile.ZipFile) -> dict:
    """Check 3: bundle-validation.json exists."""
    matches = [n for n in zf.namelist() if n.endswith("bundle-validation.json")]
    if matches:
        return {"check": "bundle_validation_exists", "status": "PASS",
                "detail": f"Found: {matches}"}
    return {"check": "bundle_validation_exists", "status": "FAIL",
            "detail": "No bundle-validation.json found"}


def check_manifest_files_present(zf: zipfile.ZipFile) -> dict:
    """Check 4: All files listed in manifest exist in ZIP."""
    manifest_files = [n for n in zf.namelist()
                      if "manifest" in n.lower() and n.endswith(".json")]
    if not manifest_files:
        return {"check": "manifest_files_present", "status": "FAIL",
                "detail": "No manifest to check"}

    zip_entries = set(zf.namelist())
    missing = []
    for mf in manifest_files:
        try:
            data = json.loads(zf.read(mf))
        except (json.JSONDecodeError, KeyError):
            continue

        # Collect all file paths from manifest (handles nested structures)
        listed = _extract_file_paths(data)
        for fp in listed:
            if fp not in zip_entries:
                missing.append(fp)

    if missing:
        return {"check": "manifest_files_present", "status": "FAIL",
                "detail": f"Missing from ZIP: {missing}"}
    return {"check": "manifest_files_present", "status": "PASS",
            "detail": "All manifest files present in ZIP"}


def _extract_file_paths(data, paths=None):
    """Recursively extract file path strings from manifest data."""
    if paths is None:
        paths = []
    if isinstance(data, str):
        # Looks like a relative path inside the ZIP
        if "/" in data and not data.startswith("http"):
            paths.append(data)
    elif isinstance(data, list):
        for item in data:
            _extract_file_paths(item, paths)
    elif isinstance(data, dict):
        for v in data.values():
            _extract_file_paths(v, paths)
    return paths


def check_head_consistency(zf: zipfile.ZipFile) -> dict:
    """Check 5: HEAD SHA values are consistent across all files."""
    sha_sources = {}  # sha -> list of filenames
    for name in zf.namelist():
        try:
            content = zf.read(name).decode("utf-8", errors="replace")
        except Exception:
            continue
        # Look for head/HEAD fields in JSON or SHA references in text
        found_shas = set()
        if name.endswith(".json"):
            try:
                d = json.loads(content)
                if isinstance(d, dict) and "head" in d:
                    val = d["head"]
                    if isinstance(val, str) and SHA_PATTERN.fullmatch(val):
                        found_shas.add(val)
            except json.JSONDecodeError:
                pass
        # Also grep for "HEAD:" or "head:" patterns in md files
        for line in content.splitlines():
            low = line.lower()
            if "head" in low or "commit" in low:
                for m in SHA_PATTERN.finditer(line):
                    found_shas.add(m.group())
        for sha in found_shas:
            sha_sources.setdefault(sha, []).append(name)

    if len(sha_sources) == 0:
        return {"check": "head_consistency", "status": "PASS",
                "detail": "No HEAD SHA values found (nothing to compare)"}
    if len(sha_sources) == 1:
        sha = list(sha_sources.keys())[0]
        return {"check": "head_consistency", "status": "PASS",
                "detail": f"Consistent HEAD: {sha}"}

    return {"check": "head_consistency", "status": "FAIL",
            "detail": f"Multiple HEAD SHAs found: {dict(sha_sources)}"}


def _iter_taskcard_statuses(data):
    """Yield (card_id, status_str) from any taskcard-state format."""
    if isinstance(data, dict):
        if "taskcards" in data and isinstance(data["taskcards"], list):
            # Nested format: {"taskcards": [{"id": "T-1", "status": "..."}, ...]}
            for item in data["taskcards"]:
                if isinstance(item, dict):
                    yield (item.get("id", "?"), item.get("status", item.get("state", "")))
        else:
            # Flat format: {"card_id": "STATUS", ...}
            for card_id, state in data.items():
                if card_id not in _TASKCARD_META_KEYS:
                    yield (card_id, state if isinstance(state, str) else str(state))
    elif isinstance(data, list):
        # Bare list format: [{"id": "T-1", "status": "..."}, ...]
        for item in data:
            if isinstance(item, dict):
                yield (item.get("id", "?"), item.get("status", item.get("state", "")))


def check_no_open_taskcards(zf: zipfile.ZipFile) -> dict:
    """Check 6: No PROPOSED/IN_PROGRESS taskcards if taskcard-state exists."""
    state_files = [n for n in zf.namelist() if "taskcard-state" in n.lower()]
    if not state_files:
        return {"check": "no_open_taskcards", "status": "FAIL",
                "detail": "No taskcard-state file found in bundle"}

    bad_entries = []
    for sf in state_files:
        try:
            data = json.loads(zf.read(sf))
        except (json.JSONDecodeError, Exception):
            continue
        for card_id, s in _iter_taskcard_statuses(data):
            if str(s).upper() in TASKCARD_BAD_STATES:
                bad_entries.append(f"{card_id}={s}")

    if bad_entries:
        return {"check": "no_open_taskcards", "status": "FAIL",
                "detail": f"Open taskcards: {bad_entries}"}
    return {"check": "no_open_taskcards", "status": "PASS",
            "detail": "No PROPOSED/IN_PROGRESS taskcards"}


def check_zip_stats_consistent(path: str, zf: zipfile.ZipFile) -> dict:
    """Check 8: bundle-validation.json recorded ZIP stats match actual ZIP."""
    bv_files = [n for n in zf.namelist() if n.endswith("bundle-validation.json")]
    if not bv_files:
        return {"check": "zip_stats_consistent", "status": "FAIL",
                "detail": "No bundle-validation.json found to read ZIP stats from"}
    try:
        data = json.loads(zf.read(bv_files[0]))
    except json.JSONDecodeError:
        return {"check": "zip_stats_consistent", "status": "FAIL",
                "detail": "bundle-validation.json is not valid JSON"}
    recorded_size = data.get("final_zip_size_bytes")
    recorded_sha = data.get("final_zip_sha256")
    # Sidecar pattern: null/absent fields mean external sidecar holds stats — allowed.
    if recorded_size is None or recorded_sha is None:
        return {"check": "zip_stats_consistent", "status": "PASS",
                "detail": "ZIP stats absent in bundle-validation.json (sidecar pattern) "
                          "— external verification required"}
    actual_size = os.path.getsize(path)
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    actual_sha = h.hexdigest()
    if actual_size != recorded_size or actual_sha != recorded_sha:
        return {"check": "zip_stats_consistent", "status": "FAIL",
                "detail": (f"Size mismatch: recorded={recorded_size} actual={actual_size}; "
                           f"SHA256 mismatch: recorded={recorded_sha} actual={actual_sha}")}
    return {"check": "zip_stats_consistent", "status": "PASS",
            "detail": f"ZIP stats consistent: {actual_size}B / {actual_sha[:16]}..."}


def check_checksums_file_exists(zf: zipfile.ZipFile) -> dict:
    """Check 9: evidence-checksums.sha256 file exists in bundle."""
    matches = [n for n in zf.namelist()
               if "checksums" in n.lower() and n.endswith(".sha256")]
    if matches:
        return {"check": "checksums_file_exists", "status": "PASS",
                "detail": f"Found: {matches}"}
    return {"check": "checksums_file_exists", "status": "WARN",
            "detail": "No *checksums*.sha256 found (older bundles may predate this convention)"}


def check_taskcard_terminal_status(zf: zipfile.ZipFile) -> dict:
    """Check 10: All taskcards have terminal statuses (not CLOSED_SCAFFOLDED etc.)."""
    state_files = [n for n in zf.namelist() if "taskcard-state" in n.lower()]
    if not state_files:
        return {"check": "taskcard_terminal_status", "status": "FAIL",
                "detail": "No taskcard-state file found"}
    non_terminal = []
    for sf in state_files:
        try:
            data = json.loads(zf.read(sf))
        except Exception:
            continue
        for card_id, s in _iter_taskcard_statuses(data):
            if s and str(s).upper() not in TASKCARD_TERMINAL_STATUSES:
                non_terminal.append(f"{card_id}={s}")
    if non_terminal:
        return {"check": "taskcard_terminal_status", "status": "FAIL",
                "detail": f"Non-terminal taskcards: {non_terminal}"}
    return {"check": "taskcard_terminal_status", "status": "PASS",
            "detail": "All taskcards have terminal statuses"}


def check_final_verdict_exists(zf: zipfile.ZipFile) -> dict:
    """Check 7: 00-final-verdict.md exists."""
    matches = [n for n in zf.namelist() if n.endswith("00-final-verdict.md")]
    if matches:
        return {"check": "final_verdict_exists", "status": "PASS",
                "detail": f"Found: {matches}"}
    return {"check": "final_verdict_exists", "status": "FAIL",
            "detail": "00-final-verdict.md not found in bundle"}


def compute_zip_metadata(path: str) -> dict:
    """Compute size and SHA256 of the ZIP file."""
    size = os.path.getsize(path)
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return {"size_bytes": size, "sha256": h.hexdigest()}


def validate(path: str) -> dict:
    """Run all checks and return report."""
    results = []

    # Check 1: ZIP readable
    r1 = check_zip_readable(path)
    results.append(r1)
    if r1["status"] == "FAIL":
        # Can't proceed if ZIP is unreadable
        report = {
            "bundle_path": path,
            "checks": results,
            "overall": "FAIL",
            "pass_count": 0,
            "fail_count": 1,
            "total_checks": 1,
        }
        return report

    with zipfile.ZipFile(path, "r") as zf:
        results.append(check_manifest_exists(zf))
        results.append(check_bundle_validation_exists(zf))
        results.append(check_manifest_files_present(zf))
        results.append(check_head_consistency(zf))
        results.append(check_no_open_taskcards(zf))
        results.append(check_final_verdict_exists(zf))
        results.append(check_zip_stats_consistent(path, zf))
        results.append(check_checksums_file_exists(zf))
        results.append(check_taskcard_terminal_status(zf))

    # Metadata
    meta = compute_zip_metadata(path)
    pass_count = sum(1 for r in results if r["status"] == "PASS")
    fail_count = sum(1 for r in results if r["status"] == "FAIL")

    report = {
        "bundle_path": path,
        "zip_size_bytes": meta["size_bytes"],
        "zip_sha256": meta["sha256"],
        "checks": results,
        "overall": "PASS" if fail_count == 0 else "FAIL",
        "pass_count": pass_count,
        "fail_count": fail_count,
        "total_checks": len(results),
    }
    return report


def main():
    parser = argparse.ArgumentParser(
        description="Validate an evidence bundle ZIP file."
    )
    parser.add_argument("zip_path", help="Path to the evidence bundle ZIP file")
    args = parser.parse_args()

    if not os.path.isfile(args.zip_path):
        report = {
            "bundle_path": args.zip_path,
            "checks": [{"check": "file_exists", "status": "FAIL",
                         "detail": f"File not found: {args.zip_path}"}],
            "overall": "FAIL",
            "pass_count": 0,
            "fail_count": 1,
            "total_checks": 1,
        }
        print(json.dumps(report, indent=2))
        sys.exit(1)

    report = validate(args.zip_path)
    print(json.dumps(report, indent=2))
    sys.exit(0 if report["overall"] == "PASS" else 1)


if __name__ == "__main__":
    main()
