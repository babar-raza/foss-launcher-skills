def test_load_document_dtos_read_values(self):
        test_dir = os.path.join(pytest.config.rootdir, "testdata")
        image_path = os.path.join(test_dir, "test.psd")
        image = PsdImage.load(image_path)

        assert len(image.resources) == 26
        assert image.resources[0].kind == PsdResourceKind.Unknown
        assert image.resources[1].kind == PsdResourceKind.Unknown
        assert image.resources[2].kind == PsdResourceKind.Unknown
        assert image.resources[0].global_angle is None
        assert image.resources[1].global_angle is None
        assert image.resources[2].global_angle is None
        assert image.has_icc_profile is False
        assert image.is_icc_profile_untagged is None
        assert image.global_angle == 0

        assert image.color_data_info.kind == PsdColorDataKind.None_
        assert image.color_data_info.raw_data_length == 0
        assert image.indexed_palette is None

        assert image.image_data_info.kind == ImageDataKind.Rle
        assert image.image_data_info.row_length_field_size == 2  # sizeof(ushort)
        assert len(image.image_data_info.row_byte_counts) == 300
        assert image.image_data_info.compressed_payload_length > 0
        assert image.image_data_info.uses_prediction is False