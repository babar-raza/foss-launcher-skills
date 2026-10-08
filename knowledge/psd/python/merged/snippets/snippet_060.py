def test_load_seekable_preservesposition(self):
        bytes_data = Path(self.get_test_data_path("test.psd")).read_bytes()
        prefix = bytes([1, 2, 3, 4, 5])
        stream = io.BytesIO()
        stream.write(prefix)
        stream.write(bytes_data)
        stream.seek(len(prefix))

        with PsdImage.load(stream) as image:
            assert stream.tell() == len(prefix)
            assert image.width > 0