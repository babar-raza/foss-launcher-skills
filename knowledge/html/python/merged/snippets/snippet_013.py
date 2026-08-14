def test_empty_bytes():
    result = detect_encoding(b"")
    assert result.encoding == "utf-8"
    assert result.text == ""
    # No exception raised.