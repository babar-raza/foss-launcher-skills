def test_full_encryption_roundtrip_aes128(random_file_id):
    """Full roundtrip: derive keys, encrypt data, decrypt data."""
    user_pwd = "mypassword"

    # Derive keys
    o_value = EncryptionUtils.compute_owner_key_v4("owner", user_pwd, 16, 4)
    u_value, enc_key = EncryptionUtils.compute_user_key_v4(
        user_pwd, o_value, -4, random_file_id, 16, 4
    )

    # Encrypt some data
    plaintext = b"Confidential PDF content"
    ciphertext = EncryptionUtils.encrypt_aes_cbc(enc_key, plaintext)

    # Verify password and decrypt
    verified_key = EncryptionUtils.verify_password_v4(
        user_pwd, u_value, o_value, -4, random_file_id, 16, 4
    )
    assert verified_key is not None

    decrypted = EncryptionUtils.decrypt_aes_cbc(verified_key, ciphertext)
    assert decrypted == plaintext