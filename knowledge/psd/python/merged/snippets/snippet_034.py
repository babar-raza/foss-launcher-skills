def test_load_psdzip_readsstructure(self):
        with io.BytesIO(
            self._build_image_data_section(
                CompressionMethod.ZIP_WITHOUT_PREDICTION,
                bytes([0x78, 0x9C, 0x63, 0x60, 0x04, 0x00, 0x00, 0xFF, 0x00]),
            )
        ) as stream:
            with BigEndianReader(stream, leave_open=True) as reader:
                image_data = ImageData.load(
                    reader, is_large_document=False, height=1, channel_count=3
                )

                assert image_data.compression == CompressionMethod.ZIP_WITHOUT_PREDICTION
                assert image_data.structure.kind == ImageDataKind.ZIP
                assert image_data.structure.uses_prediction is False
                assert image_data.structure.compressed_payload_length == 9