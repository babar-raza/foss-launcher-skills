def test_gltf_plugin_registered(self):
        from aspose.threed.formats import IOService
        from aspose.threed.formats.gltf import GltfPlugin

        io_service = IOService()
        gltf_plugin = io_service.get_plugin_for_extension('.gltf')
        self.assertIsNotNone(gltf_plugin)
        self.assertIsInstance(gltf_plugin, GltfPlugin)