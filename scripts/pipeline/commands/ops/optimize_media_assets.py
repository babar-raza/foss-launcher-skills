"""
optimize_media_assets.py — S-119: Rename static/media product images to a
fixed convention (icon/banner per family/platform directory) and compress
them under a byte-size budget.

Classification is by pixel dimensions only, never by filename:
  - square 1024x1024 or 1254x1254  -> icon
  - landscape 1774x887 (~2:1)      -> banner
Anything else is reported UNCLASSIFIED and left untouched.

Compression tries lossless first, falls back to WebP only if needed. Both
oxipng and Pillow's WebP encoder (linking libwebp 1.6.0, the current release
of Google's reference codec) were chosen by comparing GitHub star count and
maintenance activity against the alternatives -- see skills/media-optimize.md.

  1. oxipng -o max --strip safe (single pass; Zopfli was tried and dropped --
     calibrated empirically at 0-0.7% additional savings for 60-140s/file on
     this image set, not worth the cost). If this alone gets the file under
     budget: keep it as PNG (icon.png/banner.png), pixel-identical to source,
     verified automatically.
  2. If still over budget: re-encode the ORIGINAL as WebP (quality=95,
     method=6, stepping down through 90/85/80 only if needed; never below
     80). This is genuinely lossy. A coarse automated PSNR/SSIM floor catches
     gross encoder failures, but the real quality gate is a mandatory human/
     agent visual review -- PSNR and even approximate SSIM were found to
     correlate poorly with perceived quality on this sharp-edged graphic
     content (a demonstrably fine result measured 21.6dB/0.948). The script
     never self-certifies a lossy result: it stages the new icon.webp /
     banner.webp file and reports NEEDS_VISUAL_REVIEW without deleting the
     original. Run --confirm-reviewed on the reported source paths only
     after visually confirming no perceptible difference.
  3. If WebP at quality 80 still doesn't fit budget: STILL_OVER_BUDGET,
     original left untouched.

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

OXIPNG_VERSION = "10.1.1"
OXIPNG_RELEASE_URL = (
    f"https://github.com/shssoichiro/oxipng/releases/download/"
    f"v{OXIPNG_VERSION}/oxipng-{OXIPNG_VERSION}-x86_64-pc-windows-msvc.zip"
)

WEBP_QUALITY_LADDER = (95, 90, 85, 80)

# ── Configurable defaults (testing seam — see AGENTS.md §16) ────────────────

_cfg_media_root: str = "static/media"
_cfg_oxipng_bin: str | None = None
_cfg_cache_dir: str = "cache/oxipng"
_cfg_max_bytes: int = 1_048_576
_cfg_min_psnr: float = 18.0
_cfg_min_ssim: float = 0.90


def configure(
    media_root: str | None = None,
    oxipng_bin: str | None = None,
    cache_dir: str | None = None,
    max_bytes: int | None = None,
    min_psnr: float | None = None,
    min_ssim: float | None = None,
) -> None:
    """Override module-level path/behavior constants for testing."""
    global _cfg_media_root, _cfg_oxipng_bin, _cfg_cache_dir, _cfg_max_bytes
    global _cfg_min_psnr, _cfg_min_ssim
    if media_root is not None:
        _cfg_media_root = media_root
    if oxipng_bin is not None:
        _cfg_oxipng_bin = oxipng_bin
    if cache_dir is not None:
        _cfg_cache_dir = cache_dir
    if max_bytes is not None:
        _cfg_max_bytes = max_bytes
    if min_psnr is not None:
        _cfg_min_psnr = min_psnr
    if min_ssim is not None:
        _cfg_min_ssim = min_ssim


# ── Classification ───────────────────────────────────────────────────────────

def classify(width: int, height: int) -> str | None:
    """Return 'icon', 'banner', or None (unclassified) for these dimensions."""
    if (width, height) in ICON_DIMENSIONS:
        return "icon"
    if (width, height) in BANNER_DIMENSIONS:
        return "banner"
    return None


def target_candidates(source: Path, shape: str) -> tuple[Path, Path]:
    """Return (png_path, webp_path) -- the two possible destinations for this
    slot. Same directory, generic name -- the directory already encodes
    family/platform."""
    base = "icon" if shape == "icon" else "banner"
    return source.parent / f"{base}.png", source.parent / f"{base}.webp"


def existing_target_conflict(source: Path, png_path: Path, webp_path: Path) -> Path | None:
    """Return the conflicting path if either candidate target already exists
    with different pixel content than source, else None."""
    for candidate in (png_path, webp_path):
        if candidate.exists() and candidate != source:
            if not pixels_identical(source, candidate):
                return candidate
    return None


# ── oxipng resolution ────────────────────────────────────────────────────────

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
    """Single-pass max-effort lossless recompression + safe metadata strip.
    Deliberately no Zopfli backend (-z) -- calibrated on this image set to
    add 0-0.7% for 60-140s/file, not worth the cost (see skills/media-optimize.md)."""
    cmd = [oxipng_bin, "-o", "max", "--strip", "safe", str(path)]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"oxipng failed on {path}: {result.stderr}")


# ── Verification ─────────────────────────────────────────────────────────────

def pixels_identical(path_a: Path, path_b: Path) -> bool:
    """True iff both files decode to the exact same dimensions and pixel data."""
    with Image.open(path_a) as img_a, Image.open(path_b) as img_b:
        if img_a.size != img_b.size:
            return False
        return img_a.convert("RGBA").tobytes() == img_b.convert("RGBA").tobytes()


def psnr(img_a: Image.Image, img_b: Image.Image) -> float:
    """Peak signal-to-noise ratio in dB between two images (RGB comparison).

    NOTE: found (empirically, see skills/media-optimize.md) to correlate
    poorly with perceived quality on sharp-edged graphic-design content --
    used only as a coarse floor to catch gross encoder failures, never as
    the sole quality gate.
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


