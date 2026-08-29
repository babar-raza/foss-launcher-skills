def test_file_id_affects_derived_key(random_file_id):
    """Different file IDs produce different encryption keys."""
    file_id1 = os.urandom(16)
    file_id2 = os.urandom(16)

    o_value = EncryptionUtils.compute_owner_key_v4("owner", "user", 16, 4)

    _, key1 = EncryptionUtils.compute_user_key_v4("user", o_value, -4, file_id1, 16, 4)
    _, key2 = EncryptionUtils.compute_user_key_v4("user", o_value, -4, file_id2, 16, 4)

    assert key1 != key2, "Different file IDs should produce different keys"