def test_gray_alpha_keeps_the_gray_channel():
    image = _decode(_png(_W, _H, 4, 8, lambda x, y: [(x * 9) % 256, 128]))
    assert image.color_space == "DeviceGray"
    assert image.decoded_data == bytes((x * 9) % 256 for _y in range(_H)
                                       for x in range(_W))