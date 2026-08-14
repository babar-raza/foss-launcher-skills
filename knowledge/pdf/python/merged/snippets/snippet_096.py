def test_color_convenience_setter():
    doc, page = _new_page()
    ann = page.annotations.add("Circle", (0, 0, 50, 50), "")
    ann.color = (0.2, 0.4, 0.6)
    a = _roundtrip(doc).pages[0].annotations[0]
    assert a.color == pytest.approx((0.2, 0.4, 0.6))