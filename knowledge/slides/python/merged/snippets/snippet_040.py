def test_a_transition_leaves_the_package_consistent(produced):
    """Adding a transition must not break relationships or content types."""
    pres = Presentation()
    pres.slides[0].slide_show_transition.type = TransitionType.FADE
    pkg = produced(pres)

    pkg.assert_package_is_consistent()