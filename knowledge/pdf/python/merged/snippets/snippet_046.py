def test_compute_hash_v5_returns_32_bytes(self):
        """Algorithm 2.B must always return exactly 32 bytes."""
        password = b"test"
        salt = os.urandom(8)
        result = EncryptionUtils.compute_hash_v5(password, salt)
        assert len(result) == 32, "compute_hash_v5 must return 32 bytes"