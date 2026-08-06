# S-119: Media Optimize — Ensure Every Icon/Banner Slot Has Both WebP and PNG

**Arguments**: $ARGUMENTS
Expected format:
- (no arguments) — process every file under `static/media/`
- `{family}` — scope to one family (e.g. `pdf`)
- `{family} {platform}` — scope to one family/platform (e.g. `pdf python`)

## Purpose

Product icons and banner (social-preview) images dropped under
`static/media/{family}/{platform}/` need to satisfy two constraints at once:
stay under GitHub's 1MB per-file guidance, and render reliably everywhere they
might be consumed. Neither WebP nor PNG alone is the complete answer — this
skill produces **both** `{name}.webp` and `{name}.png` for every slot, each
independently under 1MB, and lets a downstream consumer choose (e.g. a future
`<picture>` element with a WebP `<source>` and a PNG `<img>` fallback).

**Why both, not one** (researched, not assumed — 2026-08-06): git and GitHub
have no image-format restriction of their own (GitHub's own UI added native
WebP rendering in August 2025), so that is not the constraint. The real one is
Open Graph (`og:image`) crawler compatibility for social-preview banners —
by 2026 most major platforms support WebP, but every source surveyed
describes it the same way: *"safe as a primary, risky as the only format."*
PNG remains the safe universal fallback. Rather than betting the whole asset
on either format, this skill produces both.

