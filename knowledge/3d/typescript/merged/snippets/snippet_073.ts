test('test_load_options_properties', () => {
        const options = new ObjLoadOptions();
        
        expect(options.flipCoordinateSystem).toBe(false);
        expect(options.enableMaterials).toBe(true);
        expect(options.scale).toBeCloseTo(1.0);
        expect(options.normalizeNormal).toBe(true);
        
        options.flipCoordinateSystem = true;
        options.enableMaterials = false;
        options.scale = 2.5;
        options.normalizeNormal = false;
        
        expect(options.flipCoordinateSystem).toBe(true);
        expect(options.enableMaterials).toBe(false);
        expect(options.scale).toBeCloseTo(2.5);
        expect(options.normalizeNormal).toBe(false);
    })