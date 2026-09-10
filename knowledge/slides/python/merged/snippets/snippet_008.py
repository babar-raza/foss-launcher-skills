def test_the_classic_comment_carries_the_extension_powerpoint_reads(produced):
    """`p15:threadingInfo` on the classic `p:cm` is what renders the reply.

    The modern part alone is not enough.  PowerPoint takes the parent from the
    `p15:threadingInfo/p15:parentCm` extension on the *classic* list; a file
    that has a correct `ppt/threadedComments/` part and no extension opens
    without complaint and shows two independent flat comments, which is the
    worst shape this defect can take — the thread is lost and nothing says so.
    """
    pres = Presentation()
    author = pres.comment_authors.add_author("Alice", "A")
    slide = pres.slides[0]
    when = datetime.datetime(2026, 1, 15, 12, 0, 0)
    root = author.comments.add_comment("Please review", slide, PointF(2.0, 3.0), when)
    reply = author.comments.add_comment("Reviewed", slide, PointF(2.0, 3.0), when)
    reply.parent_comment = root

    pkg = produced(pres)

    comments = pkg.findall(CLASSIC, "//p:cmLst/p:cm")
    assert len(comments) == 2, "expected two classic comments, found %d" % len(comments)

    parents = pkg.findall(
        CLASSIC,
        "//p:cm/p:extLst/p:ext[@uri='%s']/p15:threadingInfo/p15:parentCm"
        % THREADING_INFO_URI,
    )
    assert len(parents) == 1, (
        "exactly one classic comment must carry p15:threadingInfo/p15:parentCm; "
        "%d do, so PowerPoint has nothing to build the thread from.\n%s"
        % (len(parents), pkg.text(CLASSIC))
    )

    parent = parents[0]
    roots = [c for c in comments if not c.findall(".//{*}parentCm")]
    assert len(roots) == 1, "exactly one comment must be a thread root"
    assert parent.get("authorId") == roots[0].get("authorId"), (
        "p15:parentCm/@authorId is %r but the root comment's is %r"
        % (parent.get("authorId"), roots[0].get("authorId"))
    )
    assert parent.get("idx") == roots[0].get("idx"), (
        "p15:parentCm/@idx is %r but the root comment's is %r"
        % (parent.get("idx"), roots[0].get("idx"))
    )

    # `parentCmId` is not in CT_Comment and no consumer renders it.
    for comment in comments:
        assert "parentCmId" not in comment.attrib, (
            "the invalid parentCmId attribute is back on <p:cm>: %r"
            % dict(comment.attrib)
        )