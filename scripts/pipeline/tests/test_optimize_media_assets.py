"""
Tests for scripts/pipeline/commands/ops/optimize_media_assets.py (S-119).
"""

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

def test_target_path_uses_generic_name_in_same_directory(tmp_path):
    source = tmp_path / "pdf" / "python" / "10a46301-uuid.png"
    assert oma.target_path(source, "icon") == tmp_path / "pdf" / "python" / "icon.png"
    assert oma.target_path(source, "banner") == tmp_path / "pdf" / "python" / "banner.png"


def test_target_path_family_level_same_as_platform_level(tmp_path):
    """Family-root files (no platform subfolder) use the same icon.png name --
    the rule is directory-relative, not depth-aware."""
    source = tmp_path / "pdf" / "13d4a291-uuid.png"
    assert oma.target_path(source, "icon") == tmp_path / "pdf" / "icon.png"


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


# ── apply (oxipng itself is monkeypatched out -- no network/binary dependency) ──

def test_apply_renames_and_verifies_pixel_identity(tmp_path, monkeypatch):
    media_root = tmp_path / "media"
    source = _make_png(media_root / "pdf" / "python" / "10a46301-uuid.png", (1024, 1024), (10, 20, 30, 255))
    oma.configure(media_root=str(media_root))
    monkeypatch.setattr(oma, "run_oxipng", lambda *a, **kw: None)

    results = oma.run(family=None, platform_name=None, apply=True)

    assert results[0]["status"] == "OK"
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


def test_skip_already_done_leaves_compliant_file_untouched(tmp_path):
    media_root = tmp_path / "media"
    source = _make_png(media_root / "barcode" / "python" / "icon.png", (304, 335), (5, 5, 5, 255))
    oma.configure(media_root=str(media_root))

    results = oma.run(family=None, platform_name=None, apply=True)

    assert results[0]["status"] == "SKIP_ALREADY_DONE"
    assert source.exists()


def test_overwrite_guard_blocks_differing_target(tmp_path, monkeypatch):
    media_root = tmp_path / "media"
    _make_png(media_root / "email" / "python" / "icon.png", (1024, 1024), (1, 1, 1, 255))
    stray = _make_png(media_root / "email" / "python" / "stray-uuid.png", (1024, 1024), (9, 9, 9, 255))
    oma.configure(media_root=str(media_root))
    monkeypatch.setattr(oma, "run_oxipng", lambda *a, **kw: None)

    results = oma.run(family="email", platform_name="python", apply=True)

    stray_result = next(r for r in results if r["source"] == str(stray))
    assert stray_result["status"] == "BLOCKED"
    assert stray.exists()  # neither file touched


def test_still_over_budget_is_reported_not_silently_degraded(tmp_path, monkeypatch):
    media_root = tmp_path / "media"
    source = _make_png(media_root / "pdf" / "go" / "uuid.png", (1024, 1024), (7, 7, 7, 255))
    oma.configure(media_root=str(media_root), max_bytes=1)  # impossible to satisfy
    monkeypatch.setattr(oma, "run_oxipng", lambda *a, **kw: None)

    results = oma.run(family=None, platform_name=None, apply=True)

    assert results[0]["status"] == "STILL_OVER_BUDGET"
    assert source.exists()  # original left in place, no lossy fallback attempted
    assert not (media_root / "pdf" / "go" / "icon.png").exists()
