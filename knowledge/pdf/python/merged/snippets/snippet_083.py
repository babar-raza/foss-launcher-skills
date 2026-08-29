def test_build_stamp_honours_colour_and_contents_fallback():
    gen = build_appearance(
        "Stamp", (0, 0, 120, 40), {"C": [0, 0, 1], "Contents": "Reviewed"}
    )
    assert gen is not None
    assert b"0 0 1 RG" in gen.content and b"0 0 1 rg" in gen.content
    assert b"(Reviewed) Tj" in gen.content  # falls back to /Contents