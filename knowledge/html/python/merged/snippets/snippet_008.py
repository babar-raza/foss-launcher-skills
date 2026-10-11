def test_prescan_limit_1024():
    # <meta charset> appears at byte 1025 — must NOT be detected.
    padding = b" " * 1024
    data = padding + b'<meta charset="windows-1252">'
    assert prescan_meta_charset(data) is None