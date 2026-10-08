def test_load_psbrle_readsstructure(self):
        with io.BytesIO(
            self._build_image_data_section(
                CompressionMethod.RLE,
                bytes(
                    [
                        0x00, 0x00, 0x00, 0x02,
                        0x00, 0x00, 0x00, 0x01,
                        0x00, 0x00, 0x00, 0x03,
                        0xAB, 0xCD, 0xEF, 0x10, 0x11, 0x12,
                    ]
                ),
            )
        ) as stream:
            with BigEndianReader(stream, leave_open=True) as reader:
                image_data = ImageData.load(
                    reader, is_large_document=True, height=1, channel_count=3
                )

                assert image_data.compression == CompressionMethod.RLE
                assert image_data.structure.kind == ImageDataKind.RLE
                assert image_data.structure.row_length_field_size == 4  # sizeof(uint)
                assert len(image_data.structure.row_byte_counts) == 3
                assert image_data.structure.row_byte_counts[0] == 2
                assert image_data.structure.row_byte_counts[1] == 1
                assert image_data.structure.row_byte_counts[2] == 3
                assert image_data.structure.compressed_payload_length == 6