def test_override_latin1_maps_to_windows1252():
    result = detect_encoding(b"<p>hello</p>", override_encoding="latin1")
    assert result.encoding == "windows-1252"
    assert result.confidence == "certain"