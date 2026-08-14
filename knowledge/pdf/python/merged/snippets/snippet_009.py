def test_compute_owner_key_v4_different_passwords():
    """Different owner passwords produce different O values."""
    o1 = EncryptionUtils.compute_owner_key_v4("owner1", "user", 16, 4)
    o2 = EncryptionUtils.compute_owner_key_v4("owner2", "user", 16, 4)
    assert o1 != o2, "Different passwords should produce different O values"