def test_load_basicpsb_readsmetadata(self):
        with PsdImage.load(self.get_test_data_path("basic.psb")) as image:
            assert image.version == 6
            assert image.header.version == PsdHeader.PSB_VERSION
            assert image.is_large_document is True
            assert image.is_psb is True
            assert image.width == 200
            assert image.height == 200
            assert image.layer_count == 0
            assert image.resource_count == 24
            assert image.compression == CompressionMethod.RLE
            assert image.image_data_info.row_length_field_size == 4  # sizeof(uint)