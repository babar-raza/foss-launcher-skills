test('triangulate_with_just_control_points', () => {
        const controlPoints = [
            new Vector4(0, 0, 0, 1),
            new Vector4(1, 0, 0, 1),
            new Vector4(0, 1, 0, 1),
            new Vector4(1, 1, 0, 1),
            new Vector4(0.5, 1.5, 0, 1)
        ];

        const emptyTriangles = PolygonModifier.triangulate(controlPoints);
        expect(emptyTriangles.length).toBe(0);
    })