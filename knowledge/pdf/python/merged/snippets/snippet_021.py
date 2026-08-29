def test_empty_data_aes():
    """AES encryption/decryption works with empty data."""
    key = os.urandom(16)
    plaintext = b""
    ciphertext = EncryptionUtils.encrypt_aes_cbc(key, plaintext)
    decrypted = EncryptionUtils.decrypt_aes_cbc(key, ciphertext)
    assert decrypted == plaintext