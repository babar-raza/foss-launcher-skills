def test_decode_windows1252_non_ascii():
    text, errors = decode_bytes(b"caf\xe9", "windows-1252")
    assert text == "caf\u00e9"
    assert errors == []