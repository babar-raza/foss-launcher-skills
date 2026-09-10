def test_build_ink_draws_each_path():
    gen = build_appearance(
        "Ink", (0, 0, 100, 100), {"InkList": [[0, 0, 50, 50], [10, 10, 60, 10, 60, 60]]}
    )
    assert gen is not None
    assert gen.content.count(b" m\n") == 2  # one moveto per path
    assert gen.content.count(b"\nS\n") == 2