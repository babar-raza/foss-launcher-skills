def test_load_nonseekablestream_succeeds(self):
        bytes_data = Path(self.get_test_data_path("test.psd")).read_bytes()
        with self._non_seekable_read_stream(bytes_data) as stream:
            with PsdImage.load(stream) as image:
                assert image.width > 0
                assert len(image.layers) > 0