def test_ps_to_pdf_from_bytes(self) -> None:
        ps_bytes = b"%!PS-Adobe-3.0\n0 0 moveto 10 0 lineto stroke\n"
        input_payload = McpInput(input_path=None, input_bytes_b64=base64.b64encode(ps_bytes).decode("ascii"))
        output = McpOutput(output_path=None, return_bytes=True)
        result = ps_to_pdf(input_payload, output)
        self.assertIsNotNone(result.output_bytes_b64)
        self.assertTrue(base64.b64decode(result.output_bytes_b64).startswith(b"%PDF"))