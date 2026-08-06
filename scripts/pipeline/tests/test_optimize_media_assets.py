"""
Tests for scripts/pipeline/commands/ops/optimize_media_assets.py (S-119).
"""

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
        max_bytes=1_048_576,
        min_psnr=18.0,
        min_ssim=0.90,
    )


def _make_png(path: Path, size: tuple[int, int], color) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGBA", size, color).save(path, "PNG")
    return path


_REAL_SAMPLE = Path(__file__).resolve().parents[3] / "static" / "media" / "3d" / "icon.png"


def _copy_real_sample_over_budget(dest: Path) -> Path:
    """Copy a real, already-in-repo product icon known (calibrated manually,
    see skills/media-optimize.md) to need WebP quality ~90 to fit under 1MB
    (~150KB result, psnr=21.6dB/ssim=0.948, comfortably above this module's
    floor) -- a small solid-color synthetic image compresses too well under
    any format to exercise the real quality-ladder/floor behavior."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(_REAL_SAMPLE, dest)
    return dest


# ── Classification ───────────────────────────────────────────────────────────

def test_classify_icon_dimensions():
    assert oma.classify(1024, 1024) == "icon"
    assert oma.classify(1254, 1254) == "icon"


def test_classify_banner_dimensions():
    assert oma.classify(1774, 887) == "banner"


def test_classify_unclassified_dimensions():
    assert oma.classify(500, 500) is None
    assert oma.classify(1774, 886) is None


# ── target_path ──────────────────────────────────────────────────────────────

def test_target_path_uses_generic_webp_name_in_same_directory(tmp_path):
    source = tmp_path / "pdf" / "python" / "10a46301-uuid.png"
    assert oma.target_path(source, "icon") == tmp_path / "pdf" / "python" / "icon.webp"
    assert oma.target_path(source, "banner") == tmp_path / "pdf" / "python" / "banner.webp"


def test_target_path_family_level_same_as_platform_level(tmp_path):
    """Family-root files (no platform subfolder) use the same name -- the
    rule is directory-relative, not depth-aware."""
    source = tmp_path / "pdf" / "13d4a291-uuid.png"
    assert oma.target_path(source, "icon") == tmp_path / "pdf" / "icon.webp"


# ── PSNR / SSIM floor ────────────────────────────────────────────────────────

def test_psnr_identical_images_is_infinite():
    img = Image.new("RGB", (32, 32), (10, 20, 30))
    assert oma.psnr(img, img) == float("inf")


def test_global_ssim_identical_images_is_near_one():
    img = Image.new("RGB", (64, 64), (50, 100, 150))
    assert oma.global_ssim(img, img) > 0.999


def test_meets_quality_floor_true_for_identical_images():
    img = Image.new("RGB", (64, 64), (1, 2, 3))
    assert oma.meets_quality_floor(img, img) is True


# ── dry-run ──────────────────────────────────────────────────────────────────

def test_dry_run_plans_without_touching_files(tmp_path):
    media_root = tmp_path / "media"
    source = _make_png(media_root / "pdf" / "python" / "uuid1.png", (1024, 1024), (255, 0, 0, 255))
    oma.configure(media_root=str(media_root))

    results = oma.run(family=None, platform_name=None, apply=False)

    assert len(results) == 1
    assert results[0]["status"] == "PLANNED"
    assert results[0]["target"] == str(media_root / "pdf" / "python" / "icon.webp")
    assert source.exists()  # untouched
    assert not (media_root / "pdf" / "python" / "icon.webp").exists()  # nothing created


def test_dry_run_reports_unclassified_without_touching_files(tmp_path):
    media_root = tmp_path / "media"
    source = _make_png(media_root / "weird" / "odd.png", (500, 500), (0, 255, 0, 255))
    oma.configure(media_root=str(media_root))

    results = oma.run(family=None, platform_name=None, apply=False)

    assert results[0]["status"] == "UNCLASSIFIED"
    assert source.exists()


# ── apply: WebP path ─────────────────────────────────────────────────────────

def test_apply_converts_small_source_to_webp_and_preserves_alpha(tmp_path):
    media_root = tmp_path / "media"
    source = _make_png(media_root / "pdf" / "python" / "10a46301-uuid.png", (1024, 1024), (10, 20, 30, 128))
    oma.configure(media_root=str(media_root))

    results = oma.run(family=None, platform_name=None, apply=True)

    assert results[0]["status"] == "NEEDS_VISUAL_REVIEW"
    dest = media_root / "pdf" / "python" / "icon.webp"
    assert dest.exists()
    assert source.exists()  # WebP is lossy -- never auto-deleted, awaits confirm_reviewed()
    with Image.open(dest) as img:
        assert img.size == (1024, 1024)
        assert img.mode == "RGBA"
        px = img.convert("RGBA").getpixel((0, 0))
        assert px[3] == 128  # alpha preserved, not flattened to opaque


def test_webp_fallback_reaches_budget_on_hard_to_compress_real_sample(tmp_path):
    """Real, detail-rich source content that needs the quality ladder to
    step down (calibrated manually, see skills/media-optimize.md: q90 lands
    at ~150KB, well within budget and above the psnr/ssim floor)."""
    media_root = tmp_path / "media"
    source = _copy_real_sample_over_budget(media_root / "pdf" / "go" / "uuid.png")
    oma.configure(media_root=str(media_root))

    results = oma.run(family=None, platform_name=None, apply=True)

    result = results[0]
    assert result["status"] == "NEEDS_VISUAL_REVIEW"
    webp_path = media_root / "pdf" / "go" / "icon.webp"
    assert webp_path.exists()
    assert webp_path.stat().st_size < 1_048_576
    assert source.exists()  # NOT deleted automatically -- awaiting review
    assert "psnr" in result and "ssim" in result


def test_process_file_reencodes_already_correctly_named_file_in_place(tmp_path):
    """When webp_path == source (already named icon.webp but still over
    budget under a stricter test threshold), process_file must still replace
    it safely rather than corrupting the only copy mid-write.

    Called directly (not through run()) to isolate this from the separate
    SKIP_ALREADY_DONE size-gate in run(), which is covered by its own test.
    """
    media_root = tmp_path / "media"
    source = media_root / "3d" / "java" / "icon.webp"
    source.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGBA", (1024, 1024), (1, 2, 3, 255)).save(source, "WEBP", quality=95)
    oma.configure(media_root=str(media_root))

    result = oma.process_file(source, apply=True)

    assert result["status"] == "NEEDS_VISUAL_REVIEW"
    assert source.exists()  # same path as target -- still there, just re-encoded
    with Image.open(source) as img:
        # WebP is lossy -- even at quality 95 a solid color shifts by a unit
        # or two from quantization. Approximate match, not bit-exact.
        px = img.convert("RGBA").getpixel((0, 0))
        assert all(abs(a - b) <= 5 for a, b in zip(px, (1, 2, 3, 255)))


def test_skip_already_done_leaves_compliant_webp_untouched(tmp_path):
    media_root = tmp_path / "media"
    source = media_root / "barcode" / "python" / "icon.webp"
    source.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (304, 335), (5, 5, 5)).save(source, "WEBP", quality=90)
    oma.configure(media_root=str(media_root))

    results = oma.run(family=None, platform_name=None, apply=True)

    assert results[0]["status"] == "SKIP_ALREADY_DONE"
    assert source.exists()


def test_overwrite_guard_blocks_differing_target(tmp_path):
    media_root = tmp_path / "media"
    webp_dir = media_root / "email" / "python"
    webp_dir.mkdir(parents=True, exist_ok=True)
    Image.new("RGBA", (1024, 1024), (1, 1, 1, 255)).save(webp_dir / "icon.webp", "WEBP", quality=90)
    stray = _make_png(webp_dir / "stray-uuid.png", (1024, 1024), (9, 9, 9, 255))
    oma.configure(media_root=str(media_root))

    results = oma.run(family="email", platform_name="python", apply=True)

    stray_result = next(r for r in results if r["source"] == str(stray))
    assert stray_result["status"] == "BLOCKED"
    assert stray.exists()  # neither file touched


def test_confirm_reviewed_deletes_original_after_review(tmp_path):
    media_root = tmp_path / "media"
    source = _copy_real_sample_over_budget(media_root / "pdf" / "go" / "uuid.png")
    oma.configure(media_root=str(media_root))
    oma.run(family=None, platform_name=None, apply=True)
    assert source.exists()

    results = oma.confirm_reviewed([str(source)])

    assert results[0]["status"] == "DELETED"
    assert not source.exists()
    assert (media_root / "pdf" / "go" / "icon.webp").exists()


def test_confirm_reviewed_reports_already_gone(tmp_path):
    results = oma.confirm_reviewed([str(tmp_path / "nope.png")])
    assert results[0]["status"] == "ALREADY_GONE"


def test_confirm_reviewed_in_place_target_is_already_finalized(tmp_path):
    media_root = tmp_path / "media"
    source = media_root / "3d" / "java" / "icon.webp"
    source.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGBA", (1024, 1024), (1, 2, 3, 255)).save(source, "WEBP", quality=95)

    results = oma.confirm_reviewed([str(source)])

    assert results[0]["status"] == "ALREADY_FINALIZED"
    assert source.exists()  # nothing to delete -- it was already written in place


def test_still_over_budget_is_reported_not_silently_degraded(tmp_path):
    media_root = tmp_path / "media"
    source = _make_png(media_root / "pdf" / "go" / "uuid.png", (1024, 1024), (7, 7, 7, 255))
    oma.configure(media_root=str(media_root), max_bytes=1)  # impossible to satisfy at any quality

    results = oma.run(family=None, platform_name=None, apply=True)

    assert results[0]["status"] == "STILL_OVER_BUDGET"
    assert source.exists()  # original left in place
    assert not (media_root / "pdf" / "go" / "icon.webp").exists()
