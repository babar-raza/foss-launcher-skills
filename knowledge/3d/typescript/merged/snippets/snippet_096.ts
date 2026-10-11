it('testBasicTriangleExportBinary', () => {
        const scene = new Scene();
        const mesh = new Mesh("test_mesh");
        mesh.controlPoints = [
            new Vector4(0.0, 0.0, 0.0, 1.0),
            new Vector4(1.0, 0.0, 0.0, 1.0),
            new Vector4(1.0, 1.0, 0.0, 1.0),
        ];
        mesh.createPolygon(0, 1, 2);

        const node = new Node("test_node");
        node.entity = mesh;
        node.parentNode = scene.rootNode;

        const options = new StlSaveOptions();
        options.binaryMode = true;

        scene.save('/tmp/test_basic_binary.stl', StlFormat, options);

        expect(fs.existsSync('/tmp/test_basic_binary.stl')).toBe(true);
    })