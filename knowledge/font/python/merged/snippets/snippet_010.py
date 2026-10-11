def test_animation_builder_writes_showcase_package(testdata_dir, tmp_path) -> None:
    font_path = testdata_dir / "Roboto-VariableFont_wdth,wght.ttf"
    font = FontLoader.open(str(font_path))

    package = AnimationPreviewBuilder.build_path_showcase_package(
        font,
        [
            AnimationStep({"wght": 400.0, "wdth": 100.0}, label="Regular"),
            AnimationStep({"wght": 700.0, "wdth": 75.0}, label="Condensed Bold"),
        ],
        text="A",
        frames_per_segment=3,
        preset="draft",
        caption_mode="both",
    )

    assert isinstance(package, AnimationShowcasePackage)
    written = package.write_to(tmp_path / "animation-showcase")
    assert (written / "roboto-animation-path.png").exists()
    assert (written / "roboto-animation-path-showcase.html").exists()
    assert (written / "roboto-animation-path-showcase-manifest.json").exists()
    assert (written / "roboto-animation-path-storyboard.html").exists()
    payload = json.loads(
        (written / "roboto-animation-path-showcase-manifest.json").read_text(encoding="utf-8")
    )
    assert payload["type"] == "animation-showcase-package"
    assert payload["animation"]["filename"] == "roboto-animation-path.png"
    assert payload["storyboard"].endswith(".png")