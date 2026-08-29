def test_build_freetext_fills_background_from_c():
    gen = build_appearance(
        "FreeText", (0, 0, 100, 40), {"Contents": "hi", "C": [1, 1, 0]}
    )
    assert gen is not None
    assert b"1 1 0 rg" in gen.content  # yellow background fill
    assert b"\nf\n" in gen.content