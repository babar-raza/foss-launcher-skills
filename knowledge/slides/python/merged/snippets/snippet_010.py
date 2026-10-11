def test_a_commented_deck_leaves_the_package_consistent(produced):
    """Comment parts must be content-typed and their relationships resolvable."""
    pres = Presentation()
    author = pres.comment_authors.add_author("Alice", "A")
    slide = pres.slides[0]
    when = datetime.datetime(2026, 1, 15, 12, 0, 0)
    root = author.comments.add_comment("Please review", slide, PointF(2.0, 3.0), when)
    reply = author.comments.add_comment("Reviewed", slide, PointF(2.0, 3.0), when)
    reply.parent_comment = root

    pkg = produced(pres)

    pkg.assert_package_is_consistent()