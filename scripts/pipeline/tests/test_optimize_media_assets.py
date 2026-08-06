"""
Tests for scripts/pipeline/commands/ops/optimize_media_assets.py (S-119).
"""

import hashlib
import shutil
from pathlib import Path

import pytest
from PIL import Image

import commands.ops.optimize_media_assets as oma


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def reset_config():
    yield
    oma.configure(
        media_root="static/media",
        oxipng_bin=None,
        cache_dir="cache/oxipng",
        max_bytes=1_048_576,
    )


def _make_png(path: Path, size: tuple[int, int], color) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGBA", size, color).save(path, "PNG")
    return path


def _make_webp(path: Path, size: tuple[int, int], color) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGBA", size, color).save(path, "WEBP", quality=90)
    return path


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


_REPO_ROOT = Path(__file__).resolve().parents[3]
_REAL_MEDIA_ROOT = _REPO_ROOT / "static" / "media"
_REAL_SAMPLE_WEBP = _REAL_MEDIA_ROOT / "3d" / "icon.webp"


# ── Classification ───────────────────────────────────────────────────────────

def test_classify_icon_dimensions():
    assert oma.classify(1024, 1024) == "icon"
    assert oma.classify(1254, 1254) == "icon"


def test_classify_banner_dimensions():
    assert oma.classify(1774, 887) == "banner"


def test_classify_unclassified_dimensions():
    assert oma.classify(500, 500) is None


# ── target_paths / is_canonical ──────────────────────────────────────────────

def test_target_paths_returns_both_extensions(tmp_path):
    source = tmp_path / "pdf" / "python" / "icon.webp"
    png_path, webp_path = oma.target_paths(source, "icon")
    assert png_path == tmp_path / "pdf" / "python" / "icon.png"
    assert webp_path == tmp_path / "pdf" / "python" / "icon.webp"


def test_is_canonical():
    assert oma.is_canonical(Path("a/b/icon.png")) is True
    assert oma.is_canonical(Path("a/b/banner.webp")) is True
    assert oma.is_canonical(Path("a/b/some-uuid.png")) is False


# ── PSNR / SSIM (informational only) ─────────────────────────────────────────

def test_psnr_identical_images_is_infinite():
    img = Image.new("RGB", (32, 32), (10, 20, 30))
    assert oma.psnr(img, img) == float("inf")


def test_global_ssim_identical_images_is_near_one():
    img = Image.new("RGB", (64, 64), (50, 100, 150))
    assert oma.global_ssim(img, img) > 0.999


# ── Quantization ─────────────────────────────────────────────────────────────

def test_quantize_preserving_alpha_keeps_alpha_exact():
    img = Image.new("RGBA", (64, 64), (10, 20, 30, 128))
    q = oma.quantize_preserving_alpha(img, 16)
    assert q.mode == "RGBA"
    assert q.getpixel((0, 0))[3] == 128


def test_quantize_preserving_alpha_rgb_source():
    img = Image.new("RGB", (64, 64), (200, 50, 50))
    q = oma.quantize_preserving_alpha(img, 16)
    assert q.size == (64, 64)


# ── Transparency extraction ──────────────────────────────────────────────────

def test_extract_transparency_on_white_background():
    img = Image.new("RGB", (100, 100), (255, 255, 255))
    for x in range(30, 70):
        for y in range(30, 70):
            img.putpixel((x, y), (10, 20, 200))
    result = oma.extract_transparency(img)
    assert result is not None
    assert result.mode == "RGBA"
    assert result.getpixel((1, 1))[3] < 10  # corner (background) mostly transparent
    assert result.getpixel((50, 50))[3] > 245  # center (foreground) mostly opaque


def test_extract_transparency_none_on_ambiguous_background():
    img = Image.new("RGB", (100, 100), (128, 128, 128))
    # Add noise so the border isn't uniform enough to trust.
    for x in range(0, 100, 3):
        img.putpixel((x, 0), (255, 0, 0))
        img.putpixel((0, x), (0, 255, 0))
    assert oma.extract_transparency(img) is None


# ── dry-run ──────────────────────────────────────────────────────────────────

