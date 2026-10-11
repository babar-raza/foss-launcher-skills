def test_prescan_meta_charset_single_quote():
    assert prescan_meta_charset(b"<meta charset='utf-8'>") == "utf-8"