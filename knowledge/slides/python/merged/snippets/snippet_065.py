def test_solid_background_on_master(tmp_pptx):
    """Solid-colour background on master slide round-trips."""
    pres = Presentation()
    master = pres.masters[0]
    master.background.type = BackgroundType.OWN_BACKGROUND
    master.background.fill_format.fill_type = FillType.SOLID
    master.background.fill_format.solid_fill_color.color = Color.forest_green

    pres2 = tmp_pptx(pres)
    bg = pres2.masters[0].background
    assert bg.type == BackgroundType.OWN_BACKGROUND
    assert bg.fill_format.fill_type == FillType.SOLID
    c = bg.fill_format.solid_fill_color.color
    assert c.r == 34 and c.g == 139 and c.b == 34
    pres2.dispose()