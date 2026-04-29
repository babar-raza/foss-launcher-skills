"""Commit English provenance backfill in batches, skipping known-FAIL files."""
import subprocess, sys, pathlib

REPO = pathlib.Path(__file__).resolve().parent.parent.parent.parent

# Pre-existing FAIL files (all in baseline) — skip; addressed separately
SKIP_FILES = {
    "content/docs.aspose.org/en/3d/typescript/getting-started/license.md",
    "content/docs.aspose.org/en/email/cpp/developer-guide/features.md",
    "content/kb.aspose.org/en/3d/python/how-to-save-3d-scenes-python.md",
    "content/products.aspose.org/en/email/cpp/_index.md",
    "content/reference.aspose.org/en/3d/java/_index.md",
    "content/reference.aspose.org/en/3d/java/camera.md",
    "content/reference.aspose.org/en/3d/java/matrix4.md",
    "content/reference.aspose.org/en/3d/java/mesh.md",
    "content/reference.aspose.org/en/3d/java/property.md",
    "content/reference.aspose.org/en/3d/java/quaternion.md",
    "content/reference.aspose.org/en/3d/java/scene.md",
    "content/reference.aspose.org/en/3d/java/transform.md",
    "content/reference.aspose.org/en/3d/java/vector4.md",
    "content/reference.aspose.org/en/3d/net/AssetInfo.md",
    "content/reference.aspose.org/en/3d/net/BoundingBox.md",
    "content/reference.aspose.org/en/3d/net/FileFormat.md",
    "content/reference.aspose.org/en/3d/net/GlobalTransform.md",
    "content/reference.aspose.org/en/3d/net/_index.md",
    "content/reference.aspose.org/en/3d/net/camera.md",
    "content/reference.aspose.org/en/3d/net/entity.md",
    "content/reference.aspose.org/en/3d/net/light.md",
    "content/reference.aspose.org/en/3d/net/matrix4.md",
    "content/reference.aspose.org/en/3d/net/mesh.md",
    "content/reference.aspose.org/en/3d/net/node.md",
    "content/reference.aspose.org/en/3d/net/property.md",
    "content/reference.aspose.org/en/3d/net/quaternion.md",
    "content/reference.aspose.org/en/3d/net/scene.md",
    "content/reference.aspose.org/en/3d/net/transform.md",
    "content/reference.aspose.org/en/3d/net/vector2.md",
    "content/reference.aspose.org/en/3d/net/vector3.md",
    "content/reference.aspose.org/en/3d/net/vector4.md",
    "content/reference.aspose.org/en/3d/typescript/VertexElement.md",
    "content/reference.aspose.org/en/3d/typescript/_index.md",
    "content/reference.aspose.org/en/3d/typescript/camera.md",
    "content/reference.aspose.org/en/3d/typescript/light.md",
    "content/reference.aspose.org/en/3d/typescript/mesh.md",
    "content/reference.aspose.org/en/3d/typescript/quaternion.md",
    "content/reference.aspose.org/en/email/python/CFBDocument.md",
    "content/reference.aspose.org/en/email/python/CFBStorage.md",
    "content/reference.aspose.org/en/email/python/CFBStream.md",
    "content/reference.aspose.org/en/email/python/MsgDocument.md",
    "content/reference.aspose.org/en/email/python/MsgStorage.md",
    "content/reference.aspose.org/en/email/python/MsgStream.md",
    "content/reference.aspose.org/en/slides/python/FillFormat.md",
    "content/reference.aspose.org/en/slides/python/FontData.md",
}

def get_en_files():
    result = subprocess.run(
        ["git", "status", "--short", "--", "content/"],
        capture_output=True, text=True, cwd=REPO
    )
    files = []
    for line in result.stdout.splitlines():
        if len(line) > 3 and line[1] == "M":
            fname = line[3:].strip().replace("\\", "/")
            if "/en/" in fname and fname not in SKIP_FILES:
                files.append(fname)
    return files

def verify_nothing_staged():
    r = subprocess.run(
        ["git", "diff", "--cached", "--name-only"],
        capture_output=True, text=True, cwd=REPO
    )
    staged = [l for l in r.stdout.splitlines() if l.strip()]
    if staged:
        print(f"ERROR: {len(staged)} files already staged before batch start!")
        for f in staged[:5]:
            print(f"  {f}")
        return False
    return True

en_files = get_en_files()
print(f"English files to commit: {len(en_files)} (skipping {len(SKIP_FILES)} with FAILs)")

BATCH_SIZE = 60
total_batches = (len(en_files) + BATCH_SIZE - 1) // BATCH_SIZE

for i in range(0, len(en_files), BATCH_SIZE):
    batch = en_files[i : i + BATCH_SIZE]
    batch_num = i // BATCH_SIZE + 1

    # Safety: ensure nothing is staged before this batch
    if not verify_nothing_staged():
        print(f"Unstaging before batch {batch_num}...")
        subprocess.run(["git", "reset", "HEAD", "--", "."], capture_output=True, cwd=REPO)

    # Stage exactly this batch
    r = subprocess.run(["git", "add", "--"] + batch, capture_output=True, text=True, cwd=REPO)
    if r.returncode != 0:
        print(f"Stage error batch {batch_num}: {r.stderr}")
        sys.exit(1)

    # Verify staged count matches batch
    r_check = subprocess.run(
        ["git", "diff", "--cached", "--name-only"],
        capture_output=True, text=True, cwd=REPO
    )
    staged_count = len([l for l in r_check.stdout.splitlines() if l.strip()])
    if staged_count != len(batch):
        print(f"WARNING: staged {staged_count} files but batch has {len(batch)}")

    msg = (
        f"chore(provenance): backfill English provenance batch {batch_num}/{total_batches} (AC-05)\n\n"
        f"Adds provenance blocks to {len(batch)} English content files.\n\n"
        "Skills invoked: S-52, S-53\n\n"
        "Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
    )
    r2 = subprocess.run(["git", "commit", "-m", msg], capture_output=True, text=True, cwd=REPO)
    if r2.returncode != 0:
        print(f"Commit error batch {batch_num}:")
        # Show last 800 chars of stdout for context
        out = r2.stdout.strip()
        print(out[-800:] if len(out) > 800 else out)
        # Unstage and abort
        subprocess.run(["git", "reset", "HEAD", "--", "."], capture_output=True, cwd=REPO)
        # Try to identify which file in the batch caused the failure
        print(f"\nDebug: Finding failing file in batch {batch_num}...")
        for f in batch:
            r3 = subprocess.run(
                [str(REPO / ".venv/Scripts/python"), "scripts/pipeline/commands/content/audit.py", "--files", f],
                capture_output=True, text=True, cwd=REPO
            )
            if r3.returncode != 0:
                print(f"  FAIL: {f}")
        sys.exit(1)

    lines = r2.stdout.strip().splitlines()
    print(f"  Batch {batch_num}/{total_batches} ({len(batch)} files): {lines[-1] if lines else 'OK'}")

print("All English provenance batches committed.")
