def test_object_key_derivation():
    """Object-specific key derivation produces 16-byte keys."""
    file_key = os.urandom(16)

    obj_key = EncryptionUtils.derive_object_key(file_key, 10, 0, use_aes=True)
    assert len(obj_key) == 16, "AES object key must be 16 bytes"

    # Different objects get different keys
    obj_key2 = EncryptionUtils.derive_object_key(file_key, 20, 0, use_aes=True)
    assert obj_key != obj_key2