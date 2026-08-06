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
a fixed convention and compresses it under 1MB, preferring true-lossless
compression and falling back to visually-reviewed high-quality WebP only when
lossless can't reach the target — verified per file, not assumed.

**Naming convention** (directory already encodes family/platform, so filenames
don't repeat it). Either `.png` or `.webp` may occupy a slot, depending on
which compression path succeeded:
- Family-level icon (no platform subfolder): `static/media/{family}/icon.{png,webp}`
- Platform icon (square: 1024×1024 or 1254×1254): `static/media/{family}/{platform}/icon.{png,webp}`
- Platform banner (landscape ~2:1: 1774×887): `static/media/{family}/{platform}/banner.{png,webp}`

Classification is by pixel dimensions, not filename — square = icon, ~2:1
landscape = banner. This has been confirmed reliable across every file in the
tree (only two square sizes and one wide size occur, with zero overlap).

**Why lossless alone isn't always enough** (calibrated empirically, not
assumed): `oxipng -o max --strip safe` on these AI-generated, detail-rich
images typically only saves 9–13%, nowhere near enough from ~1.3–1.7MB
originals. A Zopfli second pass (`-o max -z`) was tried and dropped — it added
0–0.7% for 60–140 seconds per file, not worth the cost. When lossless can't
close the gap, the skill falls back to WebP (Pillow's bundled libwebp 1.6.0,
which matches the current upstream `webmproject/libwebp` release exactly —
not a stale wrapper) at quality 95, stepping down through 90/85/80 only if
needed, never lower.

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
   For each in-scope file:
   - **Attempt 1 (lossless)**: copy to a temp file, run
     `oxipng -o max --strip safe`, verify the decoded pixel buffer is
     byte-identical to the source and dimensions are unchanged, verify size
     `< 1,048,576` bytes. If it fits: finalize as `icon.png`/`banner.png`,
     remove the old file. Status `OK`.
   - **Attempt 2 (WebP fallback, only if attempt 1 didn't fit)**: re-encode
     the *original* as WebP at quality 95 (method 6), stepping down through
     90/85/80 only as needed. Run the automated PSNR/SSIM floor (≥18dB /
     ≥0.90 — a coarse gate for gross encoder failures only, see Hard
     Constraints). If a quality level passes both the size and floor checks:
     stage it as `icon.webp`/`banner.webp` **without deleting the original**.
     Status `NEEDS_VISUAL_REVIEW`.
   - Neither attempt fits: leave the original untouched. Status
     `STILL_OVER_BUDGET`.

4. **Verify — two different bars for two different outcomes**:
   - `OK` (lossless PNG): the script's own pixel-buffer assertion is
     sufficient proof — do not re-derive it from file size alone.
   - `NEEDS_VISUAL_REVIEW` (WebP): the automated PSNR/SSIM floor is
     **not** sufficient proof by itself — it was found, empirically, to
     correlate poorly with perceived quality on this sharp-edged
     graphic-design content (a demonstrably fine result measured
     21.6dB/0.948, well below common "visually lossless" numeric guidance).
     Render the before/after pair for every `NEEDS_VISUAL_REVIEW` file and
     look at them side by side before accepting. Only after this passes,
     run:
     ```bash
     .venv/Scripts/python scripts/pipeline/commands/ops/optimize_media_assets.py --confirm-reviewed <reported source path> [<path> ...]
     ```
     which deletes the original now that its WebP replacement is confirmed.
     Do not run `--confirm-reviewed` on a file you have not actually looked
     at.

5. **Report** any file the script lists as `STILL_OVER_BUDGET` (over 1MB
   after both the lossless pass and the full WebP quality ladder) or
   `BLOCKED` (target name collision with differing content, checked across
   both `.png` and `.webp`) to the operator. Do not resize or push WebP
   quality below 80 to resolve these without an explicit operator decision.

6. **Commit** via `/commit` (S-76). No override token is needed for the
   `static/media/` changes themselves — `path_guard.py`'s `ALLOWED_PREFIXES`
   permanently allows this path (added alongside this skill's own creation).

> **Skill context close** — run after the last step:
> ```bash
> PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/commands/governance/skill_context.py end --skill S-119 --status completed
> ```

## Hard Constraints

- **Prefer lossless PNG; WebP is a fallback, not a default.** Only attempt
  WebP after a real lossless PNG pass (`oxipng -o max --strip safe`) fails to
  reach budget. Do not enable oxipng's `-a/--alpha` (its own docs call it
  "technically a lossy transformation") on the PNG path.
- **WebP quality floor is 80, never lower, and never automatic-only.** Step
  down the ladder `95 → 90 → 85 → 80` only as needed. If quality 80 still
  doesn't fit budget, stop and report `STILL_OVER_BUDGET` — do not go lower,
  do not resize, do not switch to another lossy format, without a fresh
  operator decision.
- **A WebP result is never self-certified.** The automated PSNR/SSIM floor
  (≥18dB / ≥0.90) exists only to catch gross encoder failures, not to
  approve quality — it has been shown to read as "mediocre" on a result that
  is visually perfect. Every `NEEDS_VISUAL_REVIEW` file requires an actual
  visual comparison before `--confirm-reviewed` deletes the original.
- **Never silently overwrite** an existing `icon.*`/`banner.*` (either
  extension) that has different content than the file being renamed into
  that slot. Report it as `BLOCKED` and leave both files untouched.
- **Never invent a missing icon or banner.** If a platform only has one of the
  two, rename what exists; do not synthesize or duplicate the other.
- **Resolution must stay identical in both paths.** Pixel dimensions never
  change. For the PNG path, pixel values must match the source exactly
  (checked automatically). For the WebP path, dimensions are unchanged and
  pixel *values* change by design (it's lossy) — the visual-review step is
  what stands in for "no perceptible loss" here, not a pixel-exact check.

## Post-conditions

- Every file processed in scope is `< 1,048,576` bytes
- Filenames match the convention (`icon.png`/`icon.webp` or
  `banner.png`/`banner.webp` per directory — exactly one per slot)
- Every `NEEDS_VISUAL_REVIEW` file has either been confirmed via
  `--confirm-reviewed` (original deleted) or is still explicitly pending
  review (original still present) — never silently left ambiguous
- `git status` shows changes only under `static/media/` for this run
- Any file that couldn't be brought under budget by either path is reported,
  not silently left in a half-renamed state

## Error handling

- Source file dimensions don't match either the square-icon or ~2:1-banner
  shape: report as `UNCLASSIFIED`, skip it, continue with the rest of the
  batch
- Target name collision with differing content (checked across both `.png`
  and `.webp`): report as `BLOCKED`, skip it, continue with the rest of the
  batch
- File still `>= 1MB` after the lossless pass and the full WebP quality
  ladder (95/90/85/80): report as `STILL_OVER_BUDGET`, leave it under its
  original name/location, continue with the rest of the batch
- `oxipng` unreachable (not on PATH and download fails): halt the whole run
  with a clear error — do not partially process files without attempting the
  lossless step first
- `--confirm-reviewed` called on a path with no corresponding `.webp` target:
  report `NO_TARGET_FOUND`, do not delete anything
