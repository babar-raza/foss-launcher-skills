"""Find all English modified files with FAIL audit findings."""
import subprocess, sys, pathlib, re

REPO = pathlib.Path(__file__).resolve().parent.parent.parent.parent

# Get English modified files
result = subprocess.run(
    ["git", "status", "--short", "--", "content/"],
    capture_output=True, text=True, cwd=REPO
)
en_files = []
for line in result.stdout.splitlines():
    if len(line) > 3 and line[1] == "M":
        fname = line[3:].strip().replace("\\", "/")
        if "/en/" in fname:
            en_files.append(fname)

print(f"Scanning {len(en_files)} English files for FAILs...", flush=True)

failing = set()
batch_size = 50
for i in range(0, len(en_files), batch_size):
    batch = en_files[i : i + batch_size]
    r = subprocess.run(
        [str(REPO / ".venv/Scripts/python"), "scripts/pipeline/commands/content/audit.py", "--files"] + batch,
        capture_output=True, text=True, cwd=REPO
    )
    if r.returncode != 0:
        # Parse failing files from output
        for line in r.stdout.splitlines():
            # Match lines like "### content\path\to\file.md" (FAIL section headers)
            m = re.match(r"^### (content.+\.md)", line)
            if m:
                fp = m.group(1).replace("\\", "/")
                failing.add(fp)
    if (i // batch_size + 1) % 5 == 0:
        print(f"  Processed {i+len(batch)}/{len(en_files)} files, {len(failing)} FAILs found so far", flush=True)

print(f"\nTotal files with FAILs: {len(failing)}")
for fp in sorted(failing):
    print(f'    "{fp}",')
