test('test_scale', () => {
        const objContent = `# Test scaling
o TestMesh
v 1.0 1.0 1.0
v 2.0 2.0 2.0
v 3.0 2.0 2.0
f 1 2 3
`;
        const scene = new Scene();
        const stream = { read: () => objContent, close: () => {} };
        const options = new ObjLoadOptions();
        options.scale = 2.0;
        
        const importer = new ObjImporter();
        importer.importScene(scene, stream, options);
        
        expect(scene.rootNode.childNodes.length).toBeGreaterThan(0);
        
        const node = scene.rootNode.childNodes[0];
        expect(node.entity).not.toBeNull();
    })