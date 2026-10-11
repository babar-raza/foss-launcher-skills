def test_ps_to_image_png_from_bytes(self) -> None:
        ps_bytes = b"%!PS-Adobe-3.0\nnewpath 10 10 moveto 100 10 lineto stroke\nshowpage\n"
        input_payload = McpInput(input_path=None, input_bytes_b64=base64.b64encode(ps_bytes).decode("ascii"))
        output = McpOutput(output_path=None, return_bytes=True)
        result = ps_to_image(input_payload, output, McpConversionOptions(format="png", dpi=72))
        self.assertIsNotNone(result.output_bytes_b64)
        self.assertTrue(base64.b64decode(result.output_bytes_b64).startswith(PNG_SIGNATURE))