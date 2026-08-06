"""
optimize_media_assets.py — S-119: Ensure every static/media product icon/banner
slot has BOTH a WebP and a PNG artifact, each under a byte-size budget.

Dual-format policy (operator decision, 2026-08-06): WebP gives the best
compression for modern consumers; PNG gives maximum, uncontroversial
compatibility (some Open Graph/social-preview crawlers and older tooling
still don't reliably render WebP link previews -- see skills/media-optimize.md
for the full research trail). Rather than picking one, both are produced and
a future template/`<picture>` element can choose.

Classification is by pixel dimensions only, never by filename:
  - square 1024x1024 or 1254x1254  -> icon
  - landscape 1774x887 (~2:1)      -> banner
Anything else is reported UNCLASSIFIED and left untouched.

Unit of work is a SLOT (a directory + shape), not a file: a slot is complete
when both `{name}.png` and `{name}.webp` exist under budget. For each
classified source found:
  - If the source is already one of the two canonical names (icon.png,
    icon.webp, banner.png, banner.webp) -- true for all 72 files as of
    2026-08-06 -- it is NEVER modified or deleted. Only its missing sibling
    is generated from its decoded pixels.
  - If the source is a raw/temp upload (some other filename), BOTH targets
    are generated from it, and the original is deleted only via
    --confirm-reviewed once both derivatives are confirmed acceptable.

Per-format technique (each independently validated against the real corpus,
see skills/media-optimize.md):
  - WebP: quality ladder 95/90/85/80, method 6. Size is the sole automated
    acceptance criterion -- PSNR/SSIM are computed and reported for context
    only (found to swing 14.8-21.6dB on independently confirmed
    visually-perfect results, too unreliable to gate on).
  - PNG: lossless attempt first (rarely fits this content, costs little to
    try), then a palette-quantization ladder (256/192/128/96/64 colors,
    Floyd-Steinberg dithered, alpha quantized and reattached separately from
    RGB so transparency stays exact), then `oxipng -o max --strip safe`
    polish. A literal WebP-decode-then-PNG-reencode round trip was tested
    against all 72 real files and REJECTED -- it left 2 files over budget
    and several within 1-6% of the cap, because re-encoding truecolor PNG
    doesn't change color *mode*, so the file still balloons 2.5-4x versus
    the WebP regardless of the source path. Palette quantization is the
    PNG-native fix for that, not a round trip through an unrelated codec.

A non-alpha source (e.g. a future JPG drop) intended as an icon gets
background-color transparency extraction attempted first (see
extract_transparency()) -- a heuristic, flagged with a distinct review
status rather than trusted silently.

Every generated file is staged as NEEDS_VISUAL_REVIEW (or
TRANSPARENCY_EXTRACTED_NEEDS_REVIEW for the heuristic path) without deleting
anything; a human/agent must visually compare before/after and run
--confirm-reviewed. The script never self-certifies a lossy result.

CLI:
    .venv/Scripts/python scripts/pipeline/commands/ops/optimize_media_assets.py --dry-run
    .venv/Scripts/python scripts/pipeline/commands/ops/optimize_media_assets.py pdf python --apply
    .venv/Scripts/python scripts/pipeline/commands/ops/optimize_media_assets.py --confirm-reviewed PATH [PATH ...]
"""

from pathlib import Path
import sys

