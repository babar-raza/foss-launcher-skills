it('testColladaLoadOptions', () => {
        const options = new ColladaLoadOptions();

        expect(options.flipCoordinateSystem).toBe(false);
        expect(options.enableMaterials).toBe(true);
        expect(options.scale).toBe(1.0);
        expect(options.normalizeNormal).toBe(true);

        options.flipCoordinateSystem = true;
        expect(options.flipCoordinateSystem).toBe(true);

        options.scale = 2.0;
        expect(options.scale).toBe(2.0);
    })