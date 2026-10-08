def test_load_layer_dtos_read_values(self):
        test_dir = os.path.join(pytest.config.rootdir, "testdata")
        image_path = os.path.join(test_dir, "test.psd")
        image = PsdImage.load(image_path)
        layer: Layer = image.layers[0]

        assert len(layer.channels) == 4
        assert layer.channels[0].channel_id == -1
        assert layer.channels[1].channel_id == 0
        assert layer.channels[2].channel_id == 1
        assert layer.channels[3].channel_id == 2
        assert layer.channels[0].data_length > 0

        assert layer.mask_info.is_present is False
        assert layer.mask_info.raw_data_length == 4
        assert layer.blending_ranges_info.is_present is True
        assert layer.blending_ranges_info.raw_data_length == 44