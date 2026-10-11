def test_cff_index_empty():
    empty = CffIndex.from_reader(BinaryReader(b"\x00\x00"))
    assert len(empty) == 0