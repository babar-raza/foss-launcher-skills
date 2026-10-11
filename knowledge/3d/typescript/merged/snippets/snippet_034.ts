it('testSaveOptionsProperties', () => {
        const options = new StlSaveOptions();
        options.exportTextures = true;

        expect(options.exportTextures).toBe(true);
    })