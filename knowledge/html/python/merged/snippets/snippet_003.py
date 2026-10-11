def test_bom_utf16_be():
    payload = "<p>x</p>".encode("utf-16-be")
    data = b"\xfe\xff" + payload
    result = detect_encoding(data)
    assert result.encoding == "utf-16-be"
    assert result.confidence == "certain"