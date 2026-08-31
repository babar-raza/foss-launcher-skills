test('triangulate_with_normals', () => {
        const controlPoints = [
            new Vector4(0, 0, 0, 1),
            new Vector4(1, 0, 0, 1),
            new Vector4(0, 1, 0, 1),
            new Vector4(1, 1, 0, 1),
            new Vector4(0.5, 1.5, 0, 1)
        ];

        const quad = [0, 1, 3, 2];
        const norOut: any[] = [];
        const trianglesWithNormals = PolygonModifier.triangulate(controlPoints, [quad], true, [norOut]);
        expect(trianglesWithNormals.length).toBe(2);
        expect(norOut.length).toBe(2);
    })