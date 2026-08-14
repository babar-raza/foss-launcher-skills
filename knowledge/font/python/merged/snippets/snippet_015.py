def test_cff_charset_resolves_gid1(opensans_cff):
    name = opensans_cff.charset.name_for(1)
    assert isinstance(name, str)
    assert name.strip() != ""