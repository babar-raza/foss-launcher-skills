def test_lone_cr_normalised():
    data = "line1\rline2".encode("utf-8")
    result = detect_encoding(data)
    assert "\r" not in result.text
    assert result.text == "line1\nline2"