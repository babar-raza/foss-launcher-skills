def test_read_aligned4_consumes_padding(self):
        stream = io.BytesIO(bytes([0x00, 0x00, 0x00, 0x00, 0x7F]))
        reader = BigEndianReader(stream, leave_open=True)

        value = reader.read_pascal_string_aligned_to4()

        assert value == ''
        assert reader.position == 4
        assert reader.read_byte() == 0x7F