def test_compute_user_key_v4_key_length_affects_result(random_file_id):
    """Different key lengths produce different results."""
    o_value = EncryptionUtils.compute_owner_key_v4("owner", "user", 16, 4)
    _, key16 = EncryptionUtils.compute_user_key_v4(
        "user", o_value, -4, random_file_id, 16, 4
    )

    o_value5 = EncryptionUtils.compute_owner_key_v4("owner", "user", 5, 2)
    _, key5 = EncryptionUtils.compute_user_key_v4(
        "user", o_value5, -4, random_file_id, 5, 2
    )

    assert len(key16) == 16
    assert len(key5) == 5