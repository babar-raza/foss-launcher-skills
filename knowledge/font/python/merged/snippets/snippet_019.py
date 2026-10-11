def test_dict_integer_encoding():
    # 139 -> 0, 140 -> 1, 21 -> operator, thus op 21 has [0, 1]
    d = CffDict.from_bytes(bytes([139, 140, 21]))
    assert d.get(21) == [0, 1]