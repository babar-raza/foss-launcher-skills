it('testFormatDetection', () => {
        expect(format.extension).toBe('3mf');
        expect(format.extensions).toContain('3mf');
        expect(format.canImport).toBe(true);
        expect(format.canExport).toBe(true);
    })