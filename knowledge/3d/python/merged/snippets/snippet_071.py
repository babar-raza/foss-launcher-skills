def test_gltf_load_options(self):
        options = GltfLoadOptions()
        self.assertIsNotNone(options)
        self.assertTrue(options.flip_tex_coord_v)