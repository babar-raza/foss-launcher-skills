def test_removing_every_comment_removes_the_thread_part(tmp_path):
    """An empty comment list must leave no thread part behind."""
    pres = Presentation()
    author = pres.comment_authors.add_author("Alice", "A")
    slide = pres.slides[0]
    root = author.comments.add_comment("Please review", slide, PointF(2.0, 3.0), WHEN)
    reply = author.comments.add_comment("Reviewed", slide, PointF(2.0, 3.0), WHEN)
    reply.parent_comment = root

    try:
        _save(pres, tmp_path, "with.pptx").close()
        reply.remove()
        root.remove()
        pkg = _save(pres, tmp_path, "without.pptx")
    finally:
        pres.dispose()

    try:
        assert not pkg.parts_matching(THREADS), (
            "every comment was removed and the thread part is still in the "
            "package: %r" % pkg.parts_matching(THREADS)
        )
        pkg.assert_package_is_consistent()
    finally:
        pkg.close()