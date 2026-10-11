def test_load_invalid_header_field_throws(
        self, channels, width, height, bit_depth, color_mode
    ):
        bytes_data = self.build_header_bytes(
            PsdHeader.PSD_VERSION, channels, width, height, bit_depth, color_mode
        )
        stream = io.BytesIO(bytes_data)
        reader = BigEndianReader(stream, leave_open=True)

        with pytest.raises(PsdLoadException):
            PsdHeader.load(reader)