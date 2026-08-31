it('testSaveOptions', () => {
        const options = plugin.createSaveOptions();
        expect(options).toBeInstanceOf(ThreeMfSaveOptions);
        expect(options.enableCompression).toBe(true);
        expect(options.buildAll).toBe(true);
        expect(options.flipCoordinateSystem).toBe(false);

        options.enableCompression = false;
        expect(options.enableCompression).toBe(false);

        options.flipCoordinateSystem = true;
        expect(options.flipCoordinateSystem).toBe(true);
    })