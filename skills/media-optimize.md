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
a fixed convention and compresses it under 1MB with WebP — verified per file
via a mandatory visual review, not assumed.

**Naming convention** (directory already encodes family/platform, so filenames
don't repeat it). WebP is the only target format (operator decision,
2026-08-06 — see rationale below):
- Family-level icon (no platform subfolder): `static/media/{family}/icon.webp`
- Platform icon (square: 1024×1024 or 1254×1254): `static/media/{family}/{platform}/icon.webp`
- Platform banner (landscape ~2:1: 1774×887): `static/media/{family}/{platform}/banner.webp`

Classification is by pixel dimensions, not filename — square = icon, ~2:1
landscape = banner. This has been confirmed reliable across every file in the
tree (only two square sizes and one wide size occur, with zero overlap).

**Why WebP, not PNG** (calibrated empirically, not assumed): lossless PNG
recompression (`oxipng -o max --strip safe`, plus a Zopfli second pass) was
tried first. It only saved 9–13% on these AI-generated, detail-rich images —
nowhere near enough from ~1.3–1.7MB originals to reach 1MB — and Zopfli added
just 0–0.7% more for 60–140 seconds per file. WebP (Pillow's bundled libwebp
1.6.0, which matches the current upstream `webmproject/libwebp` release
exactly — not a stale wrapper, chosen the same way `oxipng` was, by comparing
GitHub star count and maintenance activity) reliably lands both calibration
samples at 150–230KB, ~80% under budget. Given that headroom and that PNG
essentially never wins on this content, WebP is the only path — no lossless
PNG attempt is made at all.

**Alpha transparency is preserved.** Verified by round-tripping a real icon
through Pillow's WebP encoder: `has_transparency_data=True`, alpha extrema
and a fully-transparent corner pixel matched exactly before/after. No special
flag is needed — Pillow's default WebP save already keeps the alpha channel
for RGBA input.

## Pre-conditions

1. `static/media/` exists and contains at least one `.png`/`.webp` file in
   scope
2. `.venv` is present (`scripts/pipeline/commands/ops/optimize_media_assets.py`
   requires Pillow)

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
   `.webp` path, current size, and whether that target already exists (in
   which case this source is redundant — reported `PENDING_REVIEW`, see Hard
   Constraints — rather than reprocessed).

2. **Review the plan** with the operator. Confirm:
   - No unexpected classification (a file that isn't cleanly square or ~2:1
     landscape is reported as `UNCLASSIFIED` and skipped, never guessed)
   - No `PENDING_REVIEW` file is silently ignored

3. **Apply**:
   ```bash
   .venv/Scripts/python scripts/pipeline/commands/ops/optimize_media_assets.py [family] [platform] --apply
   ```
   For each in-scope file: re-encode the original as WebP at quality 95
   (method 6), stepping down through 90/85/80 only as needed, never lower.
   **Size is the only automated acceptance criterion.** PSNR/SSIM are
   computed and reported alongside the result for context, but do not gate
   acceptance (see Hard Constraints for why). The first quality level that
   fits under budget is staged as `icon.webp`/`banner.webp` **without
   deleting the original**. Status `NEEDS_VISUAL_REVIEW`. If no quality
   level in the ladder fits budget: leave the original untouched, status
   `STILL_OVER_BUDGET`.

4. **Verify — visual review is the only real gate.** An automated PSNR/SSIM
   floor was tried and abandoned: it was found, empirically and **twice**,
   to swing across too wide and unpredictable a range on this sharp-edged,
   mostly-flat-color content to serve as a rejection threshold — two
   independently confirmed visually-perfect results measured 21.6dB/0.948
   and 14.8dB/0.770. A floor set to pass the first would have rejected the
   second, and vice versa; there is no safe numeric cutoff for this content
   type. Render the before/after pair for every `NEEDS_VISUAL_REVIEW` file
   and look at them side by side before accepting. Only after this passes,
   run:
   ```bash
   .venv/Scripts/python scripts/pipeline/commands/ops/optimize_media_assets.py --confirm-reviewed <reported source path> [<path> ...]
   ```
   which deletes the original now that its WebP replacement is confirmed. Do
   not run `--confirm-reviewed` on a file you have not actually looked at.

