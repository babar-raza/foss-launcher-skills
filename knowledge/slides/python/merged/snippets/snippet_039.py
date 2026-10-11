def test_a_transition_is_written_after_the_colour_map_override(produced, transition):
    """`<p:transition>` must follow `<p:clrMapOvr>`, not precede it."""
    pres = Presentation()
    pres.slides[0].slide_show_transition.type = transition
    pkg = produced(pres)

    root = pkg.xml(SLIDE)
    order = child_names(root)
    assert "p:transition" in order, "no <p:transition> was written: %r" % order

    pkg.assert_element(SLIDE, "/p:sld", child_order=True)