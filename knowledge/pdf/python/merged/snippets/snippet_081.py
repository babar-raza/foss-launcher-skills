def test_build_freetext_uses_default_appearance_size_and_colour():
    gen = build_appearance(
        "FreeText", (0, 0, 200, 30), {"Contents": "hi", "DA": "/Helv 14 Tf 1 0 0 rg"}
    )
    assert gen is not None
    assert b"/Helv 14 Tf" in gen.content
    assert b"1 0 0 rg" in gen.content