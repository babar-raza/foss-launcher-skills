def test_eps_metadata_extracts_fields(self) -> None:
        eps_bytes = b"%!PS-Adobe-3.0 EPSF-3.0\n%%BoundingBox: 0 0 10 20\n%%Title: Sample\n"
        input_payload = McpInput(input_path=None, input_bytes_b64=base64.b64encode(eps_bytes).decode("ascii"))
        meta = eps_metadata(input_payload)
        self.assertEqual(meta.get("bounding_box"), (0, 0, 10, 20))
        self.assertEqual(meta.get("title"), "Sample")