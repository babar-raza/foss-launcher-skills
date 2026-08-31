it('testRoundtripFile', () => {
        const scene1 = new Scene();
        const mesh1 = new Mesh("original");
        mesh1.controlPoints = [
            new Vector4(0.0, 0.0, 0.0, 1.0),
            new Vector4(1.0, 0.0, 0.0, 1.0),
            new Vector4(1.0, 1.0, 0.0, 1.0),
        ];
        mesh1.createPolygon(0, 1, 2);

        const node1 = new Node("original_node");
        node1.entity = mesh1;
        node1.parentNode = scene1.rootNode;

        scene1.save('/tmp/test_roundtrip.stl');

        const scene2 = Scene.fromFile('/tmp/test_roundtrip.stl');

        expect(scene2.rootNode.childNodes.length).toBe(1);
        const node2 = scene2.rootNode.childNodes[0];
        const mesh2 = node2.entity as Mesh;
        expect(mesh2!.polygonCount).toBe(1);
    })