def test_gltf_format_can_export(self):
        from aspose.threed.formats.gltf import GltfFormat

        gltf_format = GltfFormat()
        self.assertTrue(gltf_format.can_export)