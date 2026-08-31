it('testExportFormatSupport', () => {
        const stlFormat = StlFormat;
        expect(stlFormat.canExport).toBe(true);
        expect(stlFormat.canImport).toBe(true);
    })