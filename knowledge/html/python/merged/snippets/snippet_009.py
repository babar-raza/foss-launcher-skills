def test_prescan_no_charset():
    assert prescan_meta_charset(b"<html><body>") is None