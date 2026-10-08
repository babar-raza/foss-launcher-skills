def test_load_docinspection_reads(self):
        with PsdImage.load(self.get_test_data_path("test.psd")) as image:
            assert image.header is not None
            assert image.is_large_document is False
            assert image.is_psb is False
            assert image.layer_count == 2
            assert image.has_image_resources is True
            assert image.resource_count == 26
            assert image.has_color_mode_data is False
            assert image.has_merged_image_data is True
            assert image.compression == CompressionMethod.RLE
            assert image.image_data_kind == ImageDataKind.RLE
            assert image.uses_prediction is False
            assert image.version == 6
            assert image.header.version == PsdHeader.PSD_VERSION
            assert image.header.color_mode == image.color_mode