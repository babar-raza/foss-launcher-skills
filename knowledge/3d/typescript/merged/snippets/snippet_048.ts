it('testGltfLoadOptions', () => {
        const options = new GltfLoadOptions();
        expect(options).toBeDefined();
        expect(options.flipTexCoordV).toBe(true);
    })