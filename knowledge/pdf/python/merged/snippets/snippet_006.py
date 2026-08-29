def test_grayscale_sub_byte_depths_are_scaled_to_8_bit(depth):
    maxval = (1 << depth) - 1

    def sample(x, y):
        return [(x + y) % (maxval + 1)]

    image = _decode(_png(_W, _H, 0, depth, sample))
    assert image.color_space == "DeviceGray"
    expected = bytes(
        sample(x, y)[0] * 255 // maxval for y in range(_H) for x in range(_W)
    )
    assert image.decoded_data == expected