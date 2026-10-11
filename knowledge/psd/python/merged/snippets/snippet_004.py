def test_layermask_officialshape_reads(self):
        with Image.load(self.get_test_data_path("test.psd")) as img:
            psd_image = img
            layer = psd_image.layers[0]

            assert layer.layer_mask_data is None
            assert layer.layer_blending_ranges_data.length == 40
            with pytest.raises(NotSupportedException):
                layer.layer_mask_data = None
            with pytest.raises(NotSupportedException):
                layer.layer_blending_ranges_data = LayerBlendingRangesData()