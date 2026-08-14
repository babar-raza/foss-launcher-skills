it('testExportWithBlendMaterial', () => {
        const scene = new Scene();
        const mesh = new Mesh('TestMesh');

        mesh.controlPoints.push(new Vector4(0.0, 0.0, 0.0, 1.0));
        mesh.controlPoints.push(new Vector4(1.0, 0.0, 0.0, 1.0));
        mesh.controlPoints.push(new Vector4(0.0, 1.0, 0.0, 1.0));
        mesh.createPolygon(0, 1, 2);

        const material = new PbrMaterial('BlendMaterial');
        material.albedo = new Vector3(1.0, 1.0, 1.0);
        material.transparency = 1.0;

        const node = scene.rootNode.createChildNode('TestNode');
        node.entity = mesh;
        node.material = material;

        scene.save('/tmp/test_blend.gltf', GltfFormat.getInstance());

        expect(fs.existsSync('/tmp/test_blend.gltf')).toBe(true);
    })