def test_plugin_registration(self):
        io_service = IOService()
        self.assertEqual(len(io_service._plugins), 6)
        obj_plugin = io_service.get_plugin_for_extension('.obj')
        stl_plugin = io_service.get_plugin_for_extension('.stl')
        gltf_plugin = io_service.get_plugin_for_extension('.gltf')
        threemf_plugin = io_service.get_plugin_for_extension('.3mf')
        fbx_plugin = io_service.get_plugin_for_extension('.fbx')

        self.assertIsNotNone(obj_plugin)
        self.assertIsNotNone(stl_plugin)
        self.assertIsNotNone(gltf_plugin)
        self.assertIsNotNone(threemf_plugin)
        self.assertIsNotNone(fbx_plugin)