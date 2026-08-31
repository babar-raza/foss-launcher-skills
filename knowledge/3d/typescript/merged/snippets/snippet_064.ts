test('test_multiple_objects', () => {
        const objContent = `# Multiple objects
o Cube1
v 0.0 0.0 0.0
v 1.0 0.0 0.0
v 1.0 1.0 0.0
v 0.0 1.0 0.0
f 1 2 3 4

o Cube2
v 2.0 0.0 0.0
v 3.0 0.0 0.0
v 3.0 1.0 0.0
v 2.0 1.0 0.0
f 5 6 7 8
`;
        const scene = new Scene();
        const stream = { read: () => objContent, close: () => {} };
        const options = new ObjLoadOptions();
        options.fileName = "test.obj";
        
        const importer = new ObjImporter();
        importer.importScene(scene, stream, options);
        
        expect(scene.rootNode.childNodes.length).toBeGreaterThanOrEqual(2);
    })