_PIPELINE_ROOT = Path(__file__).resolve().parents[2]
if str(_PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_ROOT))
_LIB_DIR = str(_PIPELINE_ROOT / "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)

import argparse
import io
import math
import shutil
import subprocess
import urllib.request
import zipfile

from PIL import Image, ImageChops, ImageStat

# ── Constants ────────────────────────────────────────────────────────────────

ICON_DIMENSIONS = frozenset({(1024, 1024), (1254, 1254)})
BANNER_DIMENSIONS = frozenset({(1774, 887)})

SOURCE_EXTENSIONS = (".png", ".webp", ".jpg", ".jpeg")

WEBP_QUALITY_LADDER = (95, 90, 85, 80)
PNG_COLOR_LADDER = (256, 192, 128, 96, 64)

OXIPNG_VERSION = "10.1.1"
OXIPNG_RELEASE_URL = (
    f"https://github.com/shssoichiro/oxipng/releases/download/"
    f"v{OXIPNG_VERSION}/oxipng-{OXIPNG_VERSION}-x86_64-pc-windows-msvc.zip"
)

# ── Configurable defaults (testing seam — see AGENTS.md §16) ────────────────

_cfg_media_root: str = "static/media"
_cfg_oxipng_bin: str | None = None
_cfg_cache_dir: str = "cache/oxipng"
_cfg_max_bytes: int = 1_048_576


def configure(
    media_root: str | None = None,
    oxipng_bin: str | None = None,
    cache_dir: str | None = None,
    max_bytes: int | None = None,
) -> None:
    """Override module-level path/behavior constants for testing."""
    global _cfg_media_root, _cfg_oxipng_bin, _cfg_cache_dir, _cfg_max_bytes
    if media_root is not None:
        _cfg_media_root = media_root
    if oxipng_bin is not None:
        _cfg_oxipng_bin = oxipng_bin
    if cache_dir is not None:
        _cfg_cache_dir = cache_dir
    if max_bytes is not None:
        _cfg_max_bytes = max_bytes


# ── Classification ───────────────────────────────────────────────────────────

def classify(width: int, height: int) -> str | None:
    """Return 'icon', 'banner', or None (unclassified) for these dimensions."""
    if (width, height) in ICON_DIMENSIONS:
        return "icon"
    if (width, height) in BANNER_DIMENSIONS:
        return "banner"
    return None


def target_paths(source: Path, shape: str) -> tuple[Path, Path]:
    """Return (png_path, webp_path) -- both canonical artifacts for this slot.
    Same directory, generic name -- the directory already encodes
    family/platform."""
    base = "icon" if shape == "icon" else "banner"
    return source.parent / f"{base}.png", source.parent / f"{base}.webp"


def is_canonical(path: Path) -> bool:
    """True if path is already one of the two final artifact names for some
    slot -- such a file is a keeper, never modified or deleted."""
    return path.stem in ("icon", "banner") and path.suffix.lower() in (".png", ".webp")


# ── oxipng resolution (PNG lossless attempt + polish pass) ──────────────────

def resolve_oxipng() -> str:
    """Return a path to a runnable oxipng binary, downloading it if needed."""
    if _cfg_oxipng_bin is not None:
        return _cfg_oxipng_bin
    on_path = shutil.which("oxipng")
    if on_path:
        return on_path

    cache_dir = Path(_cfg_cache_dir)
    exe_path = cache_dir / f"oxipng-{OXIPNG_VERSION}-x86_64-pc-windows-msvc" / "oxipng.exe"
    if exe_path.exists():
        return str(exe_path)

    cache_dir.mkdir(parents=True, exist_ok=True)
    print(f"Downloading oxipng {OXIPNG_VERSION} from {OXIPNG_RELEASE_URL} ...")
    with urllib.request.urlopen(OXIPNG_RELEASE_URL) as resp:
        data = resp.read()
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        zf.extractall(cache_dir)
    if not exe_path.exists():
        raise RuntimeError(f"oxipng download did not produce expected binary at {exe_path}")
    print(f"oxipng downloaded to {exe_path}")
    return str(exe_path)


def run_oxipng(oxipng_bin: str, path: Path) -> None:
    """Single-pass max-effort lossless recompression + safe metadata strip."""
    cmd = [oxipng_bin, "-o", "max", "--strip", "safe", str(path)]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"oxipng failed on {path}: {result.stderr}")


# ── Verification (informational only — do not gate acceptance) ─────────────

