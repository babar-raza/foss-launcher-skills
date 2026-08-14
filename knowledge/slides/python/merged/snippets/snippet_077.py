def test_effective_inherits_from_layout():
    """Slide with NOT_DEFINED bg inherits from layout before master."""
    pres = Presentation()

    # Set master to blue
    master = pres.masters[0]
    master.background.type = BackgroundType.OWN_BACKGROUND
    master.background.fill_format.fill_type = FillType.SOLID
    master.background.fill_format.solid_fill_color.color = Color.blue

    # Set layout to red — should take priority
    layout = pres.slides[0].layout_slide
    layout.background.type = BackgroundType.OWN_BACKGROUND
    layout.background.fill_format.fill_type = FillType.SOLID
    layout.background.fill_format.solid_fill_color.color = Color.red

    eff = pres.slides[0].background.get_effective()
    assert eff.fill_format.fill_type == FillType.SOLID
    c = eff.fill_format.solid_fill_color
    assert c.r == 255 and c.g == 0 and c.b == 0
    pres.dispose()