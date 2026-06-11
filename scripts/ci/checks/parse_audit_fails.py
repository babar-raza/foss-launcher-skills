# Adapted from aspose.org scripts/ci/checks/ for standalone use
#\!/usr/bin/env python3
"""Parse audit JSON and print FAIL findings. Used for B-01 classification."""
import json
import sys


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "/tmp/audit_out.json"  # nosec B108 - CLI default path, not a temp file race
    with open(path) as fh:
        content = fh.read()

    idx = content.find("{")
    j = json.loads(content[idx:])
    fails = [f for f in j["findings"] if f["level"] == "FAIL"]
    print(f"Total FAILs: {len(fails)}")
    print()
    for f in fails:
        p = f["file"].replace("\\", "/").rsplit("/", 1)[-1] if "/" in f["file"] else f["file"]
        # Try to get a relative path
        fpath = f["file"].replace("\\", "/")
        print(f"{fpath}:{f['line']} | {f['message'][:120]}")


if __name__ == "__main__":
    main()
