it('testSaveOptionsCreation', () => {
        const options = new StlSaveOptions();
        expect(options).toBeDefined();
        expect(options.exportTextures).toBe(false);
    })