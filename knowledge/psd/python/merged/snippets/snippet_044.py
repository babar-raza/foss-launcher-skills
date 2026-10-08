def test_load_negativelayerextra_throws(self):
        layer_bytes = bytearray(self.build_layer_record_bytes_with_extra_data(bytes([])))
        self.write_uint32_big_endian(
            layer_bytes, 30, 0xFFFFFFFF
        )

        stream = BytesIO(bytes(layer_bytes))
        reader = BigEndianReader(stream, leave_open=True)

        with pytest.raises(PsdLoadException):
            Layer.load(reader, is_large_document=False)