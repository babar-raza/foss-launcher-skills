def test_save_roundtrip_is_byte_exact(self):
        test_file = os.path.join(os.path.dirname(__file__), "testdata", "test.psd")
        output_file = self.get_persistent_artifact_path("roundtrip_byteexact_test.psd")

        with open(test_file, "rb") as f:
            original_bytes = f.read()

        with PsdImage.load(test_file) as image:
            image.save(output_file)
            self.log_artifact_directory(output_file)

        with open(output_file, "rb") as f:
            saved_bytes = f.read()

        assert len(saved_bytes) == len(original_bytes), (
            "Round-trip output file length must match original file length."
        )

        for i in range(len(original_bytes)):
            assert saved_bytes[i] == original_bytes[i], (
                f"Byte mismatch at position {i}: expected "
                f"{original_bytes[i]:02X}, got {saved_bytes[i]:02X}"
            )