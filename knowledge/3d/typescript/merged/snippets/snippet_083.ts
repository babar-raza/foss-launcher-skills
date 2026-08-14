test('test_flip_coordinate_system', () => {
        const objContent = `# Test coordinate flip
v 1.0 2.0 3.0
v 2.0 3.0 4.0
v 3.0 4.0 5.0
f 1 2 3
`;
        const scene = new Scene();
        const stream = { read: () => objContent, close: () => {} };
        const options = new ObjLoadOptions();
        options.flipCoordinateSystem = true;
        
        const importer = new ObjImporter();
        importer.importScene(scene, stream, options);
        
        expect(scene.rootNode.childNodes.length).toBeGreaterThan(0);
        
        const node = scene.rootNode.childNodes[0];
        expect(node.entity).not.toBeNull();
    })