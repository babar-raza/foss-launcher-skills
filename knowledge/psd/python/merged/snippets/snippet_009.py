def test_load_toolongcolormode_throws(self):
        bytes_data = bytearray(
            Path(self.get_test_data_path("test.psd")).read_bytes()
        )
        self._write_uint32_big_endian(bytes_data, 26, 100000)

        with pytest.raises(PsdLoadException):
            with self._memory_stream(bytes_data) as stream:
                PsdImage.load(stream)