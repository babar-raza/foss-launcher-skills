"""
optimize_media_assets.py — S-119: Rename static/media product images to a
fixed convention (icon.webp/banner.webp per family/platform directory) and
compress them under a byte-size budget with WebP.

Classification is by pixel dimensions only, never by filename:
  - square 1024x1024 or 1254x1254  -> icon
  - landscape 1774x887 (~2:1)      -> banner
Anything else is reported UNCLASSIFIED and left untouched.

WebP is the only target format (operator decision, 2026-08-06): lossless PNG
recompression was tried first and dropped -- calibrated empirically at only
9-13% savings on this image set, nowhere near enough from ~1.3-1.7MB
originals to reach 1MB. Pillow's WebP encoder (linking libwebp 1.6.0, the
current release of Google's reference codec -- chosen the same way oxipng
was, by comparing GitHub star count and maintenance activity, see
skills/media-optimize.md) preserves alpha transparency by default -- verified
by round-tripping a real icon (has_transparency_data=True, alpha extrema and
a fully-transparent corner pixel matched exactly before/after).

Quality ladder: 95, stepping down through 90/85/80 only if still over budget
(size is the only automated acceptance criterion); never below 80. This is
genuinely lossy. PSNR/SSIM are computed and reported alongside each result
for context, but do NOT gate acceptance -- both were found, empirically and
twice, to swing across too wide and unpredictable a range on this
sharp-edged, mostly-flat-color content to serve as a rejection threshold
(two independently confirmed visually-perfect results measured 21.6dB/0.948
and 14.8dB/0.770 -- using either as a floor produced false rejections of
genuinely fine images). The script never self-certifies a lossy result: it
stages the new icon.webp/banner.webp file and reports NEEDS_VISUAL_REVIEW
without deleting the original. Run --confirm-reviewed on the reported source
paths only after visually confirming no perceptible difference.

If WebP at quality 80 still doesn't fit budget: STILL_OVER_BUDGET, original
left untouched.

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
import math

from PIL import Image, ImageChops, ImageStat

# ── Constants ────────────────────────────────────────────────────────────────

ICON_DIMENSIONS = frozenset({(1024, 1024), (1254, 1254)})
BANNER_DIMENSIONS = frozenset({(1774, 887)})

WEBP_QUALITY_LADDER = (95, 90, 85, 80)

# ── Configurable defaults (testing seam — see AGENTS.md §16) ────────────────

_cfg_media_root: str = "static/media"
_cfg_max_bytes: int = 1_048_576


def configure(
    media_root: str | None = None,
    max_bytes: int | None = None,
) -> None:
    """Override module-level path/behavior constants for testing."""
    global _cfg_media_root, _cfg_max_bytes
    if media_root is not None:
        _cfg_media_root = media_root
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


def target_path(source: Path, shape: str) -> Path:
    """Compute the destination path for a classified file: same directory,
    generic name, always .webp -- the directory already encodes
    family/platform, and WebP is the only target format."""
    base = "icon" if shape == "icon" else "banner"
    return source.parent / f"{base}.webp"


# ── Verification ─────────────────────────────────────────────────────────────

def psnr(img_a: Image.Image, img_b: Image.Image) -> float:
    """Peak signal-to-noise ratio in dB between two images (RGB comparison).

    NOTE: found (empirically, see skills/media-optimize.md) to correlate
    poorly with perceived quality on sharp-edged graphic-design content --
    reported alongside each result for context only, never used to gate
    acceptance.
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
    """Whole-image (non-windowed) SSIM approximation, Pillow-only (no numpy/
    scikit-image dependency). Same correlation caveat as psnr() above."""
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
    return sorted(p for p in base.rglob("*") if p.suffix.lower() in (".png", ".webp") and p.is_file())


# ── Core processing ──────────────────────────────────────────────────────────

