def test_builtin_expert_encoding_uses_expert_table():
    charset = CffCharset([".notdef", "oneoldstyle", "Thornsmall"])
    enc = CffEncoding.expert(charset)
    assert int(enc.unicode_to_gid(49)) == 1
    assert int(enc.unicode_to_gid(251)) == 2