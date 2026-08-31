it('testExportWithMaterial', () => {
        const scene = new Scene();
        const mesh = new Mesh('TestMesh');

        mesh.controlPoints.push(new Vector4(0.0, 0.0, 0.0, 1.0));
        mesh.controlPoints.push(new Vector4(1.0, 0.0, 0.0, 1.0));
        mesh.controlPoints.push(new Vector4(0.0, 1.0, 0.0, 1.0));
        mesh.createPolygon(0, 1, 2);

        const albedo = new Vector3(0.8, 0.2, 0.3);
        const material = new PbrMaterial('RedMaterial', albedo);
        material.metallicFactor = 0.5;
        material.roughnessFactor = 0.7;

        const node = scene.rootNode.createChildNode('TestNode');
        node.entity = mesh;
        node.material = material;

        scene.save('/tmp/test_material.gltf', GltfFormat.getInstance());

        expect(fs.existsSync('/tmp/test_material.gltf')).toBe(true);
    })