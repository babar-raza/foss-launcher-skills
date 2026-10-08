def test_load_resourcesfixture_reads(self):
        image = PsdImage.load(self.get_test_data_path("resources.psd"))

        assert image.resource_count == 28
        assert image.resources[0].kind == PsdResourceKind.UNKNOWN
        assert image.has_image_resources is True
        assert len(image.layers) == 3