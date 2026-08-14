def test_prescan_meta_charset_double_quote():
    assert prescan_meta_charset(b'<meta charset="windows-1252">') == "windows-1252"