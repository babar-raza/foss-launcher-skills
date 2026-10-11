def test_load_layeredpsb_readslayers(self):
        with PsdImage.load(self.get_test_data_path("layered.psb")) as image:
            assert image.version == 6
            assert image.header.version == PsdHeader.PSB_VERSION
            assert image.layer_count == 3
            assert image.layers[0].name == "Background"
            assert image.layers[1].name == "Rectangle 1"
            assert image.layers[2].name == "Ellipse 1"
            assert image.layers[2].opacity == 191