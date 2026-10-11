def test_setting_a_hyperlink_is_not_silently_discarded(produced, shape_on_blank_slide):
    """A hyperlink must reach the package, or the caller must be told it cannot."""
    pres, shape = shape_on_blank_slide(with_text="Click me")
    portion_format = shape.text_frame.paragraphs[0].portions[0].portion_format

    raised = None
    try:
        portion_format.hyperlink_click = URL
    except Exception as exc:  # noqa: BLE001 - the type is asserted below
        raised = exc

    pkg = produced(pres)
    links = pkg.findall(SLIDE, "//a:hlinkClick")

    assert raised is not None or links, (
        "assigning a hyperlink was accepted and nothing was written: the saved "
        "slide contains no <a:hlinkClick>, so the link is lost with no error"
    )

    if raised is not None:
        assert isinstance(raised, (NotImplementedError, AttributeError)), (
            "refusing is fine, but the exception must say so; got %r" % (raised,)
        )
        return

    element = links[0]
    rel_id = element.get(qname("r:id"))
    assert rel_id, "<a:hlinkClick> carries no r:id: %r" % dict(element.attrib)

    relationship = pkg.relationship(SLIDE, rel_id)
    assert relationship["type"] == REL_TYPE["hyperlink"]
    assert relationship["mode"] == "External"
    assert relationship["target"] == URL