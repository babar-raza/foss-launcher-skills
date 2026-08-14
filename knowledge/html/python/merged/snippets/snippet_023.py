def test_result_has_encoding_attr():
    result = detect_encoding(b"<p>hello</p>")
    assert isinstance(result.encoding, str)
    assert result.encoding