def test_load_nonzero_reserved_throws(self):
        bytes_data = self.build_header_bytes(PsdHeader.PSD_VERSION)
        bytes_data[6] = 1
        stream = io.BytesIO(bytes_data)
        reader = BigEndianReader(stream, leave_open=True)

        with pytest.raises(PsdLoadException):
            PsdHeader.load(reader)