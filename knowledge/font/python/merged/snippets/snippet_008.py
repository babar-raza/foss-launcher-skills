def test_animation_builder_writes_frame_package(testdata_dir, tmp_path) -> None:
    font_path = testdata_dir / "Roboto-VariableFont_wdth,wght.ttf"
    font = FontLoader.open(str(font_path))

    package = AnimationPreviewBuilder.build_path_package(
        font,
        [
            AnimationStep({"wght": 400.0, "wdth": 100.0}, label="Regular"),
            AnimationStep({"wght": 700.0, "wdth": 75.0}, label="Condensed Bold"),
        ],
        text="A",
        frames_per_segment=3,
        preset="draft",
        easing="ease-out",
        caption_mode="both",
    )

    assert isinstance(package, AnimationFramePackage)
    assert package.storyboard.filename.endswith("-storyboard.png")
    assert len(package.frames) == 3
    written = package.write_to(tmp_path / "animation-package")
    assert (written / "manifest.json").exists()
    payload = json.loads((written / "manifest.json").read_text(encoding="utf-8"))
    assert payload["frame_count"] == 3
    assert payload["storyboard"].endswith(".png")
    assert payload["frames"][0]["filename"] == "frame-001.png"
    assert "wdth=100" in payload["frames"][0]["label"]