def test_barcode_service_propagates_typed_domain_errors(
    stage: str,
    failure: Exception,
    expected_events: list[str],
) -> None:
    """Typed barcode-domain exceptions should propagate unchanged."""
    events: list[str] = []
    parser = RecordingParser(
        payload=_build_payload(),
        events=events,
        failure=failure if stage == "parse" else None,
    )
    encoder = RecordingEncoder(
        symbol=_build_symbol(),
        events=events,
        failure=failure if stage == "encode" else None,
    )
    service, _, _, _, _ = _build_service(parser=parser, encoder=encoder)

    with pytest.raises(type(failure)) as exc_info:
        service.generate("code128", "ABC123")

    assert exc_info.value is failure
    assert events == expected_events