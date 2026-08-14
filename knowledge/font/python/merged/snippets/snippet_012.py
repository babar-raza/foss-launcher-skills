def test_cff_font_name_nonempty(opensans_cff):
    assert opensans_cff.font_name.strip() != ""