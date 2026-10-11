def test_channels_officialshape_readsonly(self):
        with Image.load(self.get_test_data_path("test.psd")) as img:
            psd_image = img
            layer = psd_image.layers[0]

            channel_information = layer.channel_information

            assert layer.channels_count == len(channel_information)
            assert channel_information
            assert channel_information[0].length > 0
            with pytest.raises(NotSupportedException):
                layer.channel_information = channel_information