def test_a_deleted_comment_is_not_left_behind_in_an_orphaned_part(tmp_path):
    """Removing a comment must remove its text from the package, not hide it."""
    pres = Presentation()
    author = pres.comment_authors.add_author("Alice", "A")
    slide = pres.slides[0]
    author.comments.add_comment("keep this one", slide, PointF(1.0, 1.0), WHEN)
    doomed = author.comments.add_comment("delete this one", slide, PointF(2.0, 2.0), WHEN)

    try:
        _save(pres, tmp_path, "before.pptx").close()
        doomed.remove()
        pkg = _save(pres, tmp_path, "after.pptx")
    finally:
        pres.dispose()

    try:
        carrying = [
            part for part in pkg.namelist
            if part.endswith(".xml") and b"delete this one" in pkg.read(part)
        ]
        assert not carrying, (
            "the deleted comment's text is still in the saved package, in %r; "
            "the classic list dropped it and the thread part kept it"
            % carrying
        )
    finally:
        pkg.close()