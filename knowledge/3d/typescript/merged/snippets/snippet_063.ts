test('test_basic_cube_import', () => {
        const objContent = `# Simple cube OBJ
v 0.0 0.0 0.0
v 1.0 0.0 0.0
v 1.0 1.0 0.0
v 0.0 1.0 0.0
f 1 2 3 4
f 5 6 7 8
`;
        const scene = new Scene();
        const stream = { read: () => objContent, close: () => {} };
        const options = new ObjLoadOptions();
        options.fileName = "test.obj";
        
        const importer = new ObjImporter();
        importer.importScene(scene, stream, options);
        
        expect(scene.rootNode).not.toBeNull();
        expect(scene.rootNode.childNodes.length).toBeGreaterThan(0);
        
        const node = scene.rootNode.childNodes[0];
        expect(node.entity).not.toBeNull();
    })