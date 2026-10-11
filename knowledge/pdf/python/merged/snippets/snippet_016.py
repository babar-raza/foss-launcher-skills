def test_truncated_interlaced_data_is_rejected():
    data = _png(_W, _H, 2, 8, _rgb_at, interlace=1)
    idat = data.index(b"IDAT")
    length = struct.unpack(">I", data[idat - 4 : idat])[0]
    payload = data[idat + 4 : idat + 4 + length]
    short = zlib.compress(zlib.decompress(payload)[:10], 9)
    rebuilt = data[: idat - 4] + _chunk(b"IDAT", short) + _chunk(b"IEND", b"")
    with pytest.raises(PdfValidationException, match="truncated"):
        _decode(rebuilt)