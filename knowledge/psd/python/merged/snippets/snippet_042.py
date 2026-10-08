def test_load_toolonglayermask_throws(self):
        path = self.get_test_data_path("test.psd")

        with open(path, "rb") as f:
            bytes_data = bytearray(f.read())

        color_mode_length = BigEndianBitConverter.to_int32(bytes_data, 26)
        resources_length_offset = 26 + 4 + color_mode_length
        resources_payload_length = BigEndianBitConverter.to_int32(
            bytes_data, resources_length_offset
        )
        layer_and_mask_length_offset = (
            resources_length_offset + 4 + resources_payload_length
        )
        self.write_uint32_big_endian(
            bytes_data, layer_and_mask_length_offset, 100000
        )
        stream = BytesIO(bytes(bytes_data))

        with pytest.raises(PsdLoadException):
            PsdImage.load(stream)