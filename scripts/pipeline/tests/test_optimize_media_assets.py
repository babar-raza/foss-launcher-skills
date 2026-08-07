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


def test_dry_run_reports_sibling_target_for_over_budget_canonical_source(tmp_path):
    media_root = tmp_path / "media"
    icon_dir = media_root / "email" / "testplat"
    old_webp = _make_webp(icon_dir / "icon.webp", (1024, 1024), (255, 0, 0, 255))
    new_png = _make_png(icon_dir / "icon.png", (1024, 1024), (0, 0, 255, 255))
    oma.configure(media_root=str(media_root), max_bytes=3000)

    results = oma.run(family="email", platform_name="testplat", apply=False)

    png_result = next(r for r in results if r["source"] == str(new_png))
    assert png_result["status"] == "PLANNED"
    assert png_result["target"] == str(new_png)  # recompress itself, not the sibling
    assert png_result["sibling_target"] == str(old_webp)
    assert old_webp.exists() and new_png.exists()  # dry-run touches nothing


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


def test_over_budget_canonical_source_recompresses_itself_not_sibling(tmp_path):
    # Replicates the live 2026-08-06 static/media/email/{cpp,net,python} case:
    # an existing small, budget-compliant .webp (old design) sits next to a
    # freshly-dropped, over-budget .png (new design, different content). The
    # fix must recompress the .png from ITS OWN pixels (never regenerate it
    # from the stale .webp, which would silently discard the update), and
    # must also refresh the stale .webp sibling to match the new content.
    media_root = tmp_path / "media"
    icon_dir = media_root / "email" / "testplat"
    old_webp = _make_webp(icon_dir / "icon.webp", (1024, 1024), (255, 0, 0, 255))  # old design: red
    new_png = _make_png(icon_dir / "icon.png", (1024, 1024), (0, 0, 255, 255))     # new design: blue
    oma.configure(media_root=str(media_root), max_bytes=3000)  # webp(1956) fits, plain png(6489) doesn't

    results = oma.run(family="email", platform_name="testplat", apply=True)

    png_result = next(r for r in results if r["source"] == str(new_png))
    webp_result = next(r for r in results if r["source"] == str(old_webp))

    assert png_result["status"] in ("OK", "NEEDS_VISUAL_REVIEW")
    assert png_result["target"] == str(new_png)  # recompressed itself, not overwritten by the sibling
    assert "sibling_regenerated" in png_result
    assert png_result["sibling_regenerated"]["status"] in ("OK", "NEEDS_VISUAL_REVIEW")

    # The second loop iteration (old_webp as its own "source" entry) is a
    # redundant no-op: the sibling was already fixed inside the png's own
    # turn, so by the time the webp's own turn runs both already match.
    assert webp_result["status"] == "SKIP_ALREADY_DONE"

    with Image.open(new_png) as im:
        assert im.convert("RGB").getpixel((0, 0)) == (0, 0, 255)  # still the NEW design
    with Image.open(old_webp) as im:
        assert im.convert("RGB").getpixel((0, 0)) == (0, 0, 255)  # refreshed to match, not left red
    assert new_png.stat().st_size < 3000
    assert old_webp.stat().st_size < 3000

    # A pre-overwrite backup of the fresh content must survive the apply,
    # since it's the only way to retry if a human/agent rejects the result
    # on visual review. Found live 2026-08-06: this exact gap nearly
    # destroyed unrecoverable user-provided content.
    backup = new_png.with_name(new_png.name + ".bak")
    assert backup.exists()
    with Image.open(backup) as im:
        assert im.convert("RGB").getpixel((0, 0)) == (0, 0, 255)  # backup holds the pristine pre-overwrite pixels
    assert png_result["backup"] == str(backup)


def test_confirm_reviewed_clears_backup_after_over_budget_recompress(tmp_path):
    media_root = tmp_path / "media"
    icon_dir = media_root / "email" / "testplat"
    new_png = _make_png(icon_dir / "icon.png", (1024, 1024), (0, 0, 255, 255))
    oma.configure(media_root=str(media_root), max_bytes=3000)
    oma.run(family="email", platform_name="testplat", apply=True)
    backup = new_png.with_name(new_png.name + ".bak")
    assert backup.exists()

    results = oma.confirm_reviewed([str(new_png)])

    assert results[0]["status"] == "BACKUP_CLEARED"
    assert not backup.exists()
    assert new_png.exists()  # the canonical file itself is untouched by confirm


def test_confirm_reviewed_canonical_source_without_backup_is_unchanged(tmp_path):
    # A canonical source that was never over budget has no backup to clear --
    # must still report the pre-existing ALREADY_FINALIZED no-op.
    media_root = tmp_path / "media"
    source = _make_webp(media_root / "pdf" / "python" / "icon.webp", (1024, 1024), (1, 2, 3, 255))
    oma.configure(media_root=str(media_root))

    results = oma.confirm_reviewed([str(source)])

    assert results[0]["status"] == "ALREADY_FINALIZED"
    assert source.exists()


