it('testQuadTriangulation', () => {
        const scene = new Scene();
        const mesh = new Mesh("test_mesh");
        mesh.controlPoints = [
            new Vector4(0.0, 0.0, 0.0, 1.0),
            new Vector4(1.0, 0.0, 0.0, 1.0),
            new Vector4(1.0, 1.0, 0.0, 1.0),
            new Vector4(0.0, 1.0, 0.0, 1.0),
        ];
        mesh.createPolygon(0, 1, 2, 3);

        const node = new Node("test_node");
        node.entity = mesh;
        node.parentNode = scene.rootNode;

        scene.save('/tmp/test_quad_triangulation.stl', StlFormat);

        expect(fs.existsSync('/tmp/test_quad_triangulation.stl')).toBe(true);
    })