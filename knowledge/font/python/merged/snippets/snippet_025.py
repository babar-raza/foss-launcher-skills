def test_supplemental_encoding_resolves_custom_sid():
    # format 0 + supplemental: code 65 -> SID 391 (first entry in String INDEX)
    data = bytes([0x80, 0x00, 0x01, 65, 0x01, 0x87])
    r = BinaryReader(data)
    charset = CffCharset([".notdef", "custom-name"])
    string_index = CffIndex([b"custom-name"])
    enc = CffEncoding.from_reader(r, num_glyphs=2, charset=charset, string_index=string_index)
    assert int(enc.unicode_to_gid(65)) == 1