def test_compute_hash_v5_uses_multiple_hash_algorithms(self):
        """Algorithm should use different hash algorithms based on intermediate values.

        While we can't directly observe which hash is used, we verify that:
        1. Output is correct length
        2. Various inputs work (exercising different code paths)
        """
        # Test with many different inputs to exercise different hash algorithm selections
        for i in range(10):
            password = f"test{i}".encode()
            salt = os.urandom(8)
            result = EncryptionUtils.compute_hash_v5(password, salt)
            assert len(result) == 32