def meets_quality_floor(orig: Image.Image, candidate: Image.Image) -> bool:
    return psnr(orig, candidate) >= _cfg_min_psnr and global_ssim(orig, candidate) >= _cfg_min_ssim


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

    png_path, webp_path = target_candidates(source, shape)
    conflict = existing_target_conflict(source, png_path, webp_path)
    if conflict is not None:
        record["status"] = "BLOCKED"
        record["target"] = str(conflict)
        return record

    if not apply:
        record["status"] = "PLANNED"
        record["target"] = str(png_path)
        return record

    # --- Attempt 1: lossless PNG ---
    tmp_png = png_path.parent / f"__optimize_tmp__{png_path.name}"
    try:
        shutil.copy2(source, tmp_png)
        run_oxipng(oxipng_bin, tmp_png)
        if not pixels_identical(source, tmp_png):
            raise RuntimeError(f"oxipng changed pixel data for {source}")
        size_after = tmp_png.stat().st_size
        if size_after < _cfg_max_bytes:
            shutil.move(str(tmp_png), str(png_path))
            if webp_path.exists() and webp_path != source:
                webp_path.unlink()
            if source != png_path and source.exists():
                source.unlink()
            record.update(status="OK", method="lossless-png", target=str(png_path), size_after=size_after)
            return record
    finally:
        if tmp_png.exists():
            tmp_png.unlink()

    # --- Attempt 2: WebP fallback (lossy; requires visual review before the
    #     original is deleted -- see confirm_reviewed()) ---
    with Image.open(source) as orig_img:
        orig_img.load()
        for quality in WEBP_QUALITY_LADDER:
            tmp_webp = webp_path.parent / f"__optimize_tmp__{webp_path.name}"
            try:
                orig_img.save(tmp_webp, "WEBP", quality=quality, method=6)
                size_after = tmp_webp.stat().st_size
                if size_after >= _cfg_max_bytes:
                    continue
                with Image.open(tmp_webp) as candidate_img:
                    p = psnr(orig_img, candidate_img)
                    s = global_ssim(orig_img, candidate_img)
                if p < _cfg_min_psnr or s < _cfg_min_ssim:
                    continue
                shutil.move(str(tmp_webp), str(webp_path))
            finally:
                if tmp_webp.exists():
                    tmp_webp.unlink()
            if png_path.exists() and png_path != source:
                png_path.unlink()
            record.update(
                status="NEEDS_VISUAL_REVIEW",
                method="webp",
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
    original. Never called automatically by process_file()."""
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
        _, webp_path = target_candidates(source, shape)
        if not webp_path.exists() or webp_path == source:
            results.append({"source": p, "status": "NO_TARGET_FOUND"})
            continue
        source.unlink()
        results.append({"source": p, "status": "DELETED", "target": str(webp_path)})
    return results


def run(family: str | None, platform_name: str | None, apply: bool) -> list[dict]:
    media_root = Path(_cfg_media_root)
    files = discover(media_root, family, platform_name)
    oxipng_bin = resolve_oxipng() if apply else (_cfg_oxipng_bin or "oxipng")
    results = []
    for f in files:
        if f.stem in ("icon", "banner") and f.suffix.lower() in (".png", ".webp") and f.stat().st_size < _cfg_max_bytes:
            results.append({"source": str(f), "status": "SKIP_ALREADY_DONE"})
            continue
        results.append(process_file(f, oxipng_bin, apply))
    return results


# ── CLI ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "optimize_media_assets — S-119: rename static/media product images "
            "to a fixed convention and compress them under 1MB."
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

    if any(r["status"] in ("STILL_OVER_BUDGET", "BLOCKED", "UNCLASSIFIED") for r in results):
        sys.exit(1)


if __name__ == "__main__":
    main()
