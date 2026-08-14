def test_bom_utf16_le():
    payload = "<p>x</p>".encode("utf-16-le")
    data = b"\xff\xfe" + payload
    result = detect_encoding(data)
    assert result.encoding == "utf-16-le"
    assert result.confidence == "certain"