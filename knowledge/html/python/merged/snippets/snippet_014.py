def test_label_case_insensitive():
    assert get_canonical_name("UTF-8") == "utf-8"