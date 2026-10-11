def test_a_table_leaves_the_package_consistent(produced):
    """Relationships and content types stay resolvable when a table is added."""
    pres = Presentation()
    pres.slides[0].shapes.add_table(50.0, 50.0, [100.0, 100.0], [40.0, 40.0])
    pkg = produced(pres)

    pkg.assert_package_is_consistent()