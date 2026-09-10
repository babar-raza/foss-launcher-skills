def test_build_stamp_caption_size_fits_glyph_metrics():
    import re as _re

    def tf_size(content: bytes) -> float:
        m = _re.search(rb"/Helv ([\d.]+) Tf", content)
        assert m is not None
        return float(m.group(1))

    wide = build_appearance("Stamp", (0, 0, 120, 40), {"Contents": "WWWWWWWW"})
    narrow = build_appearance("Stamp", (0, 0, 120, 40), {"Contents": "iiiiiiii"})
    assert wide is not None and narrow is not None
    # The narrow caption is auto-sized larger because it measures narrower.
    assert tf_size(narrow.content) > tf_size(wide.content)