test('triangulate_with_control_points_and_polygons', () => {
        const controlPoints = [
            new Vector4(0, 0, 0, 1),
            new Vector4(1, 0, 0, 1),
            new Vector4(0, 1, 0, 1),
            new Vector4(1, 1, 0, 1),
            new Vector4(0.5, 1.5, 0, 1)
        ];

        const triangle = [0, 1, 2];
        const quad = [0, 1, 3, 2];
        const pentagon = [0, 1, 3, 4, 2];

        const triangles = PolygonModifier.triangulate(controlPoints, [triangle, quad, pentagon]);
        expect(triangles.length).toBe(6);
    })