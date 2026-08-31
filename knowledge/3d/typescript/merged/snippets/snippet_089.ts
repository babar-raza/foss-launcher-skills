test('triangulate_with_control_points_and_polygon_size', () => {
        const controlPoints = [
            new Vector4(0, 0, 0, 1),
            new Vector4(1, 0, 0, 1),
            new Vector4(0, 1, 0, 1),
            new Vector4(1, 1, 0, 1),
            new Vector4(0.5, 1.5, 0, 1)
        ];

        const fromSizeTriangles = PolygonModifier.triangulate(controlPoints, 4);
        expect(fromSizeTriangles.length).toBe(2);
    })