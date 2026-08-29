def test_revision_2_key_derivation(random_file_id):
    """R2 key derivation (40-bit RC4) works correctly."""
    o_value = EncryptionUtils.compute_owner_key_v4("owner", "user", 5, revision=2)
    u_value, key = EncryptionUtils.compute_user_key_v4(
        "user", o_value, -4, random_file_id, 5, revision=2
    )

    assert len(key) == 5, "R2 should produce 40-bit (5-byte) key"
    assert len(u_value) == 32, "U value always 32 bytes"