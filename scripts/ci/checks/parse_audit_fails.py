#!/usr/bin/env python3
"""Parse audit JSON and print FAIL findings. Used for B-01 classification."""
import json
import sys

path = sys.argv[1] if len(sys.argv) > 1 else "/tmp/audit_out.json"
with open(path) as fh:
    content = fh.read()

idx = content.find("{")
j = json.loads(content[idx:])
fails = [f for f in j["findings"] if f["level"] == "FAIL"]
print(f"Total FAILs: {len(fails)}")
print()
for f in fails:
    p = f["file"].replace("\\", "/").split("aspose.org/")[-1]
    print(f"{p}:{f['line']} | {f['message'][:120]}")
