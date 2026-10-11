"""
generate_missing_product_icons.py -- TC-MEDIA-02 (media-icon-generation-2026-08-06):
synthesize static/media/{family}/{platform}/icon.webp for family/platform slots that
have zero existing icon content, by recoloring an existing sibling icon (same family,
different platform) or a Desktop source SVG, and compositing the correct platform
badge cropped from the static/media/cells/ reference set.

Scope boundary vs S-119 (scripts/pipeline/commands/ops/optimize_media_assets.py):
this script ONLY writes new icon.webp (and, for one Tier-B target, banner.webp)
content for slots with zero existing icon -- it never writes the .png sibling
itself. After this script writes icon.webp, run:
    .venv/Scripts/python scripts/pipeline/commands/ops/optimize_media_assets.py
        {family} {platform} --apply
to backfill icon.png via S-119's already-tested lossless/quantization ladder --
that is S-119's own stated purpose (given one canonical format exists, generate the
missing sibling) and it produces a better-optimized PNG than reimplementing that
logic here would. See reports/skill-gaps/2026-08-06-media-composite-generation.md
for the full capability-gap rationale and why these two scripts do not conflict
despite touching the same directory tree.

CONTRACT: scripts/maintenance/generate_missing_product_icons.py
  purpose: one-off backfill of missing static/media/{family}/{platform}/icon.webp
           assets for launched platforms that have zero icon today, plus (Tier B,
           lower confidence) two family-root icons and one new family's icon+banner.
  inputs: static/media/cells/{platform}/icon.webp (accent-hue + badge reference,
          the only complete 7-platform set), static/media/{family}/{platform}/
          icon.webp (sibling shape source, where present), Desktop SVGs
          (aspose_{family}-for-net.svg, shape source where no sibling exists)
  outputs: static/media/{family}/{platform}/icon.webp -- new files only, never
           overwrites an existing icon.webp (is_gap() guards every write)
  idempotent: yes -- discover_gaps() only returns slots with zero existing icon.webp;
           re-running after a slot is filled is a no-op for that slot.

CLI:
    .venv/Scripts/python scripts/maintenance/generate_missing_product_icons.py --dry-run
    .venv/Scripts/python scripts/maintenance/generate_missing_product_icons.py email --apply
    .venv/Scripts/python scripts/maintenance/generate_missing_product_icons.py --debug-badge net
"""
from __future__ import annotations

from pathlib import Path
import argparse
import colorsys
import json
import subprocess
import sys

from PIL import Image, ImageDraw, ImageFont

_REPO_ROOT = Path(__file__).resolve().parents[2]
_MEDIA_ROOT = _REPO_ROOT / "static" / "media"
_CONTENT_ROOT = _REPO_ROOT / "content" / "products.aspose.org" / "en"
_DESKTOP = Path(r"C:\Users\prora\Desktop")
_DEBUG_DIR = _REPO_ROOT / "reports" / "evidence" / "media-icon-generation-20260806" / "debug"

BADGE_DONOR_FAMILY = "cells"  # only complete, verified 7-platform reference set

# Gap plan (from the approved plan, TC-MEDIA-04/05 scope). Each entry:
#   (family, platform, shape_source) where shape_source is either
#   ("sibling", donor_family, donor_platform) or ("svg", family)
TIER_A_GAPS = [
    ("3d", "typescript", ("sibling", "3d", "python")),
    ("email", "net", ("sibling", "email", "python")),
    ("email", "cpp", ("sibling", "email", "python")),
    ("note", "python", ("svg", "note")),
    ("slides", "net", ("svg", "slides")),
    ("slides", "java", ("svg", "slides")),
    ("slides", "cpp", ("svg", "slides")),
    ("slides", "python", ("svg", "slides")),
    ("words", "net", ("svg", "words")),
    ("words", "python", ("svg", "words")),
]


# -- Discovery ----------------------------------------------------------------

def discover_gaps() -> list[dict]:
    """Cross-check the static gap plan (TIER_A_GAPS) against live filesystem state:
    a platform is 'live' if content/products.aspose.org/en/{family}/{platform}/
    exists, and a 'gap' only if static/media/{family}/{platform}/icon.webp does
    NOT already exist. Never trusts the hardcoded list blindly -- re-verifies both
    conditions every run so this stays idempotent and safe to re-run."""
    gaps = []
    for family, platform, source in TIER_A_GAPS:
        content_dir = _CONTENT_ROOT / family / platform
        icon_path = _MEDIA_ROOT / family / platform / "icon.webp"
        live = content_dir.exists()
        already_has_icon = icon_path.exists()
        gaps.append({
            "family": family, "platform": platform, "source": source,
            "icon_path": str(icon_path), "live": live,
            "is_gap": live and not already_has_icon,
            "skip_reason": None if live else "platform not live in content/",
        })
    return gaps


# -- Platform accent-hue measurement (from cells/, the reference set) ---------

