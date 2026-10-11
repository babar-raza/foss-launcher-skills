def test_animation_builder_writes_review_package(testdata_dir, tmp_path) -> None:
    font_path = testdata_dir / "Roboto-VariableFont_wdth,wght.ttf"
    font = FontLoader.open(str(font_path))

    package = AnimationPreviewBuilder.build_path_review_package(
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

    assert isinstance(package, AnimationReviewPackage)
    written = package.write_to(tmp_path / "animation-review")
    markdown = written / "roboto-animation-path-storyboard.md"
    html = written / "roboto-animation-path-storyboard.html"
    manifest = written / "roboto-animation-path-storyboard-manifest.json"
    assert markdown.exists()
    assert html.exists()
    assert manifest.exists()
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    assert payload["type"] == "animation-review-package"
    assert payload["storyboard"].endswith(".png")