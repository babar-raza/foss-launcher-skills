def test_compute_owner_key_v4_empty_owner_uses_user():
    """Empty owner password defaults to user password."""
    o1 = EncryptionUtils.compute_owner_key_v4("", "user", 16, 4)
    o2 = EncryptionUtils.compute_owner_key_v4("user", "user", 16, 4)
    assert o1 == o2, "Empty owner password should use user password"