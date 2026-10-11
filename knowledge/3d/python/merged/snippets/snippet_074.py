def test_gltf_format_properties(self):
        from aspose.threed.formats.gltf import GltfFormat

        gltf_format = GltfFormat()
        self.assertTrue(gltf_format.can_import)
        self.assertTrue(gltf_format.can_export)
        self.assertEqual(gltf_format.version, '2.0')
        self.assertIn('gltf', gltf_format.extensions)
        self.assertIn('glb', gltf_format.extensions)