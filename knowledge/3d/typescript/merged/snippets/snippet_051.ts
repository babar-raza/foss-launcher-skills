it('testGltfPluginRegistered', () => {
        const ioService = IOService.instance;
        const gltfPlugin = ioService.getPluginForExtension('.gltf');
        expect(gltfPlugin).toBeDefined();
        if (gltfPlugin) {
            expect(gltfPlugin.getConstructorName()).toBe('GltfPlugin');
        }
    })