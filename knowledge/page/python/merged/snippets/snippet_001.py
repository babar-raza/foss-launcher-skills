def test_output_path_for(self):
        input_path = Path("testdata/ps/integration/sample.ps")
        output = output_path_for(input_path, ".pdf")
        self.assertEqual(output.as_posix(), "test-out/ps/integration/sample.pdf")