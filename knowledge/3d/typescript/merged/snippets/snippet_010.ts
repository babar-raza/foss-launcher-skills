describe('Test3MFRoundTrip', () => {
    it('testRoundTripExportImport', () => {
        const scene = new Scene();
        const loadOptions = new ThreeMfLoadOptions();
        const saveOptions = new ThreeMfSaveOptions();

        const mesh = new Mesh('test_cube');

        mesh.controlPoints.push(new Vector4(0, 0, 0, 1));
        mesh.controlPoints.push(new Vector4(1, 0, 0, 1));
        mesh.controlPoints.push(new Vector4(1, 1, 0, 1));
        mesh.controlPoints.push(new Vector4(0, 1, 0, 1));
        mesh.controlPoints.push(new Vector4(0, 0, 1, 1));
        mesh.controlPoints.push(new Vector4(1, 0, 1, 1));
        mesh.controlPoints.push(new Vector4(1, 1, 1, 1));
        mesh.controlPoints.push(new Vector4(0, 1, 1, 1));

        mesh.createPolygon(0, 1, 2);
        mesh.createPolygon(0, 2, 3);
        mesh.createPolygon(4, 7, 6);
        mesh.createPolygon(4, 6, 5);
        mesh.createPolygon(0, 4, 5);
        mesh.createPolygon(0, 5, 1);
        mesh.createPolygon(2, 6, 7);
        mesh.createPolygon(2, 7, 3);
        mesh.createPolygon(0, 3, 7);
        mesh.createPolygon(0, 7, 4);
        mesh.createPolygon(1, 5, 6);
        mesh.createPolygon(1, 6, 2);

        const node = new Node('test_cube');
        node.entity = mesh;
        node.parentNode = scene.rootNode;

        const originalVertices = mesh.controlPoints.length;
        const originalPolygons = mesh.polygonCount;

        scene.save('/tmp/test_roundtrip.3mf', saveOptions);

        const newScene = new Scene();
        newScene.open('/tmp/test_roundtrip.3mf', loadOptions);

        expect(newScene.rootNode.childNodes.length).toBeGreaterThan(0);

        const newMesh = newScene.rootNode.childNodes[0].entity as Mesh;
        expect(newMesh).toBeInstanceOf(Mesh);

        expect(newMesh!.controlPoints.length).toBe(originalVertices);
        expect(newMesh!.polygonCount).toBe(originalPolygons);
    });
})