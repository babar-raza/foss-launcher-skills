def test_compute_user_key_v4_returns_tuple(random_file_id):
    """compute_user_key_v4 returns (U value, encryption key)."""
    o_value = EncryptionUtils.compute_owner_key_v4("owner", "user", 16, 4)
    u_value, enc_key = EncryptionUtils.compute_user_key_v4(
        password="user",
        o_value=o_value,
        p_value=-4,
        file_id=random_file_id,
        key_length=16,
        revision=4,
    )
    assert len(u_value) == 32, "U value must be 32 bytes"
    assert len(enc_key) == 16, "Encryption key must be 16 bytes for AES-128"