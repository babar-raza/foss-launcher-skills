describe('TestGltfImport', () => {
    it('testGltfLoadOptions', () => {
        const options = new GltfLoadOptions();
        expect(options).toBeDefined();
        expect(options.flipTexCoordV).toBe(true);
    });

    it('testGltfLoadOptionsFlipProperty', () => {
        const options = new GltfLoadOptions();
        options.flipTexCoordV = false;
        expect(options.flipTexCoordV).toBe(false);
    });

    it('testGltfFormatDetection', () => {
        const gltfFormat = FileFormat.getFormatByExtension('.gltf');
        expect(gltfFormat).toBeDefined();
        if (gltfFormat) {
            expect(gltfFormat.extension).toBe('gltf');
            expect(gltfFormat.extensions).toContain('glb');
        }
    });

    it('testGltfPluginRegistered', () => {
        const ioService = IOService.instance;
        const gltfPlugin = ioService.getPluginForExtension('.gltf');
        expect(gltfPlugin).toBeDefined();
        if (gltfPlugin) {
            expect(gltfPlugin.getConstructorName()).toBe('GltfPlugin');
        }
    });
})