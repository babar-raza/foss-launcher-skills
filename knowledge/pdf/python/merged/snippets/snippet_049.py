def test_compute_hash_v5_empty_password(self):
        """Empty password should work without exception."""
        salt = b"12345678"
        result = EncryptionUtils.compute_hash_v5(b"", salt)
        assert len(result) == 32