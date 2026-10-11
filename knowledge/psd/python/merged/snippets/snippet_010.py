def test_load_rgbpayload_classifies(self):
        payload = bytes([0x10, 0x20, 0x30, 0x40])
        with self._memory_stream(self._build_color_data_section(payload)) as stream:
            with BigEndianReader(stream, leave_open=True) as reader:
                color_data = ColorData.load(reader, ColorModes.RGB)

                assert color_data.kind == PsdColorDataKind.RGB_PAYLOAD
                assert color_data.raw_data == payload
                assert color_data.indexed_palette is None