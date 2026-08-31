it('testExportWithTransparentMaterial', () => {
        const scene = new Scene();
        const mesh = new Mesh('TestMesh');

        mesh.controlPoints.push(new Vector4(0.0, 0.0, 0.0, 1.0));
        mesh.controlPoints.push(new Vector4(1.0, 0.0, 0.0, 1.0));
        mesh.controlPoints.push(new Vector4(0.0, 1.0, 0.0, 1.0));
        mesh.createPolygon(0, 1, 2);

        const material = new PbrMaterial('TransparentMaterial');
        material.albedo = new Vector3(1.0, 1.0, 1.0);
        material.transparency = 0.6;

        const node = scene.rootNode.createChildNode('TestNode');
        node.entity = mesh;
        node.material = material;

        scene.save('/tmp/test_transparent.gltf', GltfFormat.getInstance());

        expect(fs.existsSync('/tmp/test_transparent.gltf')).toBe(true);
    })