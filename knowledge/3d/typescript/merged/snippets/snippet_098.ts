describe('PolygonModifier', () => {
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
    });

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
    });

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
    });

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
    });

    test('triangulate_with_scene', () => {
        const scene = new Scene();
        const meshNode = new Node('mesh_node');
        
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
        meshNode.entity = mesh2;
        scene.rootNode.addChildNode(meshNode);

        PolygonModifier.triangulate(scene);
        expect((meshNode.entity as Mesh).polygonCount).toBe(6);
    });

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
    });

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
    });

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
    });
})