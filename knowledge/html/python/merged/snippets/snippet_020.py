def test_crlf_normalised():
    data = "line1\r\nline2\r\nline3".encode("utf-8")
    result = detect_encoding(data)
    assert "\r" not in result.text
    assert result.text == "line1\nline2\nline3"