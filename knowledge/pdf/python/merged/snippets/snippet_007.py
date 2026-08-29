def test_sub_byte_depths_work_interlaced(depth):
    maxval = (1 << depth) - 1

    def sample(x, y):
        return [(x * 3 + y) % (maxval + 1)]

    plain = _decode(_png(_W, _H, 0, depth, sample, interlace=0))
    woven = _decode(_png(_W, _H, 0, depth, sample, interlace=1))
    assert plain.decoded_data == woven.decoded_data