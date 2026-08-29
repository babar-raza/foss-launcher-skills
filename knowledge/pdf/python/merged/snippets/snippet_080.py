def test_build_freetext_wraps_by_glyph_metrics():
    # Same word count, same box: wide 'W' words need more lines than narrow
    # 'i' words under real Helvetica metrics (a flat estimate would tie).
    wide = build_appearance(
        "FreeText",
        (0, 0, 60, 200),
        {"Contents": "WW WW WW WW WW", "DA": "/Helv 12 Tf 0 g"},
    )
    narrow = build_appearance(
        "FreeText",
        (0, 0, 60, 200),
        {"Contents": "ii ii ii ii ii", "DA": "/Helv 12 Tf 0 g"},
    )
    assert narrow is not None and wide is not None
    assert narrow.content.count(b" Tj") < wide.content.count(b" Tj")