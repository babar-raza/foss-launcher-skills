test('test_smoothing_groups', () => {
        const objContent = `# Test smoothing groups
o TestMesh
v 0.0 0.0 0.0
v 1.0 0.0 0.0
v 1.0 1.0 0.0
v 0.0 1.0 0.0
f 1 2 3 4

s 1
v 2.0 0.0 0.0
v 3.0 0.0 0.0
f 5 6 7 8
`;
        const scene = new Scene();
        const stream = { read: () => objContent, close: () => {} };
        const options = new ObjLoadOptions();
        
        const importer = new ObjImporter();
        importer.importScene(scene, stream, options);
        
        expect(scene.rootNode.childNodes.length).toBeGreaterThan(0);
    })