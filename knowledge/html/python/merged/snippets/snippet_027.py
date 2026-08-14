def test_unsupported_encoding_raises():
    with pytest.raises(UnsupportedEncodingError):
        decode_bytes(b"hello", "iso-2022-jp")