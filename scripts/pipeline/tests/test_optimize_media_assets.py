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
        oxipng_bin=None,
        cache_dir="cache/oxipng",
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
    see skills/media-optimize.md) to survive lossless PNG recompression at
    ~1.3MB -- still over the 1MB budget -- while WebP q90 lands at ~150KB
    with psnr=21.6dB/ssim=0.948, comfortably above this module's floor.

    A synthetic os.urandom() noise image was tried first and rejected: pure
    noise doesn't compress under either PNG or WebP (no perceptual structure
    for either codec to exploit), so it can't exercise the WebP-succeeds
    branch this test needs -- only a STILL_OVER_BUDGET dead end. A real
    sample is the honest way to test the branch that real assets actually
    take.
    """
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


# ── target_candidates ────────────────────────────────────────────────────────

def test_target_candidates_uses_generic_names_in_same_directory(tmp_path):
    source = tmp_path / "pdf" / "python" / "10a46301-uuid.png"
    png_path, webp_path = oma.target_candidates(source, "icon")
    assert png_path == tmp_path / "pdf" / "python" / "icon.png"
    assert webp_path == tmp_path / "pdf" / "python" / "icon.webp"

    png_path, webp_path = oma.target_candidates(source, "banner")
    assert png_path.name == "banner.png"
    assert webp_path.name == "banner.webp"


def test_target_candidates_family_level_same_as_platform_level(tmp_path):
    """Family-root files (no platform subfolder) use the same name -- the
    rule is directory-relative, not depth-aware."""
    source = tmp_path / "pdf" / "13d4a291-uuid.png"
    png_path, _ = oma.target_candidates(source, "icon")
    assert png_path == tmp_path / "pdf" / "icon.png"


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
    assert results[0]["target"] == str(media_root / "pdf" / "python" / "icon.png")
    assert source.exists()  # untouched
    assert not (media_root / "pdf" / "python" / "icon.png").exists()  # nothing created


def test_dry_run_reports_unclassified_without_touching_files(tmp_path):
    media_root = tmp_path / "media"
    source = _make_png(media_root / "weird" / "odd.png", (500, 500), (0, 255, 0, 255))
    oma.configure(media_root=str(media_root))

    results = oma.run(family=None, platform_name=None, apply=False)

    assert results[0]["status"] == "UNCLASSIFIED"
    assert source.exists()


# ── apply: lossless PNG path (oxipng itself is monkeypatched out -- no network/binary dependency) ──

def test_apply_renames_and_verifies_pixel_identity(tmp_path, monkeypatch):
    media_root = tmp_path / "media"
    source = _make_png(media_root / "pdf" / "python" / "10a46301-uuid.png", (1024, 1024), (10, 20, 30, 255))
    oma.configure(media_root=str(media_root))
    monkeypatch.setattr(oma, "run_oxipng", lambda *a, **kw: None)

    results = oma.run(family=None, platform_name=None, apply=True)

    assert results[0]["status"] == "OK"
    assert results[0]["method"] == "lossless-png"
    dest = media_root / "pdf" / "python" / "icon.png"
    assert dest.exists()
    assert not source.exists()
    with Image.open(dest) as img:
        assert img.size == (1024, 1024)
        assert img.convert("RGBA").getpixel((0, 0)) == (10, 20, 30, 255)


def test_process_file_recompresses_already_correctly_named_file_in_place(tmp_path, monkeypatch):
    """When dest == source (already named icon.png/banner.png), process_file
    must still go through the tmp-file/verify/replace dance safely, rather
    than running oxipng directly on the only copy of the file.

    Called directly (not through run()) to isolate this from the separate
    SKIP_ALREADY_DONE size-gate in run(), which is covered by its own test.
    """
    media_root = tmp_path / "media"
    source = _make_png(media_root / "3d" / "java" / "icon.png", (1024, 1024), (1, 2, 3, 255))
    oma.configure(media_root=str(media_root))
    monkeypatch.setattr(oma, "run_oxipng", lambda *a, **kw: None)

    result = oma.process_file(source, oxipng_bin="unused", apply=True)

    assert result["status"] == "OK"
    assert source.exists()  # same path as dest -- still there, just recompressed
    with Image.open(source) as img:
        assert img.convert("RGBA").getpixel((0, 0)) == (1, 2, 3, 255)


@pytest.mark.parametrize("existing_name", ["icon.png", "icon.webp"])
def test_skip_already_done_recognizes_both_extensions(tmp_path, existing_name):
    media_root = tmp_path / "media"
    ext = existing_name.rsplit(".", 1)[1]
    source = media_root / "barcode" / "python" / existing_name
    source.parent.mkdir(parents=True, exist_ok=True)
    if ext == "png":
        Image.new("RGBA", (304, 335), (5, 5, 5, 255)).save(source, "PNG")
    else:
        Image.new("RGB", (304, 335), (5, 5, 5)).save(source, "WEBP", quality=90)
    oma.configure(media_root=str(media_root))

    results = oma.run(family=None, platform_name=None, apply=True)

    assert results[0]["status"] == "SKIP_ALREADY_DONE"
    assert source.exists()


def test_overwrite_guard_blocks_differing_target_across_extensions(tmp_path, monkeypatch):
    """A .webp already occupying the slot blocks a differing-content .png
    source just as a same-extension conflict would."""
    media_root = tmp_path / "media"
    webp_dir = media_root / "email" / "python"
    webp_dir.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (1024, 1024), (1, 1, 1)).convert("RGBA").save(webp_dir / "icon.webp", "WEBP", quality=90)
    stray = _make_png(webp_dir / "stray-uuid.png", (1024, 1024), (9, 9, 9, 255))
    oma.configure(media_root=str(media_root))
    monkeypatch.setattr(oma, "run_oxipng", lambda *a, **kw: None)

    results = oma.run(family="email", platform_name="python", apply=True)

    stray_result = next(r for r in results if r["source"] == str(stray))
    assert stray_result["status"] == "BLOCKED"
    assert stray.exists()  # neither file touched


# ── apply: WebP fallback path ────────────────────────────────────────────────

def test_webp_fallback_when_lossless_png_insufficient(tmp_path, monkeypatch):
    """Real, detail-rich source content that lossless PNG genuinely can't
    bring under budget (calibrated manually): the pipeline must fall back to
    WebP -- staged as NEEDS_VISUAL_REVIEW, original left in place until
    confirm_reviewed()."""
    media_root = tmp_path / "media"
    source = _copy_real_sample_over_budget(media_root / "pdf" / "go" / "uuid.png")
    oma.configure(media_root=str(media_root))
    monkeypatch.setattr(oma, "run_oxipng", lambda *a, **kw: None)  # isolate: lossless alone can't help here anyway

    results = oma.run(family=None, platform_name=None, apply=True)

    result = results[0]
    assert result["status"] == "NEEDS_VISUAL_REVIEW"
    assert result["method"] == "webp"
    webp_path = media_root / "pdf" / "go" / "icon.webp"
    assert webp_path.exists()
    assert webp_path.stat().st_size < 1_048_576
    assert source.exists()  # NOT deleted automatically -- awaiting review
    assert "psnr" in result and "ssim" in result


def test_confirm_reviewed_deletes_original_after_review(tmp_path, monkeypatch):
    media_root = tmp_path / "media"
    source = _copy_real_sample_over_budget(media_root / "pdf" / "go" / "uuid.png")
    oma.configure(media_root=str(media_root))
    monkeypatch.setattr(oma, "run_oxipng", lambda *a, **kw: None)
    oma.run(family=None, platform_name=None, apply=True)
    assert source.exists()

    results = oma.confirm_reviewed([str(source)])

    assert results[0]["status"] == "DELETED"
    assert not source.exists()
    assert (media_root / "pdf" / "go" / "icon.webp").exists()


def test_confirm_reviewed_reports_already_gone(tmp_path):
    results = oma.confirm_reviewed([str(tmp_path / "nope.png")])
    assert results[0]["status"] == "ALREADY_GONE"


def test_still_over_budget_is_reported_not_silently_degraded(tmp_path, monkeypatch):
    media_root = tmp_path / "media"
    source = _make_png(media_root / "pdf" / "go" / "uuid.png", (1024, 1024), (7, 7, 7, 255))
    oma.configure(media_root=str(media_root), max_bytes=1)  # impossible to satisfy, PNG or WebP
    monkeypatch.setattr(oma, "run_oxipng", lambda *a, **kw: None)

    results = oma.run(family=None, platform_name=None, apply=True)

    assert results[0]["status"] == "STILL_OVER_BUDGET"
    assert source.exists()  # original left in place
    assert not (media_root / "pdf" / "go" / "icon.png").exists()
    assert not (media_root / "pdf" / "go" / "icon.webp").exists()
