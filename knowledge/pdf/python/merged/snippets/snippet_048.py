def test_compute_hash_v5_different_salt(self):
        """Different salts produce different hashes."""
        password = b"password"
        salt1 = b"salt1___"
        salt2 = b"salt2___"
        result1 = EncryptionUtils.compute_hash_v5(password, salt1)
        result2 = EncryptionUtils.compute_hash_v5(password, salt2)
        assert result1 != result2, "Different salts must produce different hashes"