describe('TestGltfExporter', () => {
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
    });

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
    });

    it('testExportWithPositions', () => {
        const scene = new Scene();
        const mesh = new Mesh('TestMesh');

        mesh.controlPoints.push(new Vector4(0.0, 0.0, 0.0, 1.0));
        mesh.controlPoints.push(new Vector4(1.0, 0.0, 0.0, 1.0));
        mesh.controlPoints.push(new Vector4(0.0, 1.0, 0.0, 1.0));
        mesh.createPolygon(0, 1, 2);

        scene.rootNode.createChildNode('TestNode').entity = mesh;

        scene.save('/tmp/test_positions.gltf', GltfFormat.getInstance());

        expect(fs.existsSync('/tmp/test_positions.gltf')).toBe(true);
    });

    it('testExportWithNormals', () => {
        const scene = new Scene();
        const mesh = new Mesh('TestMesh');

        mesh.controlPoints.push(new Vector4(0.0, 0.0, 0.0, 1.0));
        mesh.controlPoints.push(new Vector4(1.0, 0.0, 0.0, 1.0));
        mesh.controlPoints.push(new Vector4(0.0, 1.0, 0.0, 1.0));
        mesh.createPolygon(0, 1, 2);

        const normalElement = new VertexElementNormal();
        mesh.vertexElements.push(normalElement);

        scene.rootNode.createChildNode('TestNode').entity = mesh;

        scene.save('/tmp/test_normales.gltf', GltfFormat.getInstance());

        expect(fs.existsSync('/tmp/test_normales.gltf')).toBe(true);
    });

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
    });

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
    });

    it('testGltfFormatCanExport', () => {
        const gltfFormat = GltfFormat;
        expect(gltfFormat.canExport).toBe(true);
    });

    it('testExportWithMaterial', () => {
        const scene = new Scene();
        const mesh = new Mesh('TestMesh');

        mesh.controlPoints.push(new Vector4(0.0, 0.0, 0.0, 1.0));
        mesh.controlPoints.push(new Vector4(1.0, 0.0, 0.0, 1.0));
        mesh.controlPoints.push(ne