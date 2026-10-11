def test_all_conversions(self):
        """Convert each input format to every output format."""
        for in_label, in_file in INPUT_FILES.items():
            for out_ext, out_fmt in ALL_OUTPUT_FORMATS.items():
                out_file = f"ConvertDocument.{in_label}_to_{out_ext}.{out_ext}"
                self.convert(in_file, out_file, save_format=out_fmt)