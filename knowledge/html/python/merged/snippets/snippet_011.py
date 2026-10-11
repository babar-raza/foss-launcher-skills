def test_override_invalid_label():
    with pytest.raises(ValueError):
        detect_encoding(b"<p>hello</p>", override_encoding="not-real")