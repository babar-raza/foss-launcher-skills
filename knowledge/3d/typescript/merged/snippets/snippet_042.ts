it('testFlipTexCoordV', () => {
        const scene = new Scene();
        const mesh = new Mesh('TestMesh');

        mesh.controlPoints.push(new Vector4(0.0, 0.0, 0.0, 1.0));
        mesh.controlPoints.push(new Vector4(1.0, 0.0, 0.0, 1.0));
        mesh.controlPoints.push(new Vector4(0.0, 1.0, 0.0, 1.0));
        mesh.createPolygon(0, 1, 2);

        const uvElement = new VertexElementUV();
        mesh.vertexElements.push(uvElement);

        scene.rootNode.createChildNode('TestNode').entity = mesh;

        const options1 = new GltfSaveOptions();
        options1.binaryMode = false;
        options1.flipTexCoordV = true;

        const options2 = new GltfSaveOptions();
        options2.binaryMode = false;
        options2.flipTexCoordV = false;

        scene.save('/tmp/test_flip1.gltf', GltfFormat.getInstance(), options1);
        scene.save('/tmp/test_flip2.gltf', GltfFormat.getInstance(), options2);

        expect(fs.existsSync('/tmp/test_flip1.gltf')).toBe(true);
        expect(fs.existsSync('/tmp/test_flip2.gltf')).toBe(true);
    })