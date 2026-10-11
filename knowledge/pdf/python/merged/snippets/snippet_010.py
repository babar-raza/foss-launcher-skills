def test_palette_indices_are_not_rescaled(depth):
    """An index is a lookup key, not an intensity — scaling it corrupts colour."""
    entries = min(1 << depth, 8)
    palette = bytes(
        v for i in range(entries) for v in (i * 30 % 256, 255 - i * 20, i * 11)
    )

    def sample(x, y):
        return [(x + y) % entries]

    image = _decode(_png(_W, _H, 3, depth, sample, palette=palette))
    assert image.color_space == "DeviceRGB"
    expected = bytearray()
    for y in range(_H):
        for x in range(_W):
            index = sample(x, y)[0]
            expected += palette[index * 3 : index * 3 + 3]
    assert image.decoded_data == bytes(expected)