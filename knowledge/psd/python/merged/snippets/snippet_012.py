def test_load_cmykpayload_classifies(self):
        payload = bytes([0xCA, 0xFE, 0xBA, 0xBE])
        with self._memory_stream(self._build_color_data_section(payload)) as stream:
            with BigEndianReader(stream, leave_open=True) as reader:
                color_data = ColorData.load(reader, ColorModes.CMYK)

                assert color_data.kind == PsdColorDataKind.CMYK_PAYLOAD
                assert color_data.raw_data == payload
                assert color_data.indexed_palette is None