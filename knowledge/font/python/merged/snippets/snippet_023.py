def test_builtin_standard_encoding_uses_standard_table():
    charset = CffCharset([".notdef", "A", "space", "germandbls"])
    enc = CffEncoding.standard(charset)
    assert int(enc.unicode_to_gid(65)) == 1
    assert int(enc.unicode_to_gid(32)) == 2
    assert int(enc.unicode_to_gid(249)) == 3