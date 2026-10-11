def test_compute_hash_v5_different_password(self):
        """Different passwords produce different hashes."""
        salt = b"12345678"
        result1 = EncryptionUtils.compute_hash_v5(b"pass1", salt)
        result2 = EncryptionUtils.compute_hash_v5(b"pass2", salt)
        assert result1 != result2, "Different passwords must produce different hashes"