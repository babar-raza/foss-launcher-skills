test('triangulate_with_mesh_multiple_polygons', () => {
        const mesh2 = new Mesh('test_multi');
        (mesh2 as any)._controlPoints = [
            new Vector4(0, 0, 0, 1),
            new Vector4(1, 0, 0, 1),
            new Vector4(0, 1, 0, 1),
            new Vector4(1, 1, 0, 1),
            new Vector4(0.5, 0.5, 1, 1),
            new Vector4(1.5, 0.5, 1, 1),
            new Vector4(0.5, 1.5, 1, 1),
            new Vector4(1.5, 1.5, 1, 1)
        ];
        mesh2.createPolygon(0, 1, 2);
        mesh2.createPolygon(1, 3, 2);
        mesh2.createPolygon(4, 5, 7, 6);
        mesh2.createPolygon(0, 1, 5, 4);
        expect(mesh2.polygonCount).toBe(4);

        const triangulatedMesh2 = PolygonModifier.triangulate(mesh2);
        expect(triangulatedMesh2.polygonCount).toBe(6);
    })