def psnr(img_a: Image.Image, img_b: Image.Image) -> float:
    """Peak signal-to-noise ratio in dB (RGB comparison).

    NOTE: found empirically (see skills/media-optimize.md) to correlate
    poorly with perceived quality on this sharp-edged graphic content --
    reported for context only, never used to gate acceptance.
    """
    a = img_a.convert("RGB")
    b = img_b.convert("RGB")
    diff = ImageChops.difference(a, b)
    hist = diff.histogram()
    n = a.size[0] * a.size[1] * 3
    sq_sum = 0
    for ch in range(3):
        for i, count in enumerate(hist[ch * 256:(ch + 1) * 256]):
            sq_sum += (i * i) * count
    mse = sq_sum / n
    if mse == 0:
        return float("inf")
    return 10 * math.log10((255.0 ** 2) / mse)


def global_ssim(img_a: Image.Image, img_b: Image.Image, resize_to: int = 256) -> float:
    """Whole-image (non-windowed) SSIM approximation, Pillow-only. Same
    correlation caveat as psnr() above."""
    a = img_a.convert("L").resize((resize_to, resize_to))
    b = img_b.convert("L").resize((resize_to, resize_to))
    stat_a, stat_b = ImageStat.Stat(a), ImageStat.Stat(b)
    mu_a, mu_b = stat_a.mean[0], stat_b.mean[0]
    var_a, var_b = stat_a.var[0], stat_b.var[0]
    data_a = list(a.getdata())
    data_b = list(b.getdata())
    n = len(data_a)
    cov = sum((data_a[i] - mu_a) * (data_b[i] - mu_b) for i in range(n)) / n
    c1, c2 = (0.01 * 255) ** 2, (0.03 * 255) ** 2
    return ((2 * mu_a * mu_b + c1) * (2 * cov + c2)) / ((mu_a ** 2 + mu_b ** 2 + c1) * (var_a + var_b + c2))


# ── PNG quantization ─────────────────────────────────────────────────────────

def quantize_preserving_alpha(img: Image.Image, colors: int) -> Image.Image:
    """Palette-quantize RGB; quantize/reattach alpha separately so
    transparency stays exact rather than being posterized into the palette."""
    if img.mode == "RGBA":
        alpha = img.getchannel("A")
        rgb = img.convert("RGB")
        q = rgb.quantize(colors=colors, method=Image.MEDIANCUT, dither=Image.FLOYDSTEINBERG)
        q = q.convert("RGBA")
        q.putalpha(alpha)
        return q
    return img.convert("RGB").quantize(colors=colors, method=Image.MEDIANCUT, dither=Image.FLOYDSTEINBERG)


# ── Transparency extraction for non-alpha sources (untested against real
#    data as of 2026-08-06 -- no current source needs it) ──────────────────

def detect_background_color(img: Image.Image, border: int = 4) -> tuple[float, float, float] | None:
    """Sample a border strip; return the background RGB if it's uniform and
    close to pure black or pure white, else None -- never guess on an
    ambiguous (e.g. photographic) background."""
    rgb = img.convert("RGB")
    w, h = rgb.size
    pixels = []
    for x in range(w):
        for y in range(border):
            pixels.append(rgb.getpixel((x, y)))
            pixels.append(rgb.getpixel((x, h - 1 - y)))
    for y in range(h):
        for x in range(border):
            pixels.append(rgb.getpixel((x, y)))
            pixels.append(rgb.getpixel((w - 1 - x, y)))
    n = len(pixels)
    mean = tuple(sum(p[c] for p in pixels) / n for c in range(3))
    variance = sum(sum((p[c] - mean[c]) ** 2 for c in range(3)) for p in pixels) / n
    if variance > 100:
        return None
    avg = sum(mean) / 3
    if avg < 10 or avg > 245:
        return mean
    return None


