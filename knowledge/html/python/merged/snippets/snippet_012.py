def test_default_utf8():
    result = detect_encoding(b"<p>Hello, world!</p>")
    assert result.encoding == "utf-8"
    assert result.confidence == "irrelevant"