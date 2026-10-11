def test_rgb8_round_trips_interlaced_and_not(interlace):
    image = _decode(_png(_W, _H, 2, 8, _rgb_at, interlace=interlace))
    assert (image.width, image.height) == (_W, _H)
    assert image.color_space == "DeviceRGB"
    expected = bytes(
        v for y in range(_H) for x in range(_W) for v in _rgb_at(x, y)
    )
    assert image.decoded_data == expected