def extract_transparency(img: Image.Image) -> Image.Image | None:
    """Return an RGBA version with a background-color-keyed alpha channel, or
    None if the background wasn't confidently detectable (caller should then
    proceed without alpha and flag for manual review)."""
    bg = detect_background_color(img)
    if bg is None:
        return None
    rgb = img.convert("RGB")
    inner, outer = 12, 40
    alpha_data = []
    for pixel in rgb.getdata():
        dist = math.sqrt(sum((pixel[c] - bg[c]) ** 2 for c in range(3)))
        if dist <= inner:
            alpha_data.append(0)
        elif dist >= outer:
            alpha_data.append(255)
        else:
            alpha_data.append(round((dist - inner) / (outer - inner) * 255))
    result = rgb.convert("RGBA")
    alpha_img = Image.new("L", rgb.size)
    alpha_img.putdata(alpha_data)
    result.putalpha(alpha_img)
    return result


# ── Discovery ────────────────────────────────────────────────────────────────

def discover(media_root: Path, family: str | None, platform_name: str | None) -> list[Path]:
    if family and platform_name:
        base = media_root / family / platform_name
    elif family:
        base = media_root / family
    else:
        base = media_root
    if not base.exists():
        return []
    return sorted(
        p for p in base.rglob("*")
        if p.suffix.lower() in SOURCE_EXTENSIONS and p.is_file()
    )


# ── Per-format generation ────────────────────────────────────────────────────

def generate_webp(orig_img: Image.Image, dest: Path) -> dict:
    for quality in WEBP_QUALITY_LADDER:
        tmp = dest.parent / f"__optimize_tmp__{dest.name}"
        try:
            orig_img.save(tmp, "WEBP", quality=quality, method=6)
            size = tmp.stat().st_size
            if size >= _cfg_max_bytes:
                continue
            with Image.open(tmp) as candidate:
                p, s = psnr(orig_img, candidate), global_ssim(orig_img, candidate)
            tmp.replace(dest)
        finally:
            if tmp.exists():
                tmp.unlink()
        return {
            "status": "NEEDS_VISUAL_REVIEW", "format": "webp", "quality": quality,
            "size_after": size, "psnr": round(p, 1), "ssim": round(s, 3),
        }
    return {"status": "STILL_OVER_BUDGET", "format": "webp"}


def generate_png(orig_img: Image.Image, dest: Path, oxipng_bin: str) -> dict:
    # Attempt 1: lossless (rarely fits this content, costs little to try).
    tmp = dest.parent / f"__optimize_tmp__{dest.name}"
    try:
        orig_img.save(tmp, "PNG", optimize=True)
        run_oxipng(oxipng_bin, tmp)
        with Image.open(tmp) as candidate:
            lossless_ok = (
                candidate.size == orig_img.size
                and candidate.convert("RGBA").tobytes() == orig_img.convert("RGBA").tobytes()
            )
        if lossless_ok:
            size = tmp.stat().st_size
            if size < _cfg_max_bytes:
                tmp.replace(dest)
                return {"status": "OK", "format": "png", "method": "lossless", "size_after": size}
    finally:
        if tmp.exists():
            tmp.unlink()

    # Attempt 2: palette-quantization ladder.
    for colors in PNG_COLOR_LADDER:
        tmp = dest.parent / f"__optimize_tmp__{dest.name}"
        try:
            quantized = quantize_preserving_alpha(orig_img, colors)
            quantized.save(tmp, "PNG", optimize=True)
            run_oxipng(oxipng_bin, tmp)
            size = tmp.stat().st_size
            if size >= _cfg_max_bytes:
                continue
            with Image.open(tmp) as candidate:
                p, s = psnr(orig_img, candidate), global_ssim(orig_img, candidate)
            tmp.replace(dest)
        finally:
            if tmp.exists():
                tmp.unlink()
        return {
            "status": "NEEDS_VISUAL_REVIEW", "format": "png", "colors": colors,
            "size_after": size, "psnr": round(p, 1), "ssim": round(s, 3),
        }
    return {"status": "STILL_OVER_BUDGET", "format": "png"}


