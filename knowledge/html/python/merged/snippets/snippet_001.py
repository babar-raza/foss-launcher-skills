def test_bom_utf8():
    result = detect_encoding(b"\xef\xbb\xbf<p>x</p>")
    assert result.encoding == "utf-8"
    assert result.confidence == "certain"
    # BOM bytes must not appear in decoded text
    assert "\ufeff" not in result.text
    assert result.text == "<p>x</p>"