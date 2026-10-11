def test_every_threaded_comment_declares_when_it_was_created(produced):
    """`@created` is required on `p188:cm`, whatever the classic list says."""
    pres = Presentation()
    author = pres.comment_authors.add_author("Alice", "A")
    slide = pres.slides[0]
    when = datetime.datetime(2026, 1, 15, 12, 0, 0)
    author.comments.add_comment("Please review", slide, PointF(2.0, 3.0), when)

    pkg = produced(pres)

    part = pkg.parts_matching(r"^ppt/threadedComments/.*\.xml$")[0]
    for comment in pkg.findall(part, "//p188:cm"):
        assert comment.get("created"), (
            "<p188:cm> without @created: %r" % dict(comment.attrib)
        )