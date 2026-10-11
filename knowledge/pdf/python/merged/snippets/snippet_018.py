def test_invalid_key_length_raises():
    """EncryptionUtils should reject invalid AES key lengths."""
    with pytest.raises(Exception, match="AES key must be 16, 24, or 32 bytes"):
        EncryptionUtils.encrypt_aes_cbc(b"short", b"data")
    with pytest.raises(Exception, match="AES key must be 16, 24, or 32 bytes"):
        EncryptionUtils.decrypt_aes_cbc(b"short", b"X" * 20)