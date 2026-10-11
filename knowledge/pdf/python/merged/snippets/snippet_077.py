def test_build_highlight_uses_multiply_blend():
    gen = build_appearance(
        "Highlight",
        (100, 100, 300, 140),
        {"QuadPoints": [100, 140, 300, 140, 100, 100, 300, 100], "C": [1, 1, 0]},
    )
    assert gen is not None
    assert gen.ext_gstates == {"GsMul": {"BM": "Multiply"}}
    assert b"/GsMul gs" in gen.content
    assert b"1 1 0 rg" in gen.content
    assert b"0 0 200 40 re" in gen.content  # quad bbox in local coords
    assert b"\nf\n" in gen.content