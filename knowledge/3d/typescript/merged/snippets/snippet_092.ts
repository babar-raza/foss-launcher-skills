it('testSceneSaveToFileAscii', () => {
        const scene = new Scene();
        const mesh = new Mesh("test_mesh");
        mesh.controlPoints = [
            new Vector4(0.0, 0.0, 0.0, 1.0),
            new Vector4(1.0, 0.0, 0.0, 1.0),
            new Vector4(1.0, 1.0, 0.0, 1.0),
            new Vector4(0.0, 1.0, 0.0, 1.0),
        ];
        mesh.createPolygon(0, 1, 2);
        mesh.createPolygon(0, 2, 3);

        const node = new Node("test_node");
        node.entity = mesh;
        node.parentNode = scene.rootNode;

        scene.save('/tmp/test_scene_ascii.stl');

        expect(fs.existsSync('/tmp/test_scene_ascii.stl')).toBe(true);
        const content = fs.readFileSync('/tmp/test_scene_ascii.stl', 'utf8');
        expect(content.includes("solid")).toBe(true);
        expect(content.includes("endsolid")).toBe(true);
    })