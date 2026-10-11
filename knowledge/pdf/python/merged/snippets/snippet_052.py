def test_compute_hash_v5_long_password_truncated(self):
        """Password should be max 127 bytes as per spec (caller responsibility)."""
        # Note: The function expects properly prepared password bytes
        salt = b"12345678"
        long_pwd = b"x" * 127  # Max allowed
        result = EncryptionUtils.compute_hash_v5(long_pwd, salt)
        assert len(result) == 32