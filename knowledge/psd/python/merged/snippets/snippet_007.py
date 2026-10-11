def test_resources_officialshape_reads(self):
        with Image.load(self.get_test_data_path("test.psd")) as img:
            psd_image = img

            image_resources = psd_image.image_resources
            global_layer_resources = psd_image.global_layer_resources
            global_layer_mask_info = psd_image.global_layer_mask_info
            active_layer = psd_image.active_layer

            assert psd_image.size == Size(psd_image.width, psd_image.height)
            assert image_resources
            assert image_resources[0].id != 0
            assert image_resources[0].data_size >= 0
            assert not global_layer_resources
            assert global_layer_mask_info is not None
            assert active_layer is psd_image.layers[0]
            assert psd_image.is_flatten is False
            assert psd_image.has_transparency_data is False

            with pytest.raises(NotSupportedException):
                psd_image.image_resources = image_resources
            with pytest.raises(NotSupportedException):
                psd_image.global_layer_resources = global_layer_resources
            with pytest.raises(NotSupportedException):
                psd_image.active_layer = active_layer
            with pytest.raises(NotSupportedException):
                psd_image.has_transparency_data = True