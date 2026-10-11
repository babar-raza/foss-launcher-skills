def test_a_comment_reply_survives_being_saved(produced):
    """The parent/child link must be in the package, not only in memory."""
    pres = Presentation()
    author = pres.comment_authors.add_author("Alice", "A")
    slide = pres.slides[0]
    when = datetime.datetime(2026, 1, 15, 12, 0, 0)
    root = author.comments.add_comment("Please review", slide, PointF(2.0, 3.0), when)
    reply = author.comments.add_comment("Reviewed", slide, PointF(2.0, 3.0), when)
    reply.parent_comment = root

    pkg = produced(pres)

    threaded_parts = pkg.parts_matching(r"^ppt/threadedComments/.*\.xml$")
    assert threaded_parts, (
        "a reply was written but the package has no ppt/threadedComments/ part, "
        "so the reply is a second independent comment. parts: %r"
        % sorted(pkg.namelist)
    )

    part = threaded_parts[0]
    assert pkg.content_type_of(part) == THREADED_CONTENT_TYPE

    comments = pkg.findall(part, "//p188:cm")
    assert len(comments) == 2, (
        "expected the root comment and its reply, found %d" % len(comments)
    )

    parented = [c for c in comments if c.get("parentId")]
    assert len(parented) == 1, (
        "exactly one of the two comments must carry @parentId; %d do"
        % len(parented)
    )
    root_ids = {c.get("id") for c in comments if not c.get("parentId")}
    assert parented[0].get("parentId") in root_ids, (
        "@parentId does not name the other comment"
    )