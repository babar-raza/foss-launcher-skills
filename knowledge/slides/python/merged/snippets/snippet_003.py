def test_saving_the_same_deck_repeatedly_writes_one_thread_part(tmp_path):
    """A save must reuse the slide's thread part, not allocate the next number."""
    pres = Presentation()
    author = pres.comment_authors.add_author("Alice", "A")
    slide = pres.slides[0]
    author.comments.add_comment("Please review", slide, PointF(2.0, 3.0), WHEN)

    try:
        counts = []
        for attempt in range(1, 5):
            pkg = _save(pres, tmp_path, "save%d.pptx" % attempt)
            counts.append(len(pkg.parts_matching(THREADS)))
            pkg.close()
    finally:
        pres.dispose()

    assert counts == [1, 1, 1, 1], (
        "one comment, saved four times, produced %r thread parts; each save "
        "orphaned the previous part instead of rewriting it" % counts
    )