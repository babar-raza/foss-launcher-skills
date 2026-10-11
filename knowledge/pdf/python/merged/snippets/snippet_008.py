def test_16_bit_keeps_the_high_byte():
    def sample(x, y):
        return [(x * 4097) % 65536, (y * 8193) % 65536, 0x1234]

    image = _decode(_png(_W, _H, 2, 16, sample))
    expected = bytes(
        (v >> 8) & 0xFF for y in range(_H) for x in range(_W) for v in sample(x, y)
    )
    assert image.decoded_data == expected