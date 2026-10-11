def test_load_missingfile_throws(self):
        missing_file = "missing.psd"
        with pytest.raises(FileNotFoundError):
            PsdImage.load(str(missing_file))