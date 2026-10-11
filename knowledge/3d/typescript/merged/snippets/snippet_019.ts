it('testColladaSaveOptions', () => {
        const options = new ColladaSaveOptions();

        expect(options.flipCoordinateSystem).toBe(false);
        expect(options.enableMaterials).toBe(true);
        expect(options.indented).toBe(true);

        options.flipCoordinateSystem = true;
        expect(options.flipCoordinateSystem).toBe(true);

        options.indented = false;
        expect(options.indented).toBe(false);
    })