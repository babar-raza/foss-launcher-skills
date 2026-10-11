def test_encode_apng_invalid_size():
    w, h = 10, 10
    frame1 = bytearray([255, 0, 0] * w * h)
    frame2 = bytearray([0, 255, 0] * (w * h - 1))  # Invalid size

    with pytest.raises(ValueError, match="buffer size mismatch"):
        encode_apng_from_rgb([bytes(frame1), bytes(frame2)], w, h, fps=10)