def test_animation_builder_sweep(testdata_dir):
    font_path = testdata_dir / "Roboto-VariableFont_wdth,wght.ttf"
    font = FontLoader.open(str(font_path))

    # Sweep wdth from 75 to 100 with bounce (3 frames -> generates 4 frames: 0, 1, 2, reversed_1)
    asset = AnimationPreviewBuilder.build_axis_sweep(
        font,
        axis_tag="wdth",
        start_val=75.0,
        end_val=100.0,
        frames=3,
        fps=10,
        text="A",
        size=10.0,
        bounce=True,
    )

    assert asset.filename == "roboto-sweep-wdth.png"
    assert asset.media_type == "image/apng"

    data = asset.data
    assert data.startswith(b"\x89PNG\r\n\x1a\n")
    assert b"acTL" in data
    assert b"fcTL" in data
    # Check there is an IDAT (first frame) and fdAT (subsequent frames)
    assert b"IDAT" in data
    assert b"fdAT" in data
    assert asset.frame_count == 4
    assert asset.fps == 10
    assert asset.frame_labels[0] == "wdth=75"
    assert asset.frame_labels[2] == "wdth=100"