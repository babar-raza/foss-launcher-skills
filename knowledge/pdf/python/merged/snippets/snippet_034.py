def test_generate_file_id():
    """generate_file_id produces unique 16-byte IDs."""
    id1 = EncryptionUtils.generate_file_id()
    id2 = EncryptionUtils.generate_file_id()

    assert len(id1) == 16
    assert len(id2) == 16
    assert id1 != id2