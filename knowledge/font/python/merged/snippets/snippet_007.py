def test_animation_builder_named_instance_path_requires_two_steps(testdata_dir) -> None:
    font_path = testdata_dir / "Roboto-VariableFont_wdth,wght.ttf"
    font = FontLoader.open(str(font_path))

    with pytest.raises(ValueError, match="at least two steps"):
        AnimationPreviewBuilder.build_named_instance_path(font, ["Bold"])