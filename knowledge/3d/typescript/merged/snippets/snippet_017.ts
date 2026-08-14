it('testColladaFormatCanExport', () => {
        const colladaFormat = ColladaFormat;
        expect(colladaFormat.canExport).toBe(true);
    })