def process_file(source: Path, apply: bool) -> dict:
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

    webp_path = target_path(source, shape)
    if webp_path.exists() and webp_path != source:
        # WebP is lossy, so a source can never be pixel-identical to its own
        # already-converted target -- pixel comparison can't distinguish
        # "this IS that source's prior output, just awaiting confirm_reviewed"
        # from "a genuinely different file wants this slot". Either way the
        # safe move is the same: don't touch either file, surface it for a
        # human decision (confirm_reviewed for the expected case; manual
        # investigation if this is a real, unexpected duplicate).
        record["status"] = "PENDING_REVIEW"
        record["target"] = str(webp_path)
        return record

    if not apply:
        record["status"] = "PLANNED"
        record["target"] = str(webp_path)
        return record

    with Image.open(source) as orig_img:
        orig_img.load()
        for quality in WEBP_QUALITY_LADDER:
            tmp_webp = webp_path.parent / f"__optimize_tmp__{webp_path.name}"
            try:
                orig_img.save(tmp_webp, "WEBP", quality=quality, method=6)
                size_after = tmp_webp.stat().st_size
                if size_after >= _cfg_max_bytes:
                    continue
                # PSNR/SSIM are computed and reported for the record, but do
                # NOT gate acceptance here -- both were found (empirically,
                # twice: 21.6dB/0.948 and 14.8dB/0.770, on two independently
                # confirmed visually-perfect results) to swing across too
                # wide and unpredictable a range for this sharp-edged,
                # mostly-flat-color content to serve as a rejection
                # threshold. Using either as a gate produced false rejections
                # of genuinely fine images. The real gate is the mandatory
                # human/agent visual review before --confirm-reviewed.
                with Image.open(tmp_webp) as candidate_img:
                    p = psnr(orig_img, candidate_img)
                    s = global_ssim(orig_img, candidate_img)
                # source == webp_path is possible (already-named file that's
                # merely oversized): the move below overwrites it in place.
                # orig_img was fully loaded into memory above, independent of
                # the on-disk file, so this is safe either way.
                tmp_webp.replace(webp_path)
            finally:
                if tmp_webp.exists():
                    tmp_webp.unlink()
            record.update(
                status="NEEDS_VISUAL_REVIEW",
                quality=quality,
                target=str(webp_path),
                size_after=size_after,
                psnr=round(p, 1),
                ssim=round(s, 3),
            )
            return record

    record["status"] = "STILL_OVER_BUDGET"
    return record


def confirm_reviewed(paths: list[str]) -> list[dict]:
    """After a human/agent has visually compared a NEEDS_VISUAL_REVIEW file's
    before/after pair and found no perceptible difference, delete the
    original (unless the WebP replacement was written in place under the
    same path, in which case there's nothing left to delete). Never called
    automatically by process_file()."""
    results = []
    for p in paths:
        source = Path(p)
        if not source.exists():
            results.append({"source": p, "status": "ALREADY_GONE"})
            continue
        with Image.open(source) as img:
            shape = classify(*img.size)
        if shape is None:
            results.append({"source": p, "status": "UNCLASSIFIED"})
            continue
        webp_path = target_path(source, shape)
        if webp_path == source:
            results.append({"source": p, "status": "ALREADY_FINALIZED"})
            continue
        if not webp_path.exists():
            results.append({"source": p, "status": "NO_TARGET_FOUND"})
            continue
        source.unlink()
        results.append({"source": p, "status": "DELETED", "target": str(webp_path)})
    return results


def run(family: str | None, platform_name: str | None, apply: bool) -> list[dict]:
    media_root = Path(_cfg_media_root)
    files = discover(media_root, family, platform_name)
    results = []
    for f in files:
        if f.stem in ("icon", "banner") and f.suffix.lower() == ".webp" and f.stat().st_size < _cfg_max_bytes:
            results.append({"source": str(f), "status": "SKIP_ALREADY_DONE"})
            continue
        results.append(process_file(f, apply))
    return results


# ── CLI ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "optimize_media_assets — S-119: rename static/media product images "
            "to a fixed convention and compress them under 1MB with WebP."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  .venv/Scripts/python scripts/pipeline/commands/ops/optimize_media_assets.py --dry-run
  .venv/Scripts/python scripts/pipeline/commands/ops/optimize_media_assets.py pdf python --apply
  .venv/Scripts/python scripts/pipeline/commands/ops/optimize_media_assets.py --confirm-reviewed static/media/pdf/icon-old.png
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
        help="Delete original files after manual visual review of their WebP replacement",
    )
    args = parser.parse_args()

    if args.confirm_reviewed:
        results = confirm_reviewed(args.confirm_reviewed)
        for r in results:
            print(f"  [{r['status']}] {r['source']}" + (f" -> {r['target']}" if "target" in r else ""))
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
        line = f"  [{r['status']}] {r['source']}"
        if "target" in r:
            line += f" -> {r['target']}"
        if "size_before" in r:
            line += f"  ({r['size_before']} bytes"
            if "size_after" in r:
                line += f" -> {r['size_after']} bytes"
            line += ")"
        if "psnr" in r:
            line += f"  [psnr={r['psnr']}dB ssim={r['ssim']} q={r['quality']}]"
        print(line)

    if any(r["status"] in ("STILL_OVER_BUDGET", "PENDING_REVIEW", "UNCLASSIFIED") for r in results):
        sys.exit(1)


if __name__ == "__main__":
    main()
