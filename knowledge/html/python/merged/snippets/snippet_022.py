def test_replacement_char_recorded():
    # 0x81 is undefined in cp1252 → produces U+FFFD with errors='replace'.
    text, errors = decode_bytes(b"\x81", "windows-1252")
    assert "\ufffd" in text
    assert any("decode-error" in e for e in errors)