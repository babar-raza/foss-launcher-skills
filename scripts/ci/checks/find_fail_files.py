# Adapted from aspose.org scripts/ci/checks/ for standalone use
"""Find files with FAIL severity from audit-results.json."""
import json
import os
import sys
import pathlib


def main():
    repo_root = os.environ.get("REPO_ROOT", str(pathlib.Path(__file__).resolve().parent.parent.parent.parent))
    audit_file = sys.argv[1] if len(sys.argv) > 1 else "audit-results.json"

    with open(audit_file) as f:
        data = json.load(f)

    failing_files = set()
    for finding in data.get("findings", []):
        if finding.get("level") == "FAIL":
            fpath = finding.get("file", "")
            # Normalize to repo-relative forward-slash path
            fpath = fpath.replace("\\", "/")
            fpath = fpath.replace(repo_root.replace("\\", "/") + "/", "")
            if fpath:
                failing_files.add(fpath)

    print(f"FAIL files: {len(failing_files)}")
    for fp in sorted(failing_files):
        print(fp)


if __name__ == "__main__":
    main()
