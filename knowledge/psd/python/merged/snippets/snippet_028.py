def test_load_rlefixture_readsimagedata(self):
        with PsdImage.load(self.get_test_data_path("rle.psd")) as image:
            assert image.compression == CompressionMethod.RLE
            assert image.image_data_kind == ImageDataKind.RLE
            assert image.image_data_info.row_length_field_size == 2  # sizeof(ushort)
            assert len(image.image_data_info.row_byte_counts) == 600
            assert image.image_data_info.compressed_payload_length == 5219