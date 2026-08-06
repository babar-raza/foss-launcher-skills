"""
optimize_media_assets.py — S-119: Rename static/media product images to a
fixed convention (icon.png / banner.png per family/platform directory) and
losslessly compress them under a byte-size budget using the official oxipng
CLI (downloaded on demand from its GitHub release if not already on PATH).

Classification is by pixel dimensions only, never by filename:
  - square 1024x1024 or 1254x1254  -> icon.png
  - landscape 1774x887 (~2:1)      -> banner.png
Anything else is reported UNCLASSIFIED and left untouched.

Compression is two-pass, both genuinely lossless (oxipng re-optimizes DEFLATE
encoding and filter selection only, never pixel data):
  1. oxipng -o max --strip safe
  2. oxipng -o max -z --strip safe   (Zopfli backend, only if still over budget)

Every write is verified pixel-identical to its source before the original is
replaced. A file still over budget after both passes is reported
STILL_OVER_BUDGET and left under its original name -- never silently
compressed lossily.

CLI:
    .venv/Scripts/python scripts/pipeline/commands/ops/optimize_media_assets.py --dry-run
    .venv/Scripts/python scripts/pipeline/commands/ops/optimize_media_assets.py pdf python --apply
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
import shutil
import subprocess
import urllib.request
import zipfile

from PIL import Image

# ── Constants ────────────────────────────────────────────────────────────────

ICON_DIMENSIONS = frozenset({(1024, 1024), (1254, 1254)})
BANNER_DIMENSIONS = frozenset({(1774, 887)})

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


def target_path(source: Path, shape: str) -> Path:
    """Compute the destination path for a classified file: same directory,
    generic name -- the directory already encodes family/platform."""
    name = "icon.png" if shape == "icon" else "banner.png"
    return source.parent / name


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


def run_oxipng(oxipng_bin: str, path: Path, use_zopfli: bool) -> None:
    cmd = [oxipng_bin, "-o", "max", "--strip", "safe"]
    if use_zopfli:
        cmd.append("-z")
    cmd.append(str(path))
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
    return sorted(base.rglob("*.png"))


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

    dest = target_path(source, shape)
    record["target"] = str(dest)

    if dest.exists() and dest != source and not pixels_identical(source, dest):
        record["status"] = "BLOCKED"
        return record

    if not apply:
        record["status"] = "PLANNED"
        return record

    tmp_path = dest.parent / f"__optimize_tmp__{dest.name}"
    try:
        shutil.copy2(source, tmp_path)
        run_oxipng(oxipng_bin, tmp_path, use_zopfli=False)
        if not pixels_identical(source, tmp_path):
            raise RuntimeError(f"oxipng pass 1 changed pixel data for {source}")
        size_after = tmp_path.stat().st_size

        if size_after >= _cfg_max_bytes:
            run_oxipng(oxipng_bin, tmp_path, use_zopfli=True)
            if not pixels_identical(source, tmp_path):
                raise RuntimeError(f"oxipng pass 2 changed pixel data for {source}")
            size_after = tmp_path.stat().st_size

        if size_after >= _cfg_max_bytes:
            record["status"] = "STILL_OVER_BUDGET"
            record["size_after"] = size_after
            return record

        shutil.move(str(tmp_path), str(dest))
        if source != dest and source.exists():
            source.unlink()
    finally:
        if tmp_path.exists():
            tmp_path.unlink()

    record["status"] = "OK"
    record["size_after"] = size_after
    return record


def run(family: str | None, platform_name: str | None, apply: bool) -> list[dict]:
    media_root = Path(_cfg_media_root)
    files = discover(media_root, family, platform_name)
    oxipng_bin = resolve_oxipng() if apply else (_cfg_oxipng_bin or "oxipng")
    results = []
    for f in files:
        if f.name in ("icon.png", "banner.png") and f.stat().st_size < _cfg_max_bytes:
            results.append({"source": str(f), "status": "SKIP_ALREADY_DONE"})
            continue
        results.append(process_file(f, oxipng_bin, apply))
    return results


# ── CLI ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "optimize_media_assets — S-119: rename static/media product images "
            "to a fixed convention and losslessly compress them under 1MB."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  .venv/Scripts/python scripts/pipeline/commands/ops/optimize_media_assets.py --dry-run
  .venv/Scripts/python scripts/pipeline/commands/ops/optimize_media_assets.py pdf python --apply
        """,
    )
    parser.add_argument("family", nargs="?", help="Product family (optional scope)")
    parser.add_argument("platform", nargs="?", help="Platform (optional scope, requires family)")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="Print the plan; touch nothing")
    mode.add_argument("--apply", action="store_true", help="Perform the rename + compression")
    args = parser.parse_args()

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
        print(line)

    if any(r["status"] in ("STILL_OVER_BUDGET", "BLOCKED", "UNCLASSIFIED") for r in results):
        sys.exit(1)


if __name__ == "__main__":
    main()
