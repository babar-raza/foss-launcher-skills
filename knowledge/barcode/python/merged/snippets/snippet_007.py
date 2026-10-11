def test_barcode_service_rejects_invalid_render_options_before_running_pipeline() -> None:
    """Invalid generation-time render overrides should fail before parse or encode."""
    service, parser, encoder, _, events = _build_service()

    with pytest.raises(InvalidInputError, match="scale"):
        service.generate("code128", "ABC123", render=RenderOptions(scale=0))

    assert events == []
    assert parser.calls == []
    assert encoder.calls == []