def test_compute_hash_v5_with_user_key(self):
        """User key affects the hash result."""
        password = b"password"
        salt = b"12345678"
        user_key = os.urandom(48)

        result_without = EncryptionUtils.compute_hash_v5(password, salt, b"")
        result_with = EncryptionUtils.compute_hash_v5(password, salt, user_key)

        assert result_without != result_with, "User key must affect hash"