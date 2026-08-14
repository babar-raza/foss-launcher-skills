def test_animation_builder_path_supports_multiple_steps(testdata_dir) -> None:
    font_path = testdata_dir / "Roboto-VariableFont_wdth,wght.ttf"
    font = FontLoader.open(str(font_path))

    asset = AnimationPreviewBuilder.build_path(
        font,
        [
            AnimationStep({"wght": 400.0, "wdth": 100.0}, label="Regular"),
            AnimationStep({"wght": 700.0, "wdth": 75.0}, label="Condensed Bold"),
            AnimationStep({"wght": 700.0, "wdth": 100.0}, label="Bold"),
        ],
        text="A",
        frames_per_segment=3,
        fps=12,
        preset="draft",
    )

    assert asset.filename == "roboto-animation-path.png"
    assert asset.media_type == "image/apng"
    assert asset.frame_count == 5
    assert asset.fps == 12
    assert asset.frame_labels[0] == "Regular"
    assert asset.frame_labels[-1] == "Bold"
    assert asset.data.startswith(b"\x89PNG\r\n\x1a\n")
    assert b"acTL" in asset.data