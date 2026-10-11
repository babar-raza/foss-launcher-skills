def test_unsupported_file_format_exception_exposes_read_only_enum(self) -> None:
        from aspose.note import FileFormat, UnsupportedFileFormatException

        error = UnsupportedFileFormatException(file_format="bogus-guid")
        self.assertIs(error.FileFormat, FileFormat.Unknown)

        with self.assertRaises(AttributeError):
            setattr(error, "FileFormat", FileFormat.OneNote2007)