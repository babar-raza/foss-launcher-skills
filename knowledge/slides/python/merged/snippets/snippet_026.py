def test_a_plain_deck_satisfies_every_package_rule(produced):
    """Relationships resolve, targets exist, every part is content-typed."""
    pkg = produced(Presentation())

    pkg.assert_package_is_consistent()