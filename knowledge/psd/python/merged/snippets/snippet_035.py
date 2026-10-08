def test_load_truncatedrlerows_throws(self):
        with io.BytesIO(
            self._build_image_data_section(
                CompressionMethod.RLE,
                bytes([0x00, 0x02, 0xAB, 0xCD, 0x00]),
            )
        ) as stream:
            with BigEndianReader(stream, leave_open=True) as reader:
                with pytest.raises(PsdLoadException):
                    ImageData.load(
                        reader, is_large_document=False, height=1, channel_count=3
                    )