def _generate_for_target(orig_img: Image.Image, target: Path, oxipng_bin: str) -> dict:
    if target.suffix.lower() == ".webp":
        return generate_webp(orig_img, target)
    return generate_png(orig_img, target, oxipng_bin)


# ── Core processing ──────────────────────────────────────────────────────────

def process_file(source: Path, oxipng_bin: str, apply: bool) -> dict:
    with Image.open(source) as img:
        width, height = img.size

    shape = classify(width, height)
    record: dict = {
        "source": str(source),
        "shape": shape,
        "size_before": source.stat().st_size,
    }

    if shape is None:
        record["status"] = "UNCLASSIFIED"
        return record

    png_target, webp_target = target_paths(source, shape)

    if source in (png_target, webp_target):
        # source IS one of the two final artifacts already -- never touch or
        # delete it. Only its missing sibling (if any) gets generated.
        other = webp_target if source == png_target else png_target
        if other.exists() and other.stat().st_size < _cfg_max_bytes:
            record["status"] = "SKIP_ALREADY_DONE"
            return record

        if not apply:
            record["status"] = "PLANNED"
            record["target"] = str(other)
            return record

        with Image.open(source) as orig_img:
            orig_img.load()
            result = _generate_for_target(orig_img, other, oxipng_bin)
        record.update(result)
        record["target"] = str(other)
        return record

    # source is a raw/temp upload -- both targets may need generating.
    # WebP is never pixel-identical to its own lossy output, so an existing
    # target here (from a different source than the one we're looking at)
    # can't be told apart from "this raw upload's own not-yet-confirmed
    # prior output" by pixel comparison -- surface it, don't guess (see
    # skills/media-optimize.md's PENDING_REVIEW rationale).
    conflicts = [t for t in (png_target, webp_target) if t.exists()]
    if conflicts:
        record["status"] = "PENDING_REVIEW"
        record["target"] = str(conflicts[0])
        return record

    if not apply:
        record["status"] = "PLANNED"
        record["targets"] = [str(png_target), str(webp_target)]
        return record

    with Image.open(source) as orig_img:
        orig_img.load()
        transparency_extracted = False
        if orig_img.mode != "RGBA" and shape == "icon":
            extracted = extract_transparency(orig_img)
            if extracted is not None:
                orig_img = extracted
                transparency_extracted = True

        png_result = generate_png(orig_img, png_target, oxipng_bin)
        webp_result = generate_webp(orig_img, webp_target)

    record["png"] = png_result
    record["webp"] = webp_result
    both_ok = png_result["status"] in ("OK", "NEEDS_VISUAL_REVIEW") and \
        webp_result["status"] in ("OK", "NEEDS_VISUAL_REVIEW")
    if not both_ok:
        record["status"] = "STILL_OVER_BUDGET"
    elif transparency_extracted:
        record["status"] = "TRANSPARENCY_EXTRACTED_NEEDS_REVIEW"
    else:
        record["status"] = "NEEDS_VISUAL_REVIEW"
    return record


def confirm_reviewed(paths: list[str]) -> list[dict]:
    """After a human/agent has visually compared a NEEDS_VISUAL_REVIEW (or
    TRANSPARENCY_EXTRACTED_NEEDS_REVIEW) result and found it acceptable,
    delete the raw source now that both derivatives exist -- unless the
    source is itself a canonical artifact (icon.png/icon.webp/etc.), in
    which case there is nothing to delete; it was never going anywhere.
    Never called automatically by process_file()."""
    results = []
    for p in paths:
        source = Path(p)
        if not source.exists():
            results.append({"source": p, "status": "ALREADY_GONE"})
            continue
        if is_canonical(source):
            results.append({"source": p, "status": "ALREADY_FINALIZED"})
            continue
        with Image.open(source) as img:
            shape = classify(*img.size)
        if shape is None:
            results.append({"source": p, "status": "UNCLASSIFIED"})
            continue
        png_target, webp_target = target_paths(source, shape)
        missing = [t for t in (png_target, webp_target) if not t.exists()]
        if missing:
            results.append({"source": p, "status": "NO_TARGET_FOUND", "missing": [str(m) for m in missing]})
            continue
        source.unlink()
        results.append({"source": p, "status": "DELETED", "targets": [str(png_target), str(webp_target)]})
    return results


