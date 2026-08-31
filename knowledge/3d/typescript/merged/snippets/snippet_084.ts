test('triangulate_with_mesh', () => {
        const mesh = new Mesh('test_quad');
        (mesh as any)._controlPoints = [
            new Vector4(0, 0, 0, 1),
            new Vector4(1, 0, 0, 1),
            new Vector4(0, 1, 0, 1),
            new Vector4(1, 1, 0, 1)
        ];
        mesh.createPolygon(0, 1, 3, 2);
        expect(mesh.polygonCount).toBe(1);

        const triangulatedMesh = PolygonModifier.triangulate(mesh);
        expect(triangulatedMesh.polygonCount).toBe(2);
    })