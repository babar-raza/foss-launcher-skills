it('testLoadOptions', () => {
        const options = plugin.createLoadOptions();
        expect(options).toBeInstanceOf(ThreeMfLoadOptions);
        expect(options.flipCoordinateSystem).toBe(false);

        options.flipCoordinateSystem = true;
        expect(options.flipCoordinateSystem).toBe(true);
    })