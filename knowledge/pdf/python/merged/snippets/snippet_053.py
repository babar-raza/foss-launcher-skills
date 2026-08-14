def test_be_non_cloud_style_is_ignored():
    # /BE with a solid style ("S") is not a cloud: the border stays straight.
    gen = build_appearance(
        "Square", _RECT, {"C": [0, 0, 0], "BE": {"S": N("S")}, "BS": {"W": 1}}
    )
    assert b" re" in gen.content
    assert b" c\n" not in gen.content