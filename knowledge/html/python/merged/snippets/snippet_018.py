def test_decode_gbk():
    original = "你好"
    gbk_bytes = original.encode("gbk")
    text, errors = decode_bytes(gbk_bytes, "gbk")
    assert text == original
    assert errors == []