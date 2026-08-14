def test_dict_real_encoding():
    # 30 1.5F then operator 21
    d = CffDict.from_bytes(bytes([30, 0x1A, 0x5F, 21]))
    vals = d.get(21)
    assert vals is not None
    assert vals[0] == pytest.approx(1.5)