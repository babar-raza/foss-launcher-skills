def test_16_bit_grayscale_interlaced():
    def sample(x, y):
        return [(x * 2571 + y * 511) % 65536]

    plain = _decode(_png(_W, _H, 0, 16, sample, interlace=0))
    woven = _decode(_png(_W, _H, 0, 16, sample, interlace=1))
    assert plain.decoded_data == woven.decoded_data