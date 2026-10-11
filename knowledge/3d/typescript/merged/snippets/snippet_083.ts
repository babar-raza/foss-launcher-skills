test('triangulate_with_single_polygon', () => {
        const controlPoints = [
            new Vector4(0, 0, 0, 1),
            new Vector4(1, 0, 0, 1),
            new Vector4(0, 1, 0, 1),
            new Vector4(1, 1, 0, 1),
            new Vector4(0.5, 1.5, 0, 1)
        ];

        const triangle = [0, 1, 2];
        const singleTriangle = PolygonModifier.triangulate(controlPoints, [triangle]);
        expect(singleTriangle.length).toBe(1);

        const quad = [0, 1, 3, 2];
        const quadTriangles = PolygonModifier.triangulate(controlPoints, [quad]);
        expect(quadTriangles.length).toBe(2);
    })