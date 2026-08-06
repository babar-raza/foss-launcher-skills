---
name: media-optimize
id: S-119
description: >
  Product icons and banner (social-preview) images dropped under
---

> Cross-skill references like `/knowledge-bootstrap` refer to sibling skills in this directory.

# S-119: Media Optimize — Rename and Compress Product Image Assets

**Arguments**: $ARGUMENTS
Expected format:
- (no arguments) — process every file under `static/media/`
- `{family}` — scope to one family (e.g. `pdf`)
- `{family} {platform}` — scope to one family/platform (e.g. `pdf python`)

## Purpose

Product icons and banner (social-preview) images dropped under
`static/media/{family}/{platform}/*.png` arrive with arbitrary filenames and
are frequently over GitHub's 1MB upload limit. This skill renames each file to
a fixed convention and losslessly compresses it under 1MB, with zero visual
loss and unchanged pixel resolution — verified per file, not assumed.

**Naming convention** (directory already encodes family/platform, so filenames
don't repeat it):
- Family-level icon (no platform subfolder): `static/media/{family}/icon.png`
- Platform icon (square: 1024×1024 or 1254×1254): `static/media/{family}/{platform}/icon.png`
- Platform banner (landscape ~2:1: 1774×887): `static/media/{family}/{platform}/banner.png`

Classification is by pixel dimensions, not filename — square = icon, ~2:1
landscape = banner. This has been confirmed reliable across every file in the
tree (only two square sizes and one wide size occur, with zero overlap).

## Pre-conditions

1. `static/media/` exists and contains at least one `.png` file in scope
2. `.venv` is present (`scripts/pipeline/commands/ops/optimize_media_assets.py`
   requires Pillow)
3. `oxipng` is on PATH, or the script can reach GitHub to download the official
   release binary into its local cache (`cache/oxipng/`)

## Steps

> **Skill context gate** — run before step 1:
> ```bash
> PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/commands/governance/skill_context.py begin --skill S-119 --scope "*"
> ```

1. **Dry-run first** — always review the classification and rename/compress
   plan before touching any file:
   ```bash
   .venv/Scripts/python scripts/pipeline/commands/ops/optimize_media_assets.py [family] [platform] --dry-run
   ```
   This prints, per file: current path, classified shape (icon/banner), target
   path, current size, and whether a same-name target already exists with
   different content (which blocks that file — see Hard Constraints).

2. **Review the plan** with the operator. Confirm:
   - No unexpected classification (a file that isn't cleanly square or ~2:1
     landscape is reported as `UNCLASSIFIED` and skipped, never guessed)
   - No blocked overwrite is silently ignored

3. **Apply**:
   ```bash
   .venv/Scripts/python scripts/pipeline/commands/ops/optimize_media_assets.py [family] [platform] --apply
   ```
   For each in-scope file: copy to the target name, run
   `oxipng -o max --strip safe` (pass 1), verify decoded pixel buffer is
   byte-identical to the source and dimensions are unchanged, verify size
   `< 1,048,576` bytes. If still over budget, retry with
   `oxipng -o max -z --strip safe` (pass 2 — Zopfli backend). The old
   UUID-named file is removed only after its replacement verifies clean.

4. **Verify**: every file the script reports as `OK` must be `< 1MB` and
   pixel-identical to its source (the script asserts this itself — do not
   re-derive it from file size alone).

5. **Report** any file the script lists as `STILL_OVER_BUDGET` (over 1MB after
   both oxipng passes) or `BLOCKED` (target name collision with differing
   content) to the operator. Do not resize, convert format, or apply lossy
   compression to resolve these without an explicit operator decision.

6. **Commit** via `/commit` (S-76). No override token is needed for the
   `static/media/` changes themselves — `path_guard.py`'s `ALLOWED_PREFIXES`
   permanently allows this path (added alongside this skill's own creation).

> **Skill context close** — run after the last step:
> ```bash
> PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/commands/governance/skill_context.py end --skill S-119 --status completed
> ```

## Hard Constraints

- **Never apply lossy compression.** Both oxipng passes are lossless by
  construction (DEFLATE/filter re-encoding only). Do not enable `-a/--alpha`
  (oxipng's own docs call it "technically a lossy transformation") and do not
  fall back to palette quantization, resizing, or format conversion (e.g.
  WebP/JPEG) to hit the size target — if lossless compression alone can't get a
  file under 1MB, stop and report it.
- **Never silently overwrite** an existing `icon.png`/`banner.png` that has
  different content than the file being renamed into that slot. Report it as
  `BLOCKED` and leave both files untouched.
- **Never invent a missing icon or banner.** If a platform only has one of the
  two, rename what exists; do not synthesize or duplicate the other.
- **Resolution must stay identical.** Pixel dimensions (and pixel values) must
  match the source exactly — this is checked automatically per file, not
  eyeballed.

## Post-conditions

- Every file processed in scope is `< 1,048,576` bytes
- Filenames match the convention (`icon.png` / `banner.png` per directory)
- `git status` shows changes only under `static/media/` for this run
- Any file that couldn't be brought under budget losslessly is reported, not
  silently left in a half-renamed state

## Error handling

- Source file dimensions don't match either the square-icon or ~2:1-banner
  shape: report as `UNCLASSIFIED`, skip it, continue with the rest of the
  batch
- Target name collision with differing content: report as `BLOCKED`, skip it,
  continue with the rest of the batch
- File still `>= 1MB` after both oxipng passes: report as `STILL_OVER_BUDGET`,
  leave it under its original name/location, continue with the rest of the
  batch
- `oxipng` unreachable (not on PATH and download fails): halt the whole run
  with a clear error — do not partially process files without the compression
  step
