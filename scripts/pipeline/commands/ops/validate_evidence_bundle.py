#!/usr/bin/env python3
"""Evidence bundle validator.

Validates a ZIP evidence bundle for structural completeness and consistency.

Checks performed:
  1. ZIP is readable
  2. Contains a manifest (*manifest*.json)
  3. Contains bundle-validation.json
  4. All files listed in manifest exist in ZIP
  5. HEAD SHA values are consistent across files
  6. No PROPOSED/IN_PROGRESS taskcards (if taskcard-state file exists)
  7. 00-final-verdict.md exists in ZIP

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
        if isinstance(data, dict):
            for card_id, state in data.items():
                s = state if isinstance(state, str) else str(state)
                if s.upper() in TASKCARD_BAD_STATES:
                    bad_entries.append(f"{card_id}={s}")
        elif isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    s = item.get("state", item.get("status", ""))
                    if str(s).upper() in TASKCARD_BAD_STATES:
                        bad_entries.append(str(item))

    if bad_entries:
        return {"check": "no_open_taskcards", "status": "FAIL",
                "detail": f"Open taskcards: {bad_entries}"}
    return {"check": "no_open_taskcards", "status": "PASS",
            "detail": "No PROPOSED/IN_PROGRESS taskcards"}


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
