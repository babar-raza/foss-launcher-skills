def test_build_circle_uses_bezier_curves():
    gen = build_appearance("Circle", (0, 0, 80, 60), {"IC": [0.5]})
    assert gen is not None
    assert gen.content.count(b" c\n") == 4  # four quarter-arc curves
    assert b"0.5 g" in gen.content  # grayscale fill