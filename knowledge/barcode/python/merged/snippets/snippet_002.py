def test_symbology_helpers_delegate_with_canonical_ids(
    monkeypatch: pytest.MonkeyPatch,
    helper_name: str,
    expected_symbology: str,
) -> None:
    """Symbology-specific helpers should route through generate() with canonical ids."""
    calls: list[
        tuple[
            str,
            str | bytes,
            EncodeOptions | None,
            RenderOptions | None,
        ]
    ] = []
    expected_result = object()
    encode_options = EncodeOptions(eci_assignment_number=7)
    render_options = RenderOptions(foreground_color="#202020")

    def fake_generate(
        symbology: str,
        data: str | bytes,
        *,
        encode: EncodeOptions | None = None,
        render: RenderOptions | None = None,
    ) -> object:
        calls.append((symbology, data, encode, render))
        return expected_result

    monkeypatch.setattr(api, "generate", fake_generate)

    helper = getattr(api, helper_name)
    result = helper("ABC123", encode=encode_options, render=render_options)

    assert result is expected_result
    assert calls == [
        (expected_symbology, "ABC123", encode_options, render_options),
    ]