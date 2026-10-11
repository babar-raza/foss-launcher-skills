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
    })