def test_dry_run_plans_missing_sibling_for_canonical_source(tmp_path):
    media_root = tmp_path / "media"
    source = _make_webp(media_root / "pdf" / "python" / "icon.webp", (1024, 1024), (255, 0, 0, 255))
    oma.configure(media_root=str(media_root))

    results = oma.run(family=None, platform_name=None, apply=False)

    assert len(results) == 1
    assert results[0]["status"] == "PLANNED"
    assert results[0]["target"] == str(media_root / "pdf" / "python" / "icon.png")
    assert source.exists()


def test_dry_run_plans_both_targets_for_raw_upload(tmp_path):
    media_root = tmp_path / "media"
    source = _make_png(media_root / "pdf" / "python" / "10a46301-uuid.png", (1024, 1024), (255, 0, 0, 255))
    oma.configure(media_root=str(media_root))

    results = oma.run(family=None, platform_name=None, apply=False)

    assert results[0]["status"] == "PLANNED"
    assert set(results[0]["targets"]) == {
        str(media_root / "pdf" / "python" / "icon.png"),
        str(media_root / "pdf" / "python" / "icon.webp"),
    }


def test_dry_run_reports_unclassified(tmp_path):
    media_root = tmp_path / "media"
    source = _make_png(media_root / "weird" / "odd.png", (500, 500), (0, 255, 0, 255))
    oma.configure(media_root=str(media_root))

    results = oma.run(family=None, platform_name=None, apply=False)

    assert results[0]["status"] == "UNCLASSIFIED"
    assert source.exists()


# ── apply: canonical source (the current real-repo case: 72 files, all .webp) ──

def test_apply_generates_missing_png_sibling_and_preserves_webp(tmp_path):
    media_root = tmp_path / "media"
    source = _make_webp(media_root / "pdf" / "python" / "icon.webp", (1024, 1024), (10, 20, 30, 255))
    original_hash = _sha256(source)
    oma.configure(media_root=str(media_root))

    results = oma.run(family=None, platform_name=None, apply=True)

    # A solid-color synthetic image compresses trivially -- it may legitimately
    # succeed via the lossless attempt ("OK") rather than needing quantization
    # ("NEEDS_VISUAL_REVIEW"), unlike the real detail-rich production images.
    # Both indicate the sibling was successfully generated.
    assert results[0]["status"] in ("OK", "NEEDS_VISUAL_REVIEW")
    assert results[0]["format"] == "png"
    png_path = media_root / "pdf" / "python" / "icon.png"
    assert png_path.exists()
    assert source.exists()
    assert _sha256(source) == original_hash  # byte-for-byte untouched, not just "still exists"


def test_apply_generates_missing_webp_sibling_for_png_source(tmp_path):
    media_root = tmp_path / "media"
    source = _make_png(media_root / "pdf" / "python" / "icon.png", (1024, 1024), (10, 20, 30, 255))
    original_hash = _sha256(source)
    oma.configure(media_root=str(media_root))

    results = oma.run(family=None, platform_name=None, apply=True)

    assert results[0]["status"] == "NEEDS_VISUAL_REVIEW"
    assert results[0]["format"] == "webp"
    webp_path = media_root / "pdf" / "python" / "icon.webp"
    assert webp_path.exists()
    assert source.exists()
    assert _sha256(source) == original_hash


def test_skip_already_done_when_both_siblings_present(tmp_path):
    media_root = tmp_path / "media"
    icon_dir = media_root / "barcode" / "python"
    _make_webp(icon_dir / "icon.webp", (1024, 1024), (5, 5, 5, 255))
    _make_png(icon_dir / "icon.png", (1024, 1024), (5, 5, 5, 255))
    oma.configure(media_root=str(media_root))

    results = oma.run(family=None, platform_name=None, apply=True)

    assert all(r["status"] == "SKIP_ALREADY_DONE" for r in results)


# ── apply: raw upload (both targets generated, original preserved until confirm) ──

def test_apply_raw_upload_generates_both_targets(tmp_path):
    media_root = tmp_path / "media"
    source = _make_png(media_root / "pdf" / "python" / "10a46301-uuid.png", (1024, 1024), (10, 20, 30, 255))
    oma.configure(media_root=str(media_root))

    results = oma.run(family=None, platform_name=None, apply=True)

    result = results[0]
    assert result["status"] == "NEEDS_VISUAL_REVIEW"
    assert result["png"]["status"] in ("OK", "NEEDS_VISUAL_REVIEW")
    assert result["webp"]["status"] == "NEEDS_VISUAL_REVIEW"
    assert (media_root / "pdf" / "python" / "icon.png").exists()
    assert (media_root / "pdf" / "python" / "icon.webp").exists()
    assert source.exists()  # not deleted automatically


