def test_aes256_key_derivation_roundtrip(self):
        """Full V5/R6 key derivation and verification roundtrip.

        Create encryption values, then verify password works.
        """
        password = "SecurePassword123"

        # Generate random values as would be in a real PDF
        _ = os.urandom(16)  # file_id
        file_key = os.urandom(32)  # The random file encryption key

        # Generate user validation and key salts
        u_val_salt = os.urandom(8)
        u_key_salt = os.urandom(8)

        pwd_bytes = password.encode("utf-8")[:127]

        # Compute U hash (validation)
        u_hash = EncryptionUtils.compute_hash_v5(pwd_bytes, u_val_salt, b"")

        # Compute intermediate key for encrypting file key
        intermediate = EncryptionUtils.compute_hash_v5(pwd_bytes, u_key_salt, b"")

        # Encrypt file key with intermediate key (AES-256-CBC, zero IV)
        zero_iv = bytes(16)
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

        cipher = Cipher(algorithms.AES(intermediate), modes.CBC(zero_iv))
        encryptor = cipher.encryptor()
        ue_value = encryptor.update(file_key) + encryptor.finalize()

        # U value format: hash (32) + val_salt (8) + key_salt (8) = 48 bytes
        _ = u_hash + u_val_salt + u_key_salt  # u_value

        # Now verify: compute hash with val_salt and compare to stored hash
        verify_hash = EncryptionUtils.compute_hash_v5(pwd_bytes, u_val_salt, b"")
        assert verify_hash == u_hash, "Password verification should match"

        # Derive key and decrypt UE
        derived_intermediate = EncryptionUtils.compute_hash_v5(
            pwd_bytes, u_key_salt, b""
        )
        cipher = Cipher(algorithms.AES(derived_intermediate), modes.CBC(zero_iv))
        decryptor = cipher.decryptor()
        recovered_key = decryptor.update(ue_value) + decryptor.finalize()

        assert recovered_key == file_key, "Recovered file key should match original"