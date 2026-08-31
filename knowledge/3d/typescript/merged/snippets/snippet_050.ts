it('testGltfFormatDetection', () => {
        const gltfFormat = FileFormat.getFormatByExtension('.gltf');
        expect(gltfFormat).toBeDefined();
        if (gltfFormat) {
            expect(gltfFormat.extension).toBe('gltf');
            expect(gltfFormat.extensions).toContain('glb');
        }
    })