5. **Report** any file the script lists as `STILL_OVER_BUDGET` (over 1MB
   after the full quality ladder) or `PENDING_REVIEW` (a target already
   exists for this slot — normally this source's own not-yet-confirmed
   prior output; run `--confirm-reviewed` on it once reviewed, same as any
   other `NEEDS_VISUAL_REVIEW` file, or investigate manually if it looks
   like a genuine unexpected duplicate) to the operator. Do not push WebP
   quality below 80 or resize to resolve `STILL_OVER_BUDGET` without an
   explicit operator decision.

6. **Commit** via `/commit` (S-76). No override token is needed for the
   `static/media/` changes themselves — `path_guard.py`'s `ALLOWED_PREFIXES`
   permanently allows this path (added alongside this skill's own creation).

> **Skill context close** — run after the last step:
> ```bash
> PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/commands/governance/skill_context.py end --skill S-119 --status completed
> ```

## Hard Constraints

- **WebP quality floor is 80, never lower, and never automatic-only.** Step
  down the ladder `95 → 90 → 85 → 80` only as needed. If quality 80 still
  doesn't fit budget, stop and report `STILL_OVER_BUDGET` — do not go lower,
  do not resize, do not switch to another lossy format, without a fresh
  operator decision.
- **A WebP result is never self-certified — no numeric metric decides this.**
  PSNR/SSIM are reported for context but never gate acceptance: they were
  tried as a floor and abandoned after two independently confirmed
  visually-perfect results measured 21.6dB/0.948 and 14.8dB/0.770 — a range
  wide enough that no single cutoff could pass both without also passing
  much worse cases, or reject one without also rejecting the other. Every
  `NEEDS_VISUAL_REVIEW` file requires an actual visual comparison before
  `--confirm-reviewed` deletes the original.
- **Never silently overwrite** an existing `icon.webp`/`banner.webp` when a
  *different* source file also maps to that slot. Report it as
  `PENDING_REVIEW` and leave both files untouched — WebP output is never
  pixel-identical to its own lossy source, so pixel comparison can't
  distinguish "this is that source's own prior output" from "a genuinely
  different duplicate wants this slot"; both get the same safe non-action.
- **Never invent a missing icon or banner.** If a platform only has one of the
  two, convert what exists; do not synthesize or duplicate the other.
- **Resolution (pixel dimensions) must stay identical.** Pixel *values*
  change by design — WebP here is lossy — but dimensions never do; the
  visual-review step is what stands in for "no perceptible loss," not a
  pixel-exact check.

## Post-conditions

- Every file processed in scope is `< 1,048,576` bytes
- Filenames match the convention (`icon.webp` / `banner.webp` per directory)
- Every `NEEDS_VISUAL_REVIEW` file has either been confirmed via
  `--confirm-reviewed` (original deleted) or is still explicitly pending
  review (original still present) — never silently left ambiguous
- `git status` shows changes only under `static/media/` for this run
- Any file that couldn't be brought under budget is reported, not silently
  left in a half-renamed state

## Error handling

- Source file dimensions don't match either the square-icon or ~2:1-banner
  shape: report as `UNCLASSIFIED`, skip it, continue with the rest of the
  batch
- A target already exists for this slot from a different source file: report
  as `PENDING_REVIEW`, skip it, continue with the rest of the batch
- File still `>= 1MB` after the full WebP quality ladder (95/90/85/80):
  report as `STILL_OVER_BUDGET`, leave it under its original name/location,
  continue with the rest of the batch
- `--confirm-reviewed` called on a path with no corresponding `.webp` target:
  report `NO_TARGET_FOUND`, do not delete anything
- `--confirm-reviewed` called on a path whose WebP replacement was written
  in place (same filename, just re-encoded — nothing separate to delete):
  report `ALREADY_FINALIZED`, do not delete anything
