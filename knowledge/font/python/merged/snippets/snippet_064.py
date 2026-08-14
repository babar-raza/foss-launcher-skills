def test_preview_animation_path_package_writes_assets(tmp_path: Path):
    out = tmp_path / "animation-package"
    result = run(
        "preview-animation-path-package",
        ROBOTO,
        str(out),
        "--state",
        "Regular",
        "--state",
        "wght=700,wdth=75",
        "--state",
        "Bold",
        "--frames-per-segment",
        "3",
        "--preset",
        "draft",
        "--easing",
        "ease-in-out",
        "--caption-mode",
        "both",
        "--text",
        "Anim Package",
    )
    assert result.returncode == 0
    assert (out / "manifest.json").exists()
    assert (out / "roboto-animation-path-storyboard.png").exists()
    assert (out / "frame-001.png").exists()
    payload = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert payload["frame_count"] >= 3
    assert payload["frames"][0]["filename"] == "frame-001.png"
    assert "Saved:" in result.stdout