def test_label_whitespace():
    assert get_canonical_name("  windows-1252  ") == "windows-1252"