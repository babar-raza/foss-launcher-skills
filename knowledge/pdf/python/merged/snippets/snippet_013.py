def test_rgba_drops_the_alpha_channel():
    image = _decode(_png(_W, _H, 6, 8, lambda x, y: [*_rgb_at(x, y), 64]))
    assert image.color_space == "DeviceRGB"
    expected = bytes(v for y in range(_H) for x in range(_W) for v in _rgb_at(x, y))
    assert image.decoded_data == expected