def run(family: str | None, platform_name: str | None, apply: bool) -> list[dict]:
    media_root = Path(_cfg_media_root)
    files = discover(media_root, family, platform_name)
    oxipng_bin = resolve_oxipng() if apply else (_cfg_oxipng_bin or "oxipng")
    return [process_file(f, oxipng_bin, apply) for f in files]


# ── CLI ──────────────────────────────────────────────────────────────────────

def _format_result_line(r: dict) -> str:
    line = f"  [{r['status']}] {r['source']}"
    if "target" in r:
        line += f" -> {r['target']}"
    elif "targets" in r:
        line += f" -> {', '.join(r['targets'])}"
    if "size_before" in r:
        line += f"  ({r['size_before']} bytes"
        if "size_after" in r:
            line += f" -> {r['size_after']} bytes"
        line += ")"
    if "psnr" in r:
        extra = f"q={r['quality']}" if "quality" in r else f"colors={r['colors']}"
        line += f"  [{r['format']} {extra} psnr={r['psnr']}dB ssim={r['ssim']}]"
    for sub_key in ("png", "webp"):
        if sub_key in r:
            sub = r[sub_key]
            line += f"\n      {sub_key}: [{sub['status']}]"
            if "size_after" in sub:
                line += f" {sub['size_after']} bytes"
    return line


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "optimize_media_assets — S-119: ensure every static/media icon/banner "
            "slot has both a .webp and a .png artifact, each under 1MB."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  .venv/Scripts/python scripts/pipeline/commands/ops/optimize_media_assets.py --dry-run
  .venv/Scripts/python scripts/pipeline/commands/ops/optimize_media_assets.py pdf python --apply
  .venv/Scripts/python scripts/pipeline/commands/ops/optimize_media_assets.py --confirm-reviewed static/media/pdf/uuid-upload.png
        """,
    )
    parser.add_argument("family", nargs="?", help="Product family (optional scope)")
    parser.add_argument("platform", nargs="?", help="Platform (optional scope, requires family)")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="Print the plan; touch nothing")
    mode.add_argument("--apply", action="store_true", help="Perform the rename + compression")
    mode.add_argument(
        "--confirm-reviewed",
        nargs="+",
        metavar="PATH",
        help="Delete raw-upload sources after manual visual review of their derivatives",
    )
    args = parser.parse_args()

    if args.confirm_reviewed:
        results = confirm_reviewed(args.confirm_reviewed)
        for r in results:
            extra = f" -> {', '.join(r['targets'])}" if "targets" in r else ""
            print(f"  [{r['status']}] {r['source']}{extra}")
        return

    results = run(args.family, args.platform, apply=args.apply)

    counts: dict[str, int] = {}
    for r in results:
        counts[r["status"]] = counts.get(r["status"], 0) + 1

    print(f"optimize_media_assets: {len(results)} file(s) in scope")
    for status, count in sorted(counts.items()):
        print(f"  {status}: {count}")
    print()
    for r in results:
        if r["status"] == "SKIP_ALREADY_DONE":
            continue
        print(_format_result_line(r))

    if any(r["status"] in ("STILL_OVER_BUDGET", "PENDING_REVIEW", "UNCLASSIFIED") for r in results):
        sys.exit(1)


if __name__ == "__main__":
    main()
