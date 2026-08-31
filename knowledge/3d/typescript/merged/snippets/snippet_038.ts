it('testSimpleTriangleBinary', () => {
        const scene = new Scene();
        const mesh = new Mesh('TestMesh');

        mesh.controlPoints.push(new Vector4(0.0, 0.0, 0.0, 1.0));
        mesh.controlPoints.push(new Vector4(1.0, 0.0, 0.0, 1.0));
        mesh.controlPoints.push(new Vector4(0.0, 1.0, 0.0, 1.0));
        mesh.createPolygon(0, 1, 2);

        scene.rootNode.createChildNode('TestNode').entity = mesh;

        const options = new GltfSaveOptions();
        options.binaryMode = true;

        scene.save('/tmp/test_simple.glb', GltfFormat.getInstance(), options);

        expect(fs.existsSync('/tmp/test_simple.glb')).toBe(true);

        if (fs.existsSync('/tmp/test_simple.glb')) {
            const content = fs.readFileSync('/tmp/test_simple.glb');
            expect(content.length).toBeGreaterThan(0);
        }
    })