def measure_platform_hue(platform: str) -> float:
    """Median hue (0-1, colorsys convention) among high-saturation pixels of
    static/media/cells/{platform}/icon.webp -- the platform's established accent
    color, measured fresh every run rather than hardcoded."""
    path = _MEDIA_ROOT / "cells" / platform / "icon.webp"
    with Image.open(path) as im:
        im = im.convert("RGBA")
        hues = []
        w, h = im.size
        # Sample every 4th pixel for speed; still thousands of samples.
        for y in range(0, h, 4):
            for x in range(0, w, 4):
                r, g, b, a = im.getpixel((x, y))
                if a < 200:
                    continue
                hh, ss, vv = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
                if ss >= 0.35 and 0.2 <= vv <= 0.95:
                    hues.append(hh)
    if not hues:
        raise RuntimeError(f"could not measure accent hue for platform={platform!r}")
    hues.sort()
    return hues[len(hues) // 2]


# -- Document / badge bounding-box detection -----------------------------------

_WHITE_CUTOFF = 240
_ALPHA_CUTOFF = 200  # near-FULLY-opaque, not just "present" -- excludes soft
# drop-shadow/anti-alias blur pixels (seen at canvas edges with alpha ~150
# and a faint grayish tint) that a loose >10 threshold treats as foreground.


def _is_foreground(rgba: tuple[int, int, int, int]) -> bool:
    """True if this pixel is shape content, not background -- covers BOTH
    source-image conventions found in static/media/: transparent-margin RGBA
    (cells/*, alpha=0 outside the shape) and opaque-white-canvas RGBA (3d/*,
    alpha=255 everywhere but background pixels are near-pure-white). A pixel
    is background if it's not near-fully-opaque, OR if it's near-white;
    anything else (colored strokes/fills, or off-white shaded content) is
    foreground."""
    r, g, b, a = rgba
    if a < _ALPHA_CUTOFF:
        return False
    if r >= _WHITE_CUTOFF and g >= _WHITE_CUTOFF and b >= _WHITE_CUTOFF:
        return False
    return True


def detect_document_bbox(im: Image.Image) -> tuple[int, int, int, int]:
    """Bounding box of the document shape, via foreground-edge scan along a
    column/row well inside the shape (avoids corner rounding and badge overlap
    at the top-right). Only the FIRST foreground pixel from each edge matters
    -- the document's own white interior (present in both source-image
    conventions) being classified as background doesn't affect this, since
    the border stroke is always hit first."""
    w, h = im.size
    probe_x = int(w * 0.30)
    probe_y = int(h * 0.60)
    col = [_is_foreground(im.getpixel((probe_x, yy))) for yy in range(h)]
    row = [_is_foreground(im.getpixel((xx, probe_y))) for xx in range(w)]
    top = next(i for i, v in enumerate(col) if v)
    bottom = h - 1 - next(i for i, v in enumerate(reversed(col)) if v)
    left = next(i for i, v in enumerate(row) if v)
    right = w - 1 - next(i for i, v in enumerate(reversed(row)) if v)
    return (left, top, right, bottom)


def _longest_run(getval, coords, threshold: int) -> "tuple[int, int] | None":
    """Longest contiguous run of coords where getval(c) > threshold. Robust to
    isolated noise (webp compression artifacts, soft shadow bleed) that a
    plain min/max over all matching coords would be thrown off by -- picks
    the single solid blob, not the outer envelope of scattered hits."""
    runs = []
    start = prev = None
    for c in coords:
        if getval(c) > threshold:
            if start is None:
                start = c
            prev = c
        elif start is not None:
            runs.append((start, prev))
            start = None
    if start is not None:
        runs.append((start, prev))
    if not runs:
        return None
    return max(runs, key=lambda r: r[1] - r[0])


def detect_badge_bbox(im: Image.Image, doc_bbox: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
    """Bounding box of the platform badge circle. The badge overlaps the
    document's top-right corner, so alpha alone can't tell badge-on-document
    apart from plain document-white in the OCCLUDED quarter -- only the part
    of the circle strictly outside the document is trustworthy. Uses two
    unoccluded chord scans, each taking the LONGEST CONTIGUOUS run (not a
    plain min/max, which webp-compression noise and soft edge/shadow bleed
    near the document boundary throws off):
      - columns strictly right of the document's right edge are unoccluded
        top-to-bottom -- the column with the longest solid run approximates
        the true vertical diameter, and that column's x is close to true cx.
      - rows strictly above the document's top edge are unoccluded
        left-to-right -- the row with the longest solid run approximates the
        true horizontal diameter, and that row's y is close to true cy.
    High alpha threshold (128, not a loose >10) deliberately excludes soft
    anti-aliased/shadow pixels near the document edge that a low threshold
    picks up as false chord extensions."""
    w, h = im.size
    alpha = im.split()[-1]
    left, top, right, bottom = doc_bbox
    quadrant_x0 = int(w * 0.50)
    quadrant_y1 = int(h * 0.55)
    threshold = 128

    best_vspan, best_vrun, best_vx = -1, None, None
    for x in range(right + 2, w):
        run = _longest_run(lambda yy: alpha.getpixel((x, yy)), range(0, quadrant_y1), threshold)
        if run and (run[1] - run[0]) > best_vspan:
            best_vspan, best_vrun, best_vx = run[1] - run[0], run, x

    best_hspan, best_hrun, best_hy = -1, None, None
    for y in range(0, max(top - 2, 0)):
        run = _longest_run(lambda xx: alpha.getpixel((xx, y)), range(quadrant_x0, w), threshold)
        if run and (run[1] - run[0]) > best_hspan:
            best_hspan, best_hrun, best_hy = run[1] - run[0], run, y

    if best_vrun is None or best_hrun is None:
        raise RuntimeError("could not find both an unoccluded vertical and horizontal badge chord")

    diameter = max(best_vspan, best_hspan)
    cy = (best_vrun[0] + best_vrun[1]) / 2
    cx = (best_hrun[0] + best_hrun[1]) / 2
    # Chord-based diameter is a slight underestimate unless the sampled
    # column/row passes exactly through the true center -- pad a few percent
    # so the crop clears the badge's outer ring rather than clipping it.
    r = diameter / 2 * 1.06
    return (round(cx - r), round(cy - r), round(cx + r), round(cy + r))


def extract_badge(family: str, platform: str, out_path: Path) -> tuple[Image.Image, tuple[int, int, int, int], tuple[int, int, int, int]]:
    """Crop the badge for (family, platform) and save a debug PNG. Returns
    (badge_image, doc_bbox, badge_bbox) of the SOURCE icon it was cropped from.
    The crop is masked to a true circle (not left as a square bounding box):
    the badge is round, but its bounding-box CORNERS sit outside the visible
    circle and can carry a sliver of the DONOR's own document color bleeding
    through (donor is always cells/, whose per-platform document color
    happens to equal the target platform's own recolored hue for python-
    targeted gaps -- note/python, slides/python, words/python -- so a square
    crop's corner bleed showed up as a stray yellow smear against the
    target's white document interior, found during Tier-A batch review).
    Masking to a circle removes the corner content entirely regardless of
    platform, rather than relying on donor/target hue happening to match."""
    src_path = _MEDIA_ROOT / family / platform / "icon.webp"
    with Image.open(src_path) as im:
        im = im.convert("RGBA")
        doc_bbox = detect_document_bbox(im)
        badge_bbox = detect_badge_bbox(im, doc_bbox)
        badge = im.crop(badge_bbox)
    mask = Image.new("L", badge.size, 0)
    ImageDraw.Draw(mask).ellipse((0, 0, badge.size[0] - 1, badge.size[1] - 1), fill=255)
    badge.putalpha(Image.composite(badge.split()[-1], Image.new("L", badge.size, 0), mask))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    badge.save(out_path)
    return badge, doc_bbox, badge_bbox


# -- Recoloring -----------------------------------------------------------------

def recolor_icon(im: Image.Image, target_hue: float, sat_threshold: float = 0.15) -> Image.Image:
    """HSV hue-replace: pixels at/above sat_threshold get their hue replaced with
    target_hue (saturation and value preserved -- keeps existing shading/gradient
    intact). Pixels below the threshold (white/black/gray badge content,
    highlights) are left untouched -- falls out of the threshold for free, no
    explicit masking needed."""
    im = im.convert("RGBA")
    w, h = im.size
    px = im.load()
    for y in range(h):
        for x in range(w):
            r, g, b, a = px[x, y]
            if a == 0:
                continue
            hh, ss, vv = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
            if ss >= sat_threshold:
                nr, ng, nb = colorsys.hsv_to_rgb(target_hue, ss, vv)
                px[x, y] = (round(nr * 255), round(ng * 255), round(nb * 255), a)
    return im


def compute_badge_placement(target_doc_bbox: tuple[int, int, int, int],
                             donor_doc_bbox: tuple[int, int, int, int],
                             donor_badge_bbox: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
    """Badge placement (left, top, width, height) on the TARGET icon, computed
    as a fraction of the donor document's own width/height and re-applied to
    the target document's bbox -- not an absolute canvas coordinate (document
    position varies across platforms within a family, confirmed during
    planning). Used for BOTH clearing the old badge region and placing the new
    one, so the two are always co-located by construction -- using two
    independently-derived regions (e.g. a detected old-badge bbox and a
    donor-relative new-badge placement) can disagree enough to leave a gap
    neither region covers (found during pilot testing on 3d/typescript)."""
    dl, dt, dr, db = donor_doc_bbox
    bl, bt, br, bb = donor_badge_bbox
    doc_w, doc_h = (dr - dl), (db - dt)
    rel_l, rel_t = (bl - dl) / doc_w, (bt - dt) / doc_h
    rel_w, rel_h = (br - bl) / doc_w, (bb - bt) / doc_h

    tl, tt, tr, tb = target_doc_bbox
    t_doc_w, t_doc_h = (tr - tl), (tb - tt)
    new_l = round(tl + rel_l * t_doc_w)
    new_t = round(tt + rel_t * t_doc_h)
    new_w = round(rel_w * t_doc_w)
    new_h = round(rel_h * t_doc_h)
    return (new_l, new_t, new_w, new_h)


def clear_badge_region(im: Image.Image, placement: tuple[int, int, int, int],
                        doc_bbox: "tuple[int, int, int, int] | None" = None,
                        margin: float = 1.25, min_radius_frac_of_doc_w: float = 0.24) -> Image.Image:
    """Wipe alpha to 0 in an oversized ellipse centered on the region the new
    badge will occupy (see compute_badge_placement), before recoloring +
    compositing it, so no old badge/hue fringe survives around the new
    badge's edges. The clear radius is the LARGER of (a) the new badge's own
    size * margin, and (b) a fraction of the document's width -- (a) alone is
    insufficient when the OLD badge being replaced was bigger than the new
    one (e.g. python's badge measures ~41% of its document's width, sizeable
    even by this design system's own range, vs. net's ~24% -- clearing only
    to net's own footprint left a visible sliver of the old python badge
    peeking out, found during pilot testing on email/net)."""
    im = im.convert("RGBA")
    l, t, w, h = placement
    cx, cy = l + w / 2, t + h / 2
    rad_x, rad_y = w / 2 * margin, h / 2 * margin
    if doc_bbox is not None:
        dl, dt, dr, db = doc_bbox
        doc_w = dr - dl
        floor_r = doc_w * min_radius_frac_of_doc_w
        rad_x, rad_y = max(rad_x, floor_r), max(rad_y, floor_r)
    px = im.load()
    for y in range(max(0, int(cy - rad_y - 2)), min(im.height, int(cy + rad_y + 2))):
        for x in range(max(0, int(cx - rad_x - 2)), min(im.width, int(cx + rad_x + 2))):
            if ((x - cx) / rad_x) ** 2 + ((y - cy) / rad_y) ** 2 <= 1.0:
                r_, g_, b_, a_ = im.getpixel((x, y))
                im.putpixel((x, y), (r_, g_, b_, 0))
    return im


def composite_badge(im: Image.Image, badge: Image.Image, placement: tuple[int, int, int, int]) -> Image.Image:
    """Paste badge at the given (left, top, width, height) placement."""
    im = im.convert("RGBA")
    l, t, w, h = placement
    resized_badge = badge.resize((w, h), Image.LANCZOS)
    im.alpha_composite(resized_badge, (l, t))
    return im


# -- SVG shape source -----------------------------------------------------------

_EDGE_CANDIDATES = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]


def find_edge() -> str:
    for cand in _EDGE_CANDIDATES:
        if Path(cand).exists():
            return cand
    raise RuntimeError("msedge.exe not found at any known path")


def rasterize_svg(svg_path: Path, out_png: Path, size: int = 1024, content_frac: float = 0.75) -> None:
    """Rasterize svg_path into a size x size transparent PNG, with the SVG's
    own artwork scaled to occupy only content_frac of the canvas (centered) --
    NOT full-bleed. The raw Desktop SVGs (viewBox 0 0 277 277) render
    edge-to-edge if navigated to directly, leaving no margin for a badge to
    extend into; static/media/cells/'s reference icons, by contrast, have the
    document shape occupying ~75% of their canvas with margin around it (found
    when note/python's badge came out clipped against the canvas edge --
    diagnosis: cells/python's doc_bbox is 769px wide on a 1024 canvas, ~75%,
    while a direct SVG rasterization measured 996px wide, ~97%, leaving no
    room for the donor-relative badge placement to land on-canvas). A small
    wrapper HTML page with the SVG sized via CSS reproduces that margin
    without needing a new SVG-rasterization dependency."""
    edge = find_edge()
    out_png.parent.mkdir(parents=True, exist_ok=True)
    content_size = round(size * content_frac)
    wrapper_html = out_png.with_suffix(".wrapper.html")
    wrapper_html.write_text(
        f"""<!doctype html><html><head><style>
html,body {{ margin:0; padding:0; background:transparent; width:{size}px; height:{size}px; }}
.frame {{ width:{size}px; height:{size}px; display:flex; align-items:center; justify-content:center; }}
img {{ width:{content_size}px; height:{content_size}px; }}
</style></head><body><div class="frame"><img src="{svg_path.resolve().as_uri()}"></div></body></html>""",
        encoding="utf-8",
    )
    cmd = [
        edge, "--headless", "--disable-gpu",
        f"--screenshot={out_png}",
        f"--window-size={size},{size}",
        "--default-background-color=00000000",
        wrapper_html.resolve().as_uri(),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True,
                            encoding="utf-8", errors="replace", timeout=30)
    if not out_png.exists():
        raise RuntimeError(f"rasterize_svg failed for {svg_path}: {result.stderr or result.stdout}")


def load_family_svg(family: str) -> Path:
    path = _DESKTOP / f"aspose_{family}-for-net.svg"
    if not path.exists():
        raise FileNotFoundError(f"no Desktop SVG for family={family!r}: {path}")
    return path


# -- Icon build per shape-source type --------------------------------------------

def build_icon_from_sibling(family: str, donor_platform: str, target_platform: str) -> Image.Image:
    src_path = _MEDIA_ROOT / family / donor_platform / "icon.webp"
    badge_debug = _DEBUG_DIR / f"badge_{BADGE_DONOR_FAMILY}_{target_platform}.png"
    badge, donor_doc_bbox, donor_badge_bbox = extract_badge(BADGE_DONOR_FAMILY, target_platform, badge_debug)

    with Image.open(src_path) as im:
        im = im.convert("RGBA")
        doc_bbox = detect_document_bbox(im)
        # Clear region = where the NEW badge will land (donor-relative
        # placement mapped onto this sibling's own doc_bbox), not a separately
        # detected "old badge" region -- using two independently-derived
        # regions can disagree enough to leave a gap neither covers (found
        # during pilot testing on 3d/typescript; see compute_badge_placement).
        placement = compute_badge_placement(doc_bbox, donor_doc_bbox, donor_badge_bbox)
        im = clear_badge_region(im, placement, doc_bbox=doc_bbox)
        target_hue = measure_platform_hue(target_platform)
        im = recolor_icon(im, target_hue)
        im = composite_badge(im, badge, placement)
    return im


def build_icon_from_svg(family: str, target_platform: str) -> Image.Image:
    svg_path = load_family_svg(family)
    tmp_png = _DEBUG_DIR / f"svg_raster_{family}.png"
    if not tmp_png.exists():
        rasterize_svg(svg_path, tmp_png)

    badge_debug = _DEBUG_DIR / f"badge_{BADGE_DONOR_FAMILY}_{target_platform}.png"
    badge, donor_doc_bbox, donor_badge_bbox = extract_badge(BADGE_DONOR_FAMILY, target_platform, badge_debug)

    with Image.open(tmp_png) as im:
        im = im.convert("RGBA")
        doc_bbox = detect_document_bbox(im)
        target_hue = measure_platform_hue(target_platform)
        im = recolor_icon(im, target_hue)
        placement = compute_badge_placement(doc_bbox, donor_doc_bbox, donor_badge_bbox)
        im = composite_badge(im, badge, placement)
    return im


def build_icon(gap: dict) -> Image.Image:
    kind = gap["source"][0]
    if kind == "sibling":
        _, donor_family, donor_platform = gap["source"]
        return build_icon_from_sibling(donor_family, donor_platform, gap["platform"])
    elif kind == "svg":
        _, family = gap["source"]
        return build_icon_from_svg(family, gap["platform"])
    raise ValueError(f"unknown shape source kind: {kind!r}")


# -- Tier B: root-level family icon (Pillow approximation, best-effort) --------
#
# Root-level icons (static/media/{family}/icon.webp, no platform) use a
# visibly DIFFERENT, more elaborate style than platform icons: opaque RGB
# (not RGBA) 1254x1254 canvas, solid black background, a slate-blue-gray
# rounded-rect frame with soft bevel shading, a circular glass-gradient inset
# with a white pictogram, and a white oval "FOSS" badge -- confirmed by
# sampling static/media/{cells,pdf,words,barcode}/icon.webp directly (all
# opaque RGB, black background, closely-matching slate-blue palette). This is
# a fundamentally different rendering technique (soft gradients/bevels) than
# the flat-color platform icons built above, and is explicitly flagged
# lower-confidence in the plan -- this is a simplified approximation, not an
# attempt at the reference's full glass/photoreal shading.

_ROOT_SIZE = 1254
_ROOT_FRAME_COLOR = (72, 82, 97)
_ROOT_FRAME_LIGHT = (98, 110, 128)
_ROOT_CIRCLE_DARK = (44, 70, 105)
_ROOT_CIRCLE_LIGHT = (118, 150, 188)


def _rounded_rect_mask(size: tuple[int, int], radius: int) -> Image.Image:
    mask = Image.new("L", size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, size[0] - 1, size[1] - 1), radius=radius, fill=255)
    return mask


def _diagonal_gradient(size: tuple[int, int], color_a: tuple[int, int, int], color_b: tuple[int, int, int]) -> Image.Image:
    w, h = size
    grad = Image.new("RGB", size)
    px = grad.load()
    for y in range(h):
        for x in range(w):
            t = (x / w + y / h) / 2
            px[x, y] = tuple(round(color_a[c] + (color_b[c] - color_a[c]) * t) for c in range(3))
    return grad


def build_root_icon(letter: str, glyph: Image.Image) -> Image.Image:
    """glyph: a white-on-transparent RGBA image to center inside the circle."""
    size = _ROOT_SIZE
    canvas = Image.new("RGB", (size, size), (0, 0, 0))

    frame_margin = round(size * 0.14)
    frame_box = (frame_margin, frame_margin, size - frame_margin, size - frame_margin)
    frame_radius = round(size * 0.09)
    frame_grad = _diagonal_gradient((size, size), _ROOT_FRAME_LIGHT, _ROOT_FRAME_COLOR)
    frame_mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(frame_mask).rounded_rectangle(frame_box, radius=frame_radius, fill=255)
    canvas.paste(frame_grad, (0, 0), frame_mask)

    # Subtle inset bevel line -- same slate-blue family, one shade darker,
    # NOT white (the reference card interior is solid slate-blue throughout;
    # an earlier attempt filled this white and hid the whole frame + letter).
    inner_margin = round(size * 0.02)
    inner_box = (frame_box[0] + inner_margin, frame_box[1] + inner_margin,
                 frame_box[2] - inner_margin, frame_box[3] - inner_margin)
    inner_radius = round(frame_radius * 0.85)
    bevel_mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(bevel_mask).rounded_rectangle(inner_box, radius=inner_radius, fill=255)
    bevel_fill = Image.new("RGB", (size, size), tuple(round(c * 0.82) for c in _ROOT_FRAME_COLOR))
    canvas.paste(bevel_fill, (0, 0), bevel_mask)

    letter_layer = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    font = ImageFont.truetype(r"C:\Windows\Fonts\segoeuib.ttf", round(size * 0.11))
    ImageDraw.Draw(letter_layer).text(
        (frame_box[0] + size * 0.06, frame_box[1] + size * 0.02), letter, font=font, fill=(255, 255, 255, 255))
    canvas.paste(letter_layer, (0, 0), letter_layer)

    circle_d = round(size * 0.42)
    circle_cx = frame_box[0] + round((frame_box[2] - frame_box[0]) * 0.60)
    circle_cy = frame_box[1] + round((frame_box[3] - frame_box[1]) * 0.62)
    circle_grad = _diagonal_gradient((circle_d, circle_d), _ROOT_CIRCLE_DARK, _ROOT_CIRCLE_LIGHT)
    circle_mask = Image.new("L", (circle_d, circle_d), 0)
    ImageDraw.Draw(circle_mask).ellipse((0, 0, circle_d - 1, circle_d - 1), fill=255)
    circle_layer = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    circle_rgba = circle_grad.convert("RGBA")
    circle_rgba.putalpha(circle_mask)
    circle_layer.paste(circle_rgba, (circle_cx - circle_d // 2, circle_cy - circle_d // 2), circle_rgba)
    canvas.paste(circle_layer, (0, 0), circle_layer)

    glyph_max = round(circle_d * 0.55)
    gw, gh = glyph.size
    scale = min(glyph_max / gw, glyph_max / gh)
    glyph_resized = glyph.resize((round(gw * scale), round(gh * scale)), Image.LANCZOS)
    gl_x = circle_cx - glyph_resized.size[0] // 2
    gl_y = circle_cy - glyph_resized.size[1] // 2
    glyph_layer = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    glyph_layer.paste(glyph_resized, (gl_x, gl_y), glyph_resized)
    canvas.paste(glyph_layer, (0, 0), glyph_layer)

    badge_w, badge_h = round(size * 0.24), round(size * 0.115)
    badge_cx = frame_box[2] - round(size * 0.02)
    badge_cy = frame_box[1] + round(size * 0.03)
    badge_layer = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    bd = ImageDraw.Draw(badge_layer)
    badge_box = (badge_cx - badge_w, badge_cy - badge_h // 2, badge_cx, badge_cy + badge_h // 2)
    bd.ellipse((badge_box[0] - 4, badge_box[1] + 6, badge_box[2] + 4, badge_box[3] + 10), fill=(0, 0, 0, 90))
    bd.ellipse(badge_box, fill=(248, 249, 250, 255))
    foss_font = ImageFont.truetype(r"C:\Windows\Fonts\segoeuib.ttf", round(badge_h * 0.55))
    tb = bd.textbbox((0, 0), "FOSS", font=foss_font)
    tw, th = tb[2] - tb[0], tb[3] - tb[1]
    bd.text((badge_cx - badge_w / 2 - tw / 2, badge_cy - th / 2 - tb[1]), "FOSS", font=foss_font, fill=(45, 55, 72, 255))
    canvas.paste(badge_layer, (0, 0), badge_layer)

    return canvas


def draw_page_glyph() -> Image.Image:
    size = 400
    im = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rectangle((60, 40, 340, 340), outline=(255, 255, 255, 255), width=14)
    for i, y in enumerate(range(110, 300, 45)):
        d.line((100, y, 300, y), fill=(255, 255, 255, 255), width=12)
    return im


def draw_html_glyph() -> Image.Image:
    size = 400
    im = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    font = ImageFont.truetype(r"C:\Windows\Fonts\segoeuib.ttf", 220)
    d = ImageDraw.Draw(im)
    d.text((size / 2, size / 2), "</>", font=font, fill=(255, 255, 255, 255), anchor="mm")
    return im


def build_flat_icon_from_scratch(letter: str, glyph: Image.Image, target_platform: str) -> Image.Image:
    """Build a Tier-A-style flat platform icon (1024x1024 RGBA, transparent
    background, document outline + letter + colored circle glyph + platform
    badge) with NO existing shape to recolor/rasterize from -- used only for
    html, the one family with no Desktop SVG and no sibling icon anywhere.
    Hand-drawn in the same layout convention measured from the cells
    reference set (document ~75% of canvas, circle glyph bottom-right ~40%
    of document width, badge overlapping the top-right corner)."""
    size = 1024
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    hue = measure_platform_hue(target_platform)
    r, g, b = (round(c * 255) for c in colorsys.hsv_to_rgb(hue, 0.75, 0.75))
    accent = (r, g, b, 255)

    doc_box = (round(size * 0.12), round(size * 0.10), round(size * 0.83), round(size * 0.88))
    doc_bbox = doc_box
    d = ImageDraw.Draw(canvas)
    d.rounded_rectangle(doc_box, radius=round(size * 0.04), outline=accent, width=round(size * 0.018))

    letter_font = ImageFont.truetype(r"C:\Windows\Fonts\segoeuib.ttf", round(size * 0.14))
    d.text((doc_box[0] + size * 0.06, doc_box[1] + size * 0.06), letter, font=letter_font, fill=accent)

    circle_d = round((doc_box[2] - doc_box[0]) * 0.62)
    circle_cx = doc_box[0] + round((doc_box[2] - doc_box[0]) * 0.68)
    circle_cy = doc_box[1] + round((doc_box[3] - doc_box[1]) * 0.72)
    d.ellipse((circle_cx - circle_d // 2, circle_cy - circle_d // 2,
               circle_cx + circle_d // 2, circle_cy + circle_d // 2), fill=accent)

    glyph_max = round(circle_d * 0.55)
    gw, gh = glyph.size
    scale = min(glyph_max / gw, glyph_max / gh)
    glyph_resized = glyph.resize((round(gw * scale), round(gh * scale)), Image.LANCZOS)
    canvas.alpha_composite(glyph_resized, (circle_cx - glyph_resized.size[0] // 2, circle_cy - glyph_resized.size[1] // 2))

    badge_debug = _DEBUG_DIR / f"badge_{BADGE_DONOR_FAMILY}_{target_platform}.png"
    badge, donor_doc_bbox, donor_badge_bbox = extract_badge(BADGE_DONOR_FAMILY, target_platform, badge_debug)
    placement = compute_badge_placement(doc_bbox, donor_doc_bbox, donor_badge_bbox)
    canvas = composite_badge(canvas, badge, placement)
    return canvas


# -- Banner (Tier B: html/python only) ------------------------------------------
#
# Banner "chrome" (background gradient, particle swoosh, hex decorations,
# Aspose logo, Download button) is reused from a donor banner unchanged;
# only the icon slot and headline/subtitle text are replaced. Regions below
# were measured directly against static/media/cells/python/banner.webp by
# cropping AND pixel-sampling (not guessed, and revised twice after visual
# review caught two real bugs):
#   - icon slot: (100,180)-(560,610), clear of the wave decoration (~y>590).
#   - headline box: (580,190)-(1700,340) -- the donor's own headline
#     ("Aspose.Cells FOSS for Python") turned out to extend to ~x=1600
#     (confirmed: near-white pixels at x=1600,y=250-300), far past an
#     initial x=1480 guess that left old text visibly bleeding through.
#     Safe to go this wide because the hex decorations sit LOWER
#     (confirmed clear at y<350 for x up to 1700; first non-background hex
#     pixel found at x=1700,y=400) -- headline and hexes don't share a row.
#   - subtitle box: (580,350)-(1490,470) -- kept narrower than the headline
#     box since this row's y-range does approach where the hex decorations
#     start (~x=1700,y=400), and the subtitle text is shorter anyway.
# Background is NOT uniform -- sampling found a soft horizontal+vertical glow
# (darker at the edges, e.g. (1,0,61) at x=0, lighter toward center-right,
# e.g. (9,10,87) at x=1050-1200,y=20) -- a flat single-color fill left a
# visible rectangular seam over the lighter zone (also found during review).
# Reconstructed instead via reconstruct_background(): sample two
# content-free reference rows (y=20 near the top, y=160 just above where
# content starts) per-column, then linearly extrapolate each column's
# vertical gradient down through the clear box -- reproduces the real
# per-column glow instead of a flat guess.

_BANNER_ICON_BOX = (100, 180, 560, 610)
_BANNER_HEADLINE_BOX = (580, 190, 1750, 340)
_BANNER_SUBTITLE_BOX = (580, 350, 1610, 470)
_BANNER_BG_REF_ROWS = (20, 160)


def reconstruct_background(donor_banner: Image.Image, box: tuple[int, int, int, int]) -> Image.Image:
    """Return an RGB image the size of `box`, with each column's vertical
    color gradient linearly extrapolated from two content-free reference rows
    of the donor banner (see module note above) -- reproduces the real
    per-column background glow rather than a flat fill."""
    l, t, r, b = box
    y0, y1 = _BANNER_BG_REF_ROWS
    w, h = r - l, b - t
    out = Image.new("RGB", (w, h))
    px_out = out.load()
    row0 = [donor_banner.getpixel((x, y0)) for x in range(l, r)]
    row1 = [donor_banner.getpixel((x, y1)) for x in range(l, r)]
    for xi in range(w):
        c0, c1 = row0[xi], row1[xi]
        rate = tuple((c1[c] - c0[c]) / (y1 - y0) for c in range(3))
        for yi in range(h):
            y_abs = t + yi
            px_out[xi, yi] = tuple(
                max(0, min(255, round(c0[c] + rate[c] * (y_abs - y0)))) for c in range(3)
            )
    return out


def _fit_font(draw: ImageDraw.ImageDraw, text: str, max_width: int, start_size: int, min_size: int = 24) -> ImageFont.FreeTypeFont:
    size = start_size
    while size > min_size:
        font = ImageFont.truetype(r"C:\Windows\Fonts\segoeuib.ttf", size)
        bbox = draw.textbbox((0, 0), text, font=font)
        if bbox[2] - bbox[0] <= max_width:
            return font
        size -= 2
    return ImageFont.truetype(r"C:\Windows\Fonts\segoeuib.ttf", min_size)


def build_banner(family_display: str, platform_display: str, domain_noun: str,
                  icon: Image.Image, donor_banner_path: Path) -> Image.Image:
    donor = Image.open(donor_banner_path).convert("RGB")
    banner = donor.copy()

    icon_bg = reconstruct_background(donor, _BANNER_ICON_BOX)
    banner.paste(icon_bg, (_BANNER_ICON_BOX[0], _BANNER_ICON_BOX[1]))
    headline_bg = reconstruct_background(donor, _BANNER_HEADLINE_BOX)
    banner.paste(headline_bg, (_BANNER_HEADLINE_BOX[0], _BANNER_HEADLINE_BOX[1]))
    subtitle_bg = reconstruct_background(donor, _BANNER_SUBTITLE_BOX)
    banner.paste(subtitle_bg, (_BANNER_SUBTITLE_BOX[0], _BANNER_SUBTITLE_BOX[1]))

    icon_target = 420
    icon_small = icon.resize((icon_target, icon_target), Image.LANCZOS).convert("RGBA")
    ix = _BANNER_ICON_BOX[0] + ((_BANNER_ICON_BOX[2] - _BANNER_ICON_BOX[0]) - icon_target) // 2
    iy = _BANNER_ICON_BOX[1] + 20
    banner_rgba = banner.convert("RGBA")
    banner_rgba.alpha_composite(icon_small, (ix, iy))
    banner = banner_rgba.convert("RGB")
    d = ImageDraw.Draw(banner)

    tx = _BANNER_HEADLINE_BOX[0]
    headline_max_w = _BANNER_HEADLINE_BOX[2] - _BANNER_HEADLINE_BOX[0] - 10
    headline = f"Aspose.{family_display} FOSS for {platform_display}"
    headline_font = _fit_font(d, headline, headline_max_w, start_size=66)
    d.text((tx, _BANNER_HEADLINE_BOX[1] + 10), headline, font=headline_font, fill=(255, 255, 255))

    subtitle_max_w = _BANNER_SUBTITLE_BOX[2] - _BANNER_SUBTITLE_BOX[0] - 10
    line1 = f"Open-source {platform_display} API to read, write, manipulate,"
    line2 = f"and convert {domain_noun} file formats within {platform_display} applications."
    subtitle_font = _fit_font(d, max(line1, line2, key=len), subtitle_max_w, start_size=30, min_size=18)
    d.multiline_text((tx, _BANNER_SUBTITLE_BOX[1] + 10), f"{line1}\n{line2}", font=subtitle_font,
                      fill=(230, 230, 240), spacing=14)
    return banner


# -- Output ----------------------------------------------------------------------

def write_icon(gap: dict, im: Image.Image, apply: bool) -> dict:
    dest = Path(gap["icon_path"])
    record = {"family": gap["family"], "platform": gap["platform"], "dest": str(dest),
              "source": gap["source"]}
    if dest.exists():
        record["status"] = "SKIP_ALREADY_EXISTS"
        return record
    if not apply:
        record["status"] = "PLANNED"
        return record
    dest.parent.mkdir(parents=True, exist_ok=True)
    im.save(dest, "WEBP", quality=95, method=6)
    record["status"] = "WRITTEN"
    record["size_bytes"] = dest.stat().st_size
    record["dimensions"] = im.size
    record["mode"] = im.mode
    return record


def backfill_png(family: str, platform: str) -> None:
    """Invoke S-119 (optimize_media_assets.py) to generate the missing icon.png
    sibling from the icon.webp this script just wrote -- see module docstring
    for why this composition, not reimplementation, is the correct approach."""
    cmd = [
        sys.executable,
        str(_REPO_ROOT / "scripts" / "pipeline" / "commands" / "ops" / "optimize_media_assets.py"),
        family, platform, "--apply",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True,
                            encoding="utf-8", errors="replace", cwd=str(_REPO_ROOT))
    if result.returncode not in (0,):
        raise RuntimeError(f"optimize_media_assets.py failed for {family}/{platform}: {result.stdout}\n{result.stderr}")


# -- CLI ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("family", nargs="?", help="Scope to one family (optional)")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--apply", action="store_true")
    parser.add_argument("--backfill-png", action="store_true",
                         help="Also invoke S-119 to generate the .png sibling for each written icon")
    args = parser.parse_args()

    gaps = discover_gaps()
    if args.family:
        gaps = [g for g in gaps if g["family"] == args.family]

    results = []
    for gap in gaps:
        if not gap["is_gap"]:
            results.append({**gap, "status": "SKIP_NOT_A_GAP"})
            continue
        try:
            im = build_icon(gap)
            record = write_icon(gap, im, apply=args.apply)
            if args.apply and args.backfill_png and record["status"] == "WRITTEN":
                backfill_png(gap["family"], gap["platform"])
                record["png_backfilled"] = True
            results.append(record)
        except Exception as exc:  # noqa: BLE001 -- surface per-gap, don't abort the batch
            results.append({**gap, "status": "ERROR", "error": str(exc)})

    print(json.dumps(results, indent=2, default=str))
    if any(r.get("status") == "ERROR" for r in results):
        sys.exit(1)


if __name__ == "__main__":
    main()
