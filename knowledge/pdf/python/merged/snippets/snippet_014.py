def test_permissions_affect_derived_key(random_file_id):
    """Different permissions produce different encryption keys."""
    o_value = EncryptionUtils.compute_owner_key_v4("owner", "user", 16, 4)

    _, key1 = EncryptionUtils.compute_user_key_v4(
        "user", o_value, -4, random_file_id, 16, 4
    )
    _, key2 = EncryptionUtils.compute_user_key_v4(
        "user", o_value, -100, random_file_id, 16, 4
    )

    assert key1 != key2, "Different permissions should produce different keys"