it('testExportWithUvs', () => {
        const scene = new Scene();
        const mesh = new Mesh('TestMesh');

        mesh.controlPoints.push(new Vector4(0.0, 0.0, 0.0, 1.0));
        mesh.controlPoints.push(new Vector4(1.0, 0.0, 0.0, 1.0));
        mesh.controlPoints.push(new Vector4(0.0, 1.0, 0.0, 1.0));
        mesh.createPolygon(0, 1, 2);

        const uvElement = new VertexElementUV();
        mesh.vertexElements.push(uvElement);

        scene.rootNode.createChildNode('TestNode').entity = mesh;

        scene.save('/tmp/test_uvs.gltf', GltfFormat.getInstance());

        expect(fs.existsSync('/tmp/test_uvs.gltf')).toBe(true);
    })