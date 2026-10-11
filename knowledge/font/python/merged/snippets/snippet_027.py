def test_dict_to_bytes_serializes_top_dict_operator():
    d = CffDict()
    d.set(TopDictOp.CHARSTRINGS, [1234])
    out = d.to_bytes()
    parsed = CffDict.from_bytes(out)
    assert parsed.get(TopDictOp.CHARSTRINGS) == [1234]