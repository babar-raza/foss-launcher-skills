def test_decode_shift_jis():
    original = "テスト"
    sjis_bytes = original.encode("shift_jis")
    text, errors = decode_bytes(sjis_bytes, "shift_jis")
    assert text == original
    assert errors == []