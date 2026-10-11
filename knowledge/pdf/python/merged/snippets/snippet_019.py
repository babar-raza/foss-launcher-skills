def test_encrypt_decrypt_aes128_roundtrip():
    """Round-trip encryption using 128-bit AES key."""
    key = os.urandom(16)
    plaintext = b"Hello, PDF AES 128!"
    ciphertext = EncryptionUtils.encrypt_aes_cbc(key, plaintext)
    decrypted = EncryptionUtils.decrypt_aes_cbc(key, ciphertext)
    assert decrypted == plaintext