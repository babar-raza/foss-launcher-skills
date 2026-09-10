def test_a_repeatedly_saved_deck_has_no_unreachable_parts(tmp_path):
    """Nothing may ship that no relationship names."""
    pres = Presentation()
    author = pres.comment_authors.add_author("Alice", "A")
    slide = pres.slides[0]
    author.comments.add_comment("Please review", slide, PointF(2.0, 3.0), WHEN)

    try:
        _save(pres, tmp_path, "first.pptx").close()
        pkg = _save(pres, tmp_path, "second.pptx")
    finally:
        pres.dispose()

    try:
        pkg.assert_every_part_is_reachable()
    finally:
        pkg.close()