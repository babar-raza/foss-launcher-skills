def test_revision_3_key_derivation(random_file_id):
    """R3 key derivation (128-bit) works correctly."""
    o_value = EncryptionUtils.compute_owner_key_v4("owner", "user", 16, revision=3)
    _u_value, key = EncryptionUtils.compute_user_key_v4(
        "user", o_value, -4, random_file_id, 16, revision=3
    )

    assert len(key) == 16, "R3 should produce 128-bit (16-byte) key"