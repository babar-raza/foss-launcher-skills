def test_load_psbheader_reads_metadata(self):
        stream = io.BytesIO(self.build_header_bytes(PsdHeader.PSB_VERSION))
        reader = BigEndianReader(stream, leave_open=True)

        header = PsdHeader.load(reader)

        assert header.version == PsdHeader.PSB_VERSION
        assert header.is_large_document is True
        assert header.width == 1
        assert header.height == 1
        assert header.channels == 3