def test_over_budget_canonical_source_with_no_sibling_recompresses_alone(tmp_path):
    # Simpler case: only the over-budget canonical file exists (no sibling to
    # refresh yet). Must still recompress in place rather than erroring.
    media_root = tmp_path / "media"
    icon_dir = media_root / "email" / "testplat2"
    new_png = _make_png(icon_dir / "icon.png", (1024, 1024), (0, 0, 255, 255))
    oma.configure(media_root=str(media_root), max_bytes=3000)

    results = oma.run(family="email", platform_name="testplat2", apply=True)

    assert results[0]["status"] in ("OK", "NEEDS_VISUAL_REVIEW")
    assert results[0]["target"] == str(new_png)
    assert "sibling_regenerated" in results[0]  # sibling webp gets created too
    assert (icon_dir / "icon.webp").exists()
    assert new_png.stat().st_size < 3000


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


# ── process_replace (explicit operator-directed swap) ───────────────────────

def test_replace_backs_up_and_regenerates_existing_pair(tmp_path):
    media_root = tmp_path / "media"
    icon_dir = media_root / "pdf"
    old_png = _make_png(icon_dir / "icon.png", (1024, 1024), (255, 0, 0, 255))
    old_webp = _make_webp(icon_dir / "icon.webp", (1024, 1024), (255, 0, 0, 255))
    old_png_bytes, old_webp_bytes = old_png.read_bytes(), old_webp.read_bytes()
    new_source = _make_png(tmp_path / "incoming" / "new-icon.png", (1024, 1024), (0, 0, 255, 255))
    oma.configure(media_root=str(media_root))

    result = oma.process_replace(new_source, "pdf", None, media_root, oma.resolve_oxipng())

    assert result["status"] == "NEEDS_VISUAL_REVIEW"
    assert result["png"]["status"] in ("OK", "NEEDS_VISUAL_REVIEW")
    assert result["webp"]["status"] == "NEEDS_VISUAL_REVIEW"

    with Image.open(old_png) as im:
        assert im.convert("RGB").getpixel((0, 0)) == (0, 0, 255)  # new content, not the old red
    with Image.open(old_webp) as im:
        assert im.convert("RGB").getpixel((0, 0)) == (0, 0, 255)

    png_backup = old_png.with_name("icon.png.bak")
    webp_backup = old_webp.with_name("icon.webp.bak")
    assert png_backup.exists() and webp_backup.exists()
    assert png_backup.read_bytes() == old_png_bytes  # backup holds pristine pre-replace bytes
    assert webp_backup.read_bytes() == old_webp_bytes
    assert result["backups"] == {str(old_png): str(png_backup), str(old_webp): str(webp_backup)}


def test_replace_creates_new_family_dir(tmp_path):
    media_root = tmp_path / "media"  # diagram/ocr-style case: no folder yet
    new_source = _make_png(tmp_path / "incoming" / "new-icon.png", (1024, 1024), (10, 200, 30, 255))
    oma.configure(media_root=str(media_root))

    result = oma.process_replace(new_source, "diagram", None, media_root, oma.resolve_oxipng())

    assert result["status"] == "NEEDS_VISUAL_REVIEW"
    assert result["backups"] == {}  # nothing existed to back up
    assert (media_root / "diagram" / "icon.png").exists()
    assert (media_root / "diagram" / "icon.webp").exists()
    assert not (media_root / "diagram" / "icon.png.bak").exists()


def test_replace_unclassified_source_rejected(tmp_path):
    media_root = tmp_path / "media"
    old_png = _make_png(media_root / "pdf" / "icon.png", (1024, 1024), (255, 0, 0, 255))
    original_hash = _sha256(old_png)
    new_source = _make_png(tmp_path / "incoming" / "odd-size.png", (500, 500), (0, 0, 255, 255))
    oma.configure(media_root=str(media_root))

    result = oma.process_replace(new_source, "pdf", None, media_root, oma.resolve_oxipng())

    assert result["status"] == "UNCLASSIFIED"
    assert _sha256(old_png) == original_hash  # untouched
    assert not old_png.with_name("icon.png.bak").exists()


def test_confirm_reviewed_clears_backup_after_replace(tmp_path):
    media_root = tmp_path / "media"
    icon_dir = media_root / "pdf"
    old_png = _make_png(icon_dir / "icon.png", (1024, 1024), (255, 0, 0, 255))
    _make_webp(icon_dir / "icon.webp", (1024, 1024), (255, 0, 0, 255))
    new_source = _make_png(tmp_path / "incoming" / "new-icon.png", (1024, 1024), (0, 0, 255, 255))
    oma.configure(media_root=str(media_root))
    oma.process_replace(new_source, "pdf", None, media_root, oma.resolve_oxipng())
    png_backup = old_png.with_name("icon.png.bak")
    webp_backup = icon_dir / "icon.webp.bak"
    assert png_backup.exists() and webp_backup.exists()

    results = oma.confirm_reviewed([str(old_png), str(icon_dir / "icon.webp")])

    assert all(r["status"] == "BACKUP_CLEARED" for r in results)
    assert not png_backup.exists()
    assert not webp_backup.exists()
    assert old_png.exists()  # canonical files themselves untouched by confirm


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
