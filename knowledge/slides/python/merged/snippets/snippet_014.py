def test_a_table_uses_the_schema_name_for_its_frame_locks(produced):
    """A table's frame locks must be `<a:graphicFrameLocks>`."""
    pres = Presentation()
    pres.slides[0].shapes.add_table(50.0, 50.0, [100.0, 100.0], [40.0, 40.0])
    pkg = produced(pres)

    children = _lock_children(pkg)
    assert INVENTED not in children, (
        "<%s> is not an OOXML element; PowerPoint discards it silently. "
        "children of <p:cNvGraphicFramePr>: %r" % (INVENTED, children)
    )
    assert CORRECT in children, (
        "expected <%s>, found %r" % (CORRECT, children)
    )
    pkg.assert_element(SLIDE, "//a:graphicFrameLocks", attrs={"noGrp": "1"})