test('test_normals_and_uvs', () => {
        const objContent = `# With normals and UVs
v 0.0 0.0 0.0
v 1.0 0.0 0.0
v 1.0 1.0 0.0
v 0.0 1.0 0.0
vt 0.0 0.0
vt 1.0 0.0
vt 1.0 1.0
vt 0.0 1.0
vt 0.0 1.0
vn 0.0 0.0 1.0
f 1/1/1 2/2/1 3/3/1 4/4/1
`;
        const scene = new Scene();
        const stream = { read: () => objContent, close: () => {} };
        const options = new ObjLoadOptions();
        options.fileName = "test.obj";
        
        const importer = new ObjImporter();
        importer.importScene(scene, stream, options);
        
        expect(scene.rootNode.childNodes.length).toBeGreaterThan(0);
        
        const node = scene.rootNode.childNodes[0];
        expect(node.entity).not.toBeNull();
    })