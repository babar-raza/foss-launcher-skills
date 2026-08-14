def test_gltf_format_detection(self):
        from aspose.threed import FileFormat

        gltf_format = FileFormat.get_format_by_extension('.gltf')
        self.assertIsNotNone(gltf_format)
        self.assertEqual(gltf_format.extension, 'gltf')

        glb_format = FileFormat.get_format_by_extension('.glb')
        self.assertIsNotNone(glb_format)