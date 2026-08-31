test('test_obj_format_detection', () => {
        const objFormat = new ObjFormat();
        expect(objFormat.canImport).toBe(true);
        expect(objFormat.canExport).toBe(false);
        expect(objFormat.extension).toBe("obj");
        expect(objFormat.extensions).toContain("obj");
    })