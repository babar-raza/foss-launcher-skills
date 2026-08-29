def test_build_stamp_draws_named_caption_in_red_by_default():
    gen = build_appearance(
        "Stamp", (0, 0, 120, 40), {"Name": "NotApproved"}
    )
    assert gen is not None
    assert b"1 0 0 RG" in gen.content  # default rubber-stamp red border
    assert b"(NOT APPROVED) Tj" in gen.content  # camel-split, upper-cased
    assert "Helv" in gen.fonts