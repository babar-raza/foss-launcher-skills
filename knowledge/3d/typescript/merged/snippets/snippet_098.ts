it('testSaveOptionsProperties', () => {
        const options = new StlSaveOptions();

        expect(options.flipCoordinateSystem).toBe(false);
        expect(options.binaryMode).toBe(false);
        expect(options.scale).toBe(1.0);

        options.flipCoordinateSystem = true;
        options.binaryMode = true;
        options.scale = 2.5;

        expect(options.flipCoordinateSystem).toBe(true);
        expect(options.binaryMode).toBe(true);
        expect(options.scale).toBe(2.5);
    })