def test_compute_hash_v5_deterministic(self):
        """Same inputs produce same output (deterministic)."""
        password = b"password"
        salt = b"12345678"
        result1 = EncryptionUtils.compute_hash_v5(password, salt)
        result2 = EncryptionUtils.compute_hash_v5(password, salt)
        assert result1 == result2, "Same inputs must produce same hash"