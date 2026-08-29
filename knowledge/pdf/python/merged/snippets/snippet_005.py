def test_single_pixel_interlaced():
    """Only the first Adam7 pass is non-empty for a 1x1 image."""
    image = _decode(_png(1, 1, 2, 8, lambda x, y: [10, 20, 30], interlace=1))
    assert image.decoded_data == bytes([10, 20, 30])