def test_pending_review_when_raw_upload_conflicts_with_existing_target(tmp_path):
    media_root = tmp_path / "media"
    icon_dir = media_root / "email" / "python"
    _make_webp(icon_dir / "icon.webp", (1024, 1024), (1, 1, 1, 255))
    stray = _make_png(icon_dir / "stray-uuid.png", (1024, 1024), (9, 9, 9, 255))
    oma.configure(media_root=str(media_root))

    results = oma.run(family="email", platform_name="python", apply=True)

    stray_result = next(r for r in results if r["source"] == str(stray))
    assert stray_result["status"] == "PENDING_REVIEW"
    assert stray.exists()


def test_still_over_budget_reported_for_canonical_source(tmp_path):
    media_root = tmp_path / "media"
    source = _make_webp(media_root / "pdf" / "go" / "icon.webp", (1024, 1024), (7, 7, 7, 255))
    oma.configure(media_root=str(media_root), max_bytes=1)

    results = oma.run(family=None, platform_name=None, apply=True)

    assert results[0]["status"] == "STILL_OVER_BUDGET"
    assert source.exists()
    assert not (media_root / "pdf" / "go" / "icon.png").exists()


# ── confirm_reviewed ─────────────────────────────────────────────────────────

def test_confirm_reviewed_canonical_source_is_never_deleted(tmp_path):
    media_root = tmp_path / "media"
    source = _make_webp(media_root / "pdf" / "python" / "icon.webp", (1024, 1024), (1, 2, 3, 255))
    oma.configure(media_root=str(media_root))

    results = oma.confirm_reviewed([str(source)])

    assert results[0]["status"] == "ALREADY_FINALIZED"
    assert source.exists()


def test_confirm_reviewed_deletes_raw_upload_once_both_targets_exist(tmp_path):
    media_root = tmp_path / "media"
    source = _make_png(media_root / "pdf" / "python" / "uuid.png", (1024, 1024), (10, 20, 30, 255))
    oma.configure(media_root=str(media_root))
    oma.run(family=None, platform_name=None, apply=True)
    assert source.exists()

    results = oma.confirm_reviewed([str(source)])

    assert results[0]["status"] == "DELETED"
    assert not source.exists()
    assert (media_root / "pdf" / "python" / "icon.png").exists()
    assert (media_root / "pdf" / "python" / "icon.webp").exists()


def test_confirm_reviewed_no_target_found(tmp_path):
    media_root = tmp_path / "media"
    source = _make_png(media_root / "pdf" / "python" / "uuid.png", (1024, 1024), (10, 20, 30, 255))
    oma.configure(media_root=str(media_root))
    # Deliberately never run apply -- no targets exist yet.

    results = oma.confirm_reviewed([str(source)])

    assert results[0]["status"] == "NO_TARGET_FOUND"
    assert source.exists()


def test_confirm_reviewed_already_gone():
    results = oma.confirm_reviewed(["static/media/nope/uuid.png"])
    assert results[0]["status"] == "ALREADY_GONE"


# ── Corpus-wide margin check against the real repository (conservative: skips
#    the oxipng polish pass, which can only shrink further, to keep this fast) ─

@pytest.mark.skipif(not _REAL_MEDIA_ROOT.exists(), reason="static/media not present in this checkout")
def test_real_corpus_quantizes_under_budget_with_margin():
    webp_files = sorted(_REAL_MEDIA_ROOT.rglob("*.webp"))
    assert len(webp_files) > 0, "expected real static/media/**/*.webp fixtures"
    margin_floor = 0.20  # at least 20% headroom under budget, before the oxipng bonus
    failures = []
    for src in webp_files:
        with Image.open(src) as img:
            img.load()
            q = oma.quantize_preserving_alpha(img, 256)
            import io as _io
            buf = _io.BytesIO()
            q.save(buf, "PNG", optimize=True)
            size = buf.tell()
        if size >= oma._cfg_max_bytes * (1 - margin_floor):
            failures.append((src, size))
    assert not failures, f"files without {margin_floor:.0%} margin at 256 colors: {failures}"
