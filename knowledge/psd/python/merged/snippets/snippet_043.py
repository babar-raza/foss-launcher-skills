def test_load_toolonglayerextra_throws(self):
        layer_bytes = self.build_layer_record_bytes_with_extra_data(
            bytes([0x00, 0x00, 0x00, 0x10, 0x00, 0x00, 0x00, 0x00])
        )
        stream = BytesIO(layer_bytes)
        reader = BigEndianReader(stream, leave_open=True)

        with pytest.raises(PsdLoadException):
            Layer.load(reader, is_large_document=False)