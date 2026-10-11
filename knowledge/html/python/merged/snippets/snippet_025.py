def test_smoke_all_codecs(canonical_name: str):
    payload = _SMOKE_PAYLOADS.get(canonical_name, b"Hello")
    text, errors = decode_bytes(payload, canonical_name)
    assert isinstance(text, str)
    # No unexpected exception raised.