**Naming convention** (directory already encodes family/platform, so
filenames don't repeat it). Every slot has up to two canonical files:
- Family-level icon (no platform subfolder): `static/media/{family}/icon.png` + `icon.webp`
- Platform icon (square: 1024×1024 or 1254×1254): `static/media/{family}/{platform}/icon.png` + `icon.webp`
- Platform banner (landscape ~2:1: 1774×887): `static/media/{family}/{platform}/banner.png` + `banner.webp`

Classification is by pixel dimensions, not filename — square = icon, ~2:1
landscape = banner.

## The two techniques (each independently validated against the real corpus, 2026-08-06)

- **Missing `.webp`**: quality ladder `95 → 90 → 85 → 80`, method 6. Size is
  the sole automated acceptance criterion — PSNR/SSIM are computed and
  reported for context only. They were tried as a gate and abandoned: two
  independently confirmed visually-perfect results measured 21.6dB/0.948 and
  14.8dB/0.770, too wide and unpredictable a range on this sharp-edged,
  mostly-flat-color content to serve as a rejection threshold.
- **Missing `.png`**: lossless attempt first (rarely fits this content, costs
  little to try), then **palette-quantization** — `256 → 192 → 128 → 96 → 64`
  colors, Floyd–Steinberg dithered, alpha quantized and reattached separately
  from RGB so transparency stays exact — then `oxipng -o max --strip safe`
  polish. **A literal "decode WebP, re-encode PNG" round trip was tested
  against all 72 real files and rejected**: it left 2 files over 1MB and
  several within 1–6% of the cap, because re-encoding truecolor PNG doesn't
  change PNG's color *mode* — the file still balloons 2.5–4x larger than the
  WebP regardless of the source path. Palette quantization is PNG's own
  mechanism for this problem (color type 3), not a round trip through an
  unrelated codec, and fit all 72 real files with 42–96% headroom.

## Pre-conditions

1. `static/media/` exists and contains at least one image file in scope
2. `.venv` is present with Pillow installed
3. `oxipng` is on PATH, or the script can reach GitHub to download the
   official release binary into its local cache (`cache/oxipng/`)

## Steps

> **Skill context gate** — run before step 1:
> ```bash
> PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/commands/governance/skill_context.py begin --skill S-119 --scope "*"
> ```

1. **Dry-run first**:
   ```bash
   .venv/Scripts/python scripts/pipeline/commands/ops/optimize_media_assets.py [family] [platform] --dry-run
   ```
   For each classified file, reports: current path, which sibling(s) are
   missing, and target path(s). A file already named `icon.png`/`icon.webp`/
   `banner.png`/`banner.webp` (a canonical artifact — true for all 72 files as
   of 2026-08-06) is treated as a keeper: only its missing sibling is planned,
   never its own replacement. A raw/temp-named upload plans both targets.

2. **Review the plan**: confirm no unexpected `UNCLASSIFIED` (dimensions
   matching neither shape — never guessed) and no `PENDING_REVIEW` silently
   ignored (a target already exists for a slot a *different* file also maps
   to — see Hard Constraints).

3. **Apply**:
   ```bash
   .venv/Scripts/python scripts/pipeline/commands/ops/optimize_media_assets.py [family] [platform] --apply
   ```
   For each source: if it's already a canonical artifact, only the missing
   sibling is generated from its decoded pixels — **the canonical source
   itself is never modified or deleted.** If it's a raw upload, both
   `icon.png`/`banner.png` and `icon.webp`/`banner.webp` are generated from
   it; the raw source is left in place pending review, not deleted
   automatically.

4. **Verify — visual review is the only real gate, for either format.**
   PSNR/SSIM are reported per generated file for context but do not decide
   acceptance (see the evidence above). Render every `NEEDS_VISUAL_REVIEW`
   (and `TRANSPARENCY_EXTRACTED_NEEDS_REVIEW` — see Hard Constraints) file's
   before/after pair and look at them side by side. For a canonical source,
   "before" is the untouched sibling that already exists; for a raw upload,
   "before" is the raw source itself. Only after this passes, run:
   ```bash
   .venv/Scripts/python scripts/pipeline/commands/ops/optimize_media_assets.py --confirm-reviewed <reported source path> [<path> ...]
   ```
   For a canonical source this only marks the sibling accepted (nothing to
   delete — the source was never going anywhere). For a raw upload, this
   deletes the raw source now that both derivatives are confirmed. Do not run
   `--confirm-reviewed` on a file you have not actually looked at.

5. **Report** any `STILL_OVER_BUDGET` (over 1MB after the full ladder for
   that format) or `PENDING_REVIEW` (target collision) to the operator. Do
   not push WebP quality below 80, PNG colors below 64, or resize, without an
   explicit operator decision.

6. **Commit** via `/commit` (S-76). No override token is needed for
   `static/media/` — `path_guard.py`'s `ALLOWED_PREFIXES` permanently allows
   this path.

> **Skill context close** — run after the last step:
> ```bash
> PYTHONPATH=scripts/pipeline .venv/Scripts/python scripts/pipeline/commands/governance/skill_context.py end --skill S-119 --status completed
> ```

## Hard Constraints

- **A canonical artifact (`icon.png`/`icon.webp`/`banner.png`/`banner.webp`)
  is never modified or deleted**, regardless of what else runs against its
  slot. Only its missing sibling is generated.
- **WebP quality floor is 80; PNG color floor is 64 colors — never lower,
  never automatic-only.** Step down each ladder only as needed. If the floor
  still doesn't fit budget for a format, report `STILL_OVER_BUDGET` for that
  format and stop — no resizing, no format substitution, without a fresh
  operator decision.
- **Neither format's result is ever self-certified.** The automated
  PSNR/SSIM computation exists only for context — it has been shown to read
  as "mediocre" on results that are visually perfect, in both directions.
  Every `NEEDS_VISUAL_REVIEW` file requires an actual visual comparison
  before `--confirm-reviewed`.
- **Target collisions are never guessed through.** If a slot's target already
  exists and the current source is a *different* file than whatever produced
  it, report `PENDING_REVIEW` and touch neither file — a lossy format can
  never be pixel-identical to its own source by construction, so pixel
  comparison cannot distinguish "this is that source's own prior output" from
  "a genuinely different file wants this slot."
- **Never invent a missing icon or banner.** If a platform only has one
  shape's source, generate that shape's two artifacts; do not synthesize the
  other shape.
- **Transparency extraction (for a future non-alpha source, e.g. a JPG) is a
  heuristic, not a solved problem.** Only attempted when a border-strip
  sample is uniform and close to pure black or pure white; otherwise convert
  straight to an opaque artifact and flag for manual review rather than
  guessing. Results get the distinct `TRANSPARENCY_EXTRACTED_NEEDS_REVIEW`
  status for extra scrutiny during visual review.
- **Resolution (pixel dimensions) never changes** in either format. Pixel
  *values* change by design for the lossy paths — the visual-review step is
  what stands in for "no perceptible loss," not a pixel-exact check (which
  does still apply to the lossless PNG path when it succeeds).

## Post-conditions

- Every generated file is `< 1,048,576` bytes
- Every slot with a source has both `icon.png`+`icon.webp` or
  `banner.png`+`banner.webp` — never just one, once processing completes
- Existing canonical files are untouched — verify via hash comparison, not
  just "the file still exists"
- Every `NEEDS_VISUAL_REVIEW`/`TRANSPARENCY_EXTRACTED_NEEDS_REVIEW` file has
  either been confirmed (raw-upload source deleted, or canonical-source
  sibling marked accepted) or is still explicitly pending — never silently
  left ambiguous
- `git status` shows changes only under `static/media/` for this run —
  additions only when the source was already canonical (no deletions, no
  renames)

## Error handling

- Source dimensions match neither shape: `UNCLASSIFIED`, skip, continue
- A different file already occupies a target this source also maps to:
  `PENDING_REVIEW`, skip, continue
- A format's full ladder still exceeds budget: `STILL_OVER_BUDGET` for that
  format; if it's a raw upload and either format failed, the whole file is
  `STILL_OVER_BUDGET` (both derivatives must succeed before review is
  possible)
- `--confirm-reviewed` on a canonical source: `ALREADY_FINALIZED`, nothing
  deleted
- `--confirm-reviewed` on a raw upload missing one or both targets:
  `NO_TARGET_FOUND`, nothing deleted
- `oxipng` unreachable (not on PATH and download fails): halt the whole run
  with a clear error rather than silently skipping the lossless/polish steps
