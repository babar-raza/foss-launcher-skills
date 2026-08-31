it('testExportMultipleMeshes', () => {
        const scene = new Scene();

        const mesh1 = new Mesh("mesh1");
        mesh1.controlPoints = [
            new Vector4(0.0, 0.0, 0.0, 1.0),
            new Vector4(1.0, 0.0, 0.0, 1.0),
            new Vector4(1.0, 1.0, 0.0, 1.0),
        ];
        mesh1.createPolygon(0, 1, 2);

        const node1 = new Node("node1");
        node1.entity = mesh1;
        node1.parentNode = scene.rootNode;

        const mesh2 = new Mesh("mesh2");
        mesh2.controlPoints = [
            new Vector4(2.0, 0.0, 0.0, 1.0),
            new Vector4(3.0, 0.0, 0.0, 1.0),
            new Vector4(3.0, 1.0, 0.0, 1.0),
        ];
        mesh2.createPolygon(0, 1, 2);

        const node2 = new Node("node2");
        node2.entity = mesh2;
        node2.parentNode = scene.rootNode;

        const mesh3 = new Mesh("mesh3");
        mesh3.controlPoints = [
            new Vector4(4.0, 0.0, 0.0, 1.0),
            new Vector4(5.0, 0.0, 0.0, 1.0),
            new Vector4(5.0, 1.0, 0.0, 1.0),
        ];
        mesh3.createPolygon(0, 1, 2);

        const node3 = new Node("node3");
        node3.entity = mesh3;
        node3.parentNode = scene.rootNode;

        scene.save('/tmp/test_multiple.stl', StlFormat);
        expect(fs.existsSync('/tmp/test_multiple.stl')).toBe(true);
    })