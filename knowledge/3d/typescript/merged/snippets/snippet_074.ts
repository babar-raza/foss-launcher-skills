test('test_plugin_registration', () => {
        const ioService = IOService.instance;
        
        const objPlugin = ioService.getPluginForExtension('.obj');
        const stlPlugin = ioService.getPluginForExtension('.stl');
        const gltfPlugin = ioService.getPluginForExtension('.gltf');
        const threeMfPlugin = ioService.getPluginForExtension('.3mf');
        const fbxPlugin = ioService.getPluginForExtension('.fbx');
        
        expect(objPlugin).not.toBeNull();
        expect(stlPlugin).not.toBeNull();
        expect(gltfPlugin).not.toBeNull();
        expect(threeMfPlugin).not.toBeNull();
        expect(fbxPlugin).not.toBeNull();
    })