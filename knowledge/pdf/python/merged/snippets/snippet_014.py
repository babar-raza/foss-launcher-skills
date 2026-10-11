def test_bit_depth_illegal_for_the_colour_type_is_rejected():
    """ISO 15948 table 11: truecolour has no 1/2/4-bit form."""
    with pytest.raises(PdfValidationException, match="bit depth"):
        _decode(_png(4, 4, 2, 4, _rgb_at))