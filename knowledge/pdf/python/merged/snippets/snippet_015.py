def test_unknown_interlace_method_is_rejected():
    data = bytearray(_png(4, 4, 2, 8, _rgb_at))
    ihdr = data.index(b"IHDR")
    data[ihdr + 4 + 12] = 2  # interlace byte
    payload = bytes(data[ihdr : ihdr + 4 + 13])
    data[ihdr + 4 + 13 : ihdr + 4 + 17] = struct.pack(
        ">I", zlib.crc32(payload) & 0xFFFFFFFF
    )
    with pytest.raises(PdfValidationException, match="interlace"):
        _decode(bytes(data))