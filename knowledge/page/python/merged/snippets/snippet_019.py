def test_xps_to_image_png_from_file(self) -> None:
        path = Path("testdata/xps/integration/Simple.xps")
        input_payload = McpInput(input_path=str(path), input_bytes_b64=None)
        output = McpOutput(output_path=None, return_bytes=True)
        result = xps_to_image(input_payload, output, McpConversionOptions(format="png", dpi=72))
        self.assertTrue(base64.b64decode(result.output_bytes_b64).startswith(PNG_SIGNATURE))