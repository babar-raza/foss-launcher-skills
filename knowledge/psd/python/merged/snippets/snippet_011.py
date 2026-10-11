def test_load_indexeddata_parsespalette(self):
        payload = self._build_indexed_palette_payload()
        with self._memory_stream(self._build_color_data_section(payload)) as stream:
            with BigEndianReader(stream, leave_open=True) as reader:
                color_data = ColorData.load(reader, ColorModes.INDEXED)

                assert color_data.kind == PsdColorDataKind.INDEXED_PALETTE
                assert color_data.raw_data == payload
                assert color_data.indexed_palette is not None
                assert len(color_data.indexed_palette.entries) == 256
                assert color_data.indexed_palette.entries[0] == (0x00, 0xFF, 0x80)
                assert color_data.indexed_palette.entries[17] == (0x11, 0xEE, 0x91)