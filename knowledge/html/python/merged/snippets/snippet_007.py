def test_prescan_http_equiv():
    data = b'<meta http-equiv="Content-Type" content="text/html; charset=gbk">'
    assert prescan_meta_charset(data) == "gbk"