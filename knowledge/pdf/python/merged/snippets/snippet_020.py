def test_encrypt_decrypt_aes256_roundtrip():
    """Round-trip encryption using 256-bit AES key."""
    key = os.urandom(32)
    plaintext = b"Hello, PDF AES 256!"
    ciphertext = EncryptionUtils.encrypt_aes_cbc(key, plaintext)
    decrypted = EncryptionUtils.decrypt_aes_cbc(key, ciphertext)
    assert decrypted == plaintext