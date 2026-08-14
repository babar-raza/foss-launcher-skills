def test_generate_delegates_to_the_default_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The top-level generator should forward all inputs unchanged."""
    service = RecordingService()
    encode_options = EncodeOptions(eci_assignment_number=26)
    render_options = RenderOptions(scale=2.0)

    monkeypatch.setattr(api, "_get_default_service", lambda: service)

    result = api.generate(
        " CODE-128 ",
        b"ABC123",
        encode=encode_options,
        render=render_options,
    )

    assert result is service.result
    assert service.calls == [(" CODE-128 ", b"ABC123", encode_options, render_options)]