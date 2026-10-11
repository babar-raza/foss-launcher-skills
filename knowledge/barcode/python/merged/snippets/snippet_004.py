def test_barcode_service_runs_parse_before_encode_and_forwards_encode_options() -> None:
    """The service should orchestrate parse -> encode without mutating encode options."""
    service, parser, encoder, profile, events = _build_service()
    encode_options = EncodeOptions(gs1_enabled=True, eci_assignment_number=26)

    barcode = service.generate(" CODE-128 ", "ABC123", encode=encode_options)

    assert events == ["parse", "encode"]
    assert parser.calls == [("ABC123", encode_options)]
    assert encoder.calls == [(parser.payload, encode_options)]
    assert barcode == Barcode(
        symbol=encoder.symbol,
        profile=profile,
        default_render_options=None,
    )