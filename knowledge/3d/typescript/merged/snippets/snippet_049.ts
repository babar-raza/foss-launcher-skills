it('testGltfLoadOptionsFlipProperty', () => {
        const options = new GltfLoadOptions();
        options.flipTexCoordV = false;
        expect(options.flipTexCoordV).toBe(false);
    })