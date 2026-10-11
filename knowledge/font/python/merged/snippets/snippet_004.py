def test_animation_builder_exposes_presets() -> None:
    assert AnimationPreviewBuilder.available_presets() == ("draft", "standard", "showcase")