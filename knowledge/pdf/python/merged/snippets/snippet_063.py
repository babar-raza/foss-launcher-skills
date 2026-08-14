def test_build_freetext_draws_wrapped_text_and_border():
    gen = build_appearance(
        "FreeText",
        (0, 0, 60, 80),
        {"Contents": "the quick brown fox jumps", "DA": "/Helv 10 Tf 0 g"},
    )
    assert gen is not None
    assert b"/Helv 10 Tf" in gen.content
    assert b"0 g" in gen.content  # DA text colour
    assert gen.content.count(b" Tj") > 1  # wrapped across lines
    assert b" re" in gen.content and b"\nS\n" in gen.content  # border box
    # A font resource is requested so the caller can build /Resources /Font.
    assert "Helv" in gen.fonts