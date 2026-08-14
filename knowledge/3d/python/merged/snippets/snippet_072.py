def test_gltf_load_options_flip_property(self):
        options = GltfLoadOptions()
        options.flip_tex_coord_v = False
        self.assertFalse(options.flip_tex_coord_v)