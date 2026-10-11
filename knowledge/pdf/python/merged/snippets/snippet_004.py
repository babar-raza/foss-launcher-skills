def test_interlaced_and_progressive_agree():
    """The two encodings of the same image must decode identically."""
    plain = _decode(_png(_W, _H, 2, 8, _rgb_at, interlace=0))
    woven = _decode(_png(_W, _H, 2, 8, _rgb_at, interlace=1))
    assert plain.decoded_data == woven.decoded_data