it('testSimpleTriangleAscii', () => {
        const scene = new Scene();
        const mesh = new Mesh('TestMesh');

        mesh.controlPoints.push(new Vector4(0.0, 0.0, 0.0, 1.0));
        mesh.controlPoints.push(new Vector4(1.0, 0.0, 0.0, 1.0));
        mesh.controlPoints.push(new Vector4(0.0, 1.0, 0.0, 1.0));
        mesh.createPolygon(0, 1, 2);

        scene.rootNode.createChildNode('TestNode').entity = mesh;

        scene.save('/tmp/test_simple.gltf', GltfFormat.getInstance());

        expect(fs.existsSync('/tmp/test_simple.gltf')).toBe(true);
    })