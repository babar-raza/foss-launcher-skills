def test_palette_interlaced():
    palette = bytes([0, 0, 0, 255, 0, 0, 0, 255, 0, 0, 0, 255])

    def sample(x, y):
        return [(x * y) % 4]

    plain = _decode(_png(_W, _H, 3, 4, sample, palette=palette, interlace=0))
    woven = _decode(_png(_W, _H, 3, 4, sample, palette=palette, interlace=1))
    assert plain.decoded_data == woven.decoded_data