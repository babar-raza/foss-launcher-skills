def test_load_psdheader_reads_metadata(self):
        stream = io.BytesIO(self.build_header_bytes(PsdHeader.PSD_VERSION))
        reader = BigEndianReader(stream, leave_open=True)

        header = PsdHeader.load(reader)

        assert header.version == PsdHeader.PSD_VERSION
        assert header.width == 1
        assert header.height == 1
        assert header.channels == 3
        assert header.bit_depth == 8
        assert header.color_mode == ColorModes.RGB