def test_compute_owner_key_v4_produces_32_bytes():
    """compute_owner_key_v4 returns 32-byte O value."""
    o_value = EncryptionUtils.compute_owner_key_v4(
        owner_password="owner", user_password="user", key_length=16, revision=4
    )
    assert len(o_value) == 32